"""T22: /api/draft generation bridge. In-process, loopback, no .env read.

The server is built with ``make_api_server`` on an ephemeral loopback port and
the LLM client is a stub injected directly — no test reads ``.env`` and no
socket beyond loopback is opened.
"""

import http.client
import json
import re
import threading
import unittest

from replydesk.api import (
    ALLOWED_ORIGINS,
    CAPS,
    make_api_server,
    runresult_json,
)
from replydesk.fixtures import demo_run
from replydesk.llm import LLMError
from tools.build_demo import demo_run_json

_HOST = "127.0.0.1"  # loopback only

_TONE = (
    "# Voice\nWe are warm and direct, and we say thanks by name.\n\n"
    "# Facts I'll stand behind\n- we open at 7am\n"
)
_DRAFT_REPLY = (
    "Thank you for the kind words. We are so glad you enjoyed your visit, "
    "and we hope to see you again soon."
)


class StubClient:
    """Returns a fixed reply for every draft call; assist degrades quietly."""

    def __init__(self, reply=_DRAFT_REPLY, error=None):
        self.reply = reply
        self.error = error
        self.calls = 0

    def complete(self, system, user, *, key, max_tokens):
        self.calls += 1
        if self.error:
            raise LLMError(self.error)
        return self.reply


def _valid_body(**overrides):
    body = {
        "tone": _TONE,
        "profile": {"name": "test cafe", "kind": "coffee shop", "city": "town"},
        "reviews": [
            {"review_id": "r1", "stars": 5, "text": "great coffee and staff"},
            {"review_id": "r2", "stars": 2, "text": "order was cold"},
        ],
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


class ApiServerTest(unittest.TestCase):
    """Each test gets its own server on an ephemeral loopback port."""

    def setUp(self):
        self.client = StubClient()
        self.httpd = make_api_server(_HOST, 0, self.client)
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def request(self, body=b"", method="POST", origin=None, path="/api/draft"):
        conn = http.client.HTTPConnection(_HOST, self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    # -- health -------------------------------------------------------------

    def test_health_returns_ok(self):
        resp, data = self.request(method="GET", path="/api/health")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"),
                         "application/json; charset=utf-8")
        self.assertEqual(json.loads(data), {"ok": True})

    def test_health_echoes_allowlisted_origin(self):
        resp, _ = self.request(method="GET", path="/api/health",
                               origin=ALLOWED_ORIGINS[0])
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"),
                         ALLOWED_ORIGINS[0])

    def test_unknown_get_path_is_404(self):
        resp, data = self.request(method="GET", path="/api/other")
        self.assertEqual(resp.status, 404)
        self.assertEqual(json.loads(data), {"error": "not found"})

    def test_draft_post_still_works_alongside_health(self):
        resp, data = self.request(_valid_body())
        self.assertEqual(resp.status, 200)
        self.assertIn("drafts", json.loads(data))

    # -- CORS ---------------------------------------------------------------

    def test_preflight_echoes_allowlisted_origin(self):
        for origin in ALLOWED_ORIGINS:
            with self.subTest(origin=origin):
                resp, _ = self.request(method="OPTIONS", origin=origin)
                self.assertEqual(resp.status, 204)
                self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), origin)
                self.assertEqual(
                    resp.getheader("Access-Control-Allow-Methods"), "POST, OPTIONS")
                self.assertEqual(
                    resp.getheader("Access-Control-Allow-Headers"), "Content-Type")
                self.assertEqual(resp.getheader("Access-Control-Max-Age"), "600")

    def test_prefflight_non_allowlisted_origin_gets_no_acao(self):
        resp, _ = self.request(method="OPTIONS", origin="https://evil.example.com")
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))

    def test_post_allowlisted_origin_gets_acao(self):
        resp, _ = self.request(_valid_body(), origin="https://replydeskhq.tech")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"),
                         "https://replydeskhq.tech")

    def test_post_non_allowlisted_origin_gets_no_acao(self):
        resp, _ = self.request(_valid_body(), origin="https://evil.example.com")
        self.assertEqual(resp.status, 200)
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))

    # -- happy path ---------------------------------------------------------

    def test_happy_path_schema(self):
        resp, data = self.request(_valid_body())
        self.assertEqual(resp.status, 200)
        payload = json.loads(data)
        self.assertEqual(payload["decisions"][0]["review_id"], "r1")
        self.assertEqual(payload["drafts"][0]["review_id"], "r1")
        self.assertIn("generated_on", payload)
        self.assertEqual(payload["profile"],
                         {"name": "test cafe", "kind": "coffee shop", "city": "town"})
        self.assertGreater(self.client.calls, 0)

    def test_profile_optional_defaults_applied(self):
        body = json.loads(_valid_body())
        del body["profile"]
        resp, data = self.request(json.dumps(body).encode("utf-8"))
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(json.loads(data)["decisions"]), 2)

    def test_runresult_json_matches_demo_wrapper_bytes(self):
        run = demo_run()
        self.assertEqual(runresult_json(run), demo_run_json(run))

    # -- caps ---------------------------------------------------------------

    def _assert_cap_error(self, resp, data, status, cap_name):
        self.assertEqual(resp.status, status)
        self.assertIn(cap_name, json.loads(data)["error"])

    def test_cap_max_reviews(self):
        reviews = [{"review_id": f"r{i}", "stars": 5, "text": "fine"}
                   for i in range(CAPS["MAX_REVIEWS"] + 1)]
        resp, data = self.request(_valid_body(reviews=reviews))
        self._assert_cap_error(resp, data, 400, "MAX_REVIEWS")

    def test_cap_max_tone_chars(self):
        resp, data = self.request(_valid_body(
            tone=_TONE + "x" * (CAPS["MAX_TONE_CHARS"] + 1)))
        self._assert_cap_error(resp, data, 400, "MAX_TONE_CHARS")

    def test_cap_max_review_chars(self):
        body = json.loads(_valid_body())
        body["reviews"][0]["text"] = "x" * (CAPS["MAX_REVIEW_CHARS"] + 1)
        resp, data = self.request(json.dumps(body).encode("utf-8"))
        self._assert_cap_error(resp, data, 400, "MAX_REVIEW_CHARS")

    def test_cap_max_profile_chars(self):
        body = json.loads(_valid_body())
        body["profile"]["name"] = "x" * (CAPS["MAX_PROFILE_CHARS"] + 1)
        resp, data = self.request(json.dumps(body).encode("utf-8"))
        self._assert_cap_error(resp, data, 400, "MAX_PROFILE_CHARS")

    def test_cap_max_body_bytes(self):
        big = b"x" * (CAPS["MAX_BODY_BYTES"] + 1)
        resp, data = self.request(big)
        self._assert_cap_error(resp, data, 413, "MAX_BODY_BYTES")

    def test_review_id_pattern(self):
        body = json.loads(_valid_body())
        body["reviews"][0]["review_id"] = "BAD_ID!"
        resp, data = self.request(json.dumps(body).encode("utf-8"))
        self._assert_cap_error(resp, data, 400, "review_id")

    # -- malformed input ----------------------------------------------------

    def test_malformed_json_is_400(self):
        resp, data = self.request(b"{not json")
        self.assertEqual(resp.status, 400)
        self.assertIn("error", json.loads(data))

    def test_errors_never_echo_user_text(self):
        secret = "SECRET-REVIEW-TEXT-xyzzy"
        body = json.loads(_valid_body())
        body["reviews"][0]["text"] = "x" * (CAPS["MAX_REVIEW_CHARS"] + len(secret))
        body["reviews"][0]["text"] += secret
        resp, data = self.request(json.dumps(body).encode("utf-8"))
        self.assertEqual(resp.status, 400)
        self.assertNotIn(secret, data.decode("utf-8"))

    def test_unknown_path_is_404(self):
        resp, _ = self.request(_valid_body(), path="/api/other")
        self.assertEqual(resp.status, 404)

    # -- degradation and 503 ------------------------------------------------

    def test_pipeline_failure_degrades_to_200_templates(self):
        self.client.error = "stub endpoint down"
        resp, data = self.request(_valid_body())
        self.assertEqual(resp.status, 200)
        payload = json.loads(data)
        self.assertTrue(all(d["source"] == "template" for d in payload["drafts"]))

    def test_client_none_is_503(self):
        httpd = make_api_server(_HOST, 0, None)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection(_HOST, port, timeout=10)
        conn.request("POST", "/api/draft", body=_valid_body(),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        self.assertEqual(resp.status, 503)
        self.assertEqual(json.loads(data)["error"], "service unavailable")

    def test_client_none_malformed_json_is_400(self):
        # Degraded mode must still validate requests (A9: behavior is the
        # same with or without a local .env).
        httpd = make_api_server(_HOST, 0, None)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection(_HOST, port, timeout=10)
        conn.request("POST", "/api/draft", body="{not json",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        self.assertEqual(resp.status, 400)
        self.assertEqual(json.loads(data)["error"], "malformed JSON")


if __name__ == "__main__":
    unittest.main()
