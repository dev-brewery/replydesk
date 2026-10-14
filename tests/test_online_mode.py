"""T14: --online end-to-end. All offline; urllib transport mocked.

No test reads the real ``.env``: a fake one is written to a temp dir, and the
transport is a fake ``urlopen``. Fake endpoint/key values use the reserved
``.test`` TLD and obviously fake tokens.
"""

import http.client
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

import app
from replydesk.llm import HttpLLM

# Fake config values — reserved TLD, fake token; never real endpoints or keys.
FAKE_BASE_URL = "http://llm.endpoint.test/v1"
FAKE_MODEL = "test-model"
FAKE_API_KEY = "test-key-000"

_ASSIST_MARKER = "triage customer reviews"
_DRAFT_REPLY = (
    "Thank you for the kind words. We are so glad you enjoyed your visit, "
    "and we hope to see you again soon."
)


def _fake_env_text(base_url=FAKE_BASE_URL, model=FAKE_MODEL, api_key=FAKE_API_KEY):
    lines = [f"LLM_BASE_URL={base_url}", f"LLM_MODEL={model}"]
    if api_key is not None:
        lines.append(f"LLM_API_KEY={api_key}")
    return "\n".join(lines) + "\n"


class _FakeResponse:
    def __init__(self, content: str):
        self._body = json.dumps(
            {"choices": [{"message": {"content": content}}]}
        ).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeTransport:
    """Stands in for urllib.request.urlopen; records requests, routes replies.

    Assist consults (system prompt contains the triage-assist marker) get the
    routed assist reply; draft calls get ``_DRAFT_REPLY``.
    """

    def __init__(self, assist_reply="thank-you|genuine thanks", fail=False):
        self.requests = []
        self.assist_reply = assist_reply
        self.fail = fail

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.fail:
            raise OSError("connection refused")
        body = json.loads(request.data.decode("utf-8"))
        system = body["messages"][0]["content"]
        if _ASSIST_MARKER in system:
            return _FakeResponse(self.assist_reply)
        return _FakeResponse(_DRAFT_REPLY)

    def llm_calls(self):
        return [json.loads(r.data.decode("utf-8")) for r in self.requests]


def _auth_header(transport):
    return [req.headers.get("Authorization") for req in transport.requests]


class OnlineClientConfigTests(unittest.TestCase):
    """online_client(): fake .env in a temp dir toggles the mode."""

    def _env_file(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, ".env")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_valid_env_builds_client(self):
        path = self._env_file(_fake_env_text())
        client, degraded = app.online_client(path)
        self.assertIsNone(degraded)
        self.assertIsInstance(client, HttpLLM)

    def test_missing_env_degrades(self):
        client, degraded = app.online_client(
            os.path.join(tempfile.gettempdir(), "no-such-env-file")
        )
        self.assertIsNone(client)
        self.assertIn("could not read", degraded)

    def test_missing_required_values_degrade(self):
        path = self._env_file(_fake_env_text(base_url=""))
        client, degraded = app.online_client(path)
        self.assertIsNone(client)
        self.assertIn("LLM_BASE_URL", degraded)

    def test_api_key_optional(self):
        path = self._env_file(_fake_env_text(api_key=None))
        client, degraded = app.online_client(path)
        self.assertIsNone(degraded)
        self.assertIsInstance(client, HttpLLM)


class OnlineRunTests(unittest.TestCase):
    """Server-level runs with the transport mocked at urllib.request.urlopen."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env_path = os.path.join(tmp.name, ".env")
        with open(self.env_path, "w", encoding="utf-8") as fh:
            fh.write(_fake_env_text())
        self.transport = _FakeTransport()
        client, degraded = app.online_client(self.env_path)
        self.assertIsNone(degraded)
        # attempts=1 keeps the failure-mode tests fast; retries are llm.py's job.
        client._attempts = 1
        self.httpd = app.make_server(
            "127.0.0.1", 0, client=client, note_text="", demo_mode=False,
        )
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def _post(self, reviews):
        body = urllib.parse.urlencode({
            "tone": "# Voice\nWarm, plain, short.\n\n"
                    "# Facts I'll stand behind\n- we open at 7am",
            "reviews": reviews,
        }).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/run", body=body)
        response = conn.getresponse()
        html = response.read().decode("utf-8")
        conn.close()
        return response, html

    def test_online_run_produces_model_drafts(self):
        with mock.patch("urllib.request.urlopen", self.transport):
            response, html = self._post("5 | the barista remembered my order")
        self.assertEqual(response.status, 200)
        self.assertIn("MODEL", html)
        self.assertNotIn("Template reply", html)
        self.assertNotIn("offline mode", html)
        # The fake key reached the transport as a bearer token, never the page.
        self.assertNotIn(FAKE_API_KEY, html)
        self.assertIn("Bearer " + FAKE_API_KEY, _auth_header(self.transport)[0])

    def test_assist_consult_fires_for_star_fall_through(self):
        with mock.patch("urllib.request.urlopen", self.transport):
            self._post("5 | the barista remembered my order")
        keys = [
            json.loads(req.data.decode("utf-8")) for req in self.transport.requests
        ]
        # One assist consult (key assist:r1) plus the draft call (key r1).
        assist_bodies = [b for b in keys if "triage customer reviews"
                         in b["messages"][0]["content"]]
        self.assertEqual(len(assist_bodies), 1)
        self.assertEqual(assist_bodies[0]["max_tokens"], 512)
        draft_bodies = [b for b in keys if b not in assist_bodies]
        self.assertEqual([b["max_tokens"] for b in draft_bodies], [800])
        self.assertEqual(
            [b["model"] for b in keys], [FAKE_MODEL] * len(keys)
        )


class OnlineDegradedTests(unittest.TestCase):
    """Failure modes degrade to the labeled template path with a clear note."""

    def _run(self, client, note_text, reviews="5 | the barista remembered my order"):
        httpd = app.make_server("127.0.0.1", 0, client=client,
                                note_text=note_text, demo_mode=False)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            body = urllib.parse.urlencode({
                "tone": "# Voice\nWarm, plain, short.\n\n"
                        "# Facts I'll stand behind\n- we open at 7am",
                "reviews": reviews,
            }).encode()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/run", body=body)
            response = conn.getresponse()
            html = response.read().decode("utf-8")
            conn.close()
            return response, html
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_missing_env_degrades_with_note(self):
        client, degraded = app.online_client("no-such-env-file")
        self.assertIsNotNone(degraded)
        transport = _FakeTransport()
        with mock.patch("urllib.request.urlopen", transport):
            response, html = self._run(
                app._OfflineClient(),
                app._ONLINE_DEGRADED_NOTE.format(degraded),
            )
        self.assertEqual(response.status, 200)
        self.assertIn("Online mode unavailable", html)
        self.assertIn("Template reply", html)
        self.assertEqual(transport.requests, [])  # never reached the network

    def test_llm_error_degrades_to_labeled_template(self):
        client = HttpLLM("http://llm.endpoint.test/v1", FAKE_MODEL,
                         api_key=FAKE_API_KEY, attempts=1)
        transport = _FakeTransport(fail=True)
        with mock.patch("urllib.request.urlopen", transport):
            response, html = self._run(client, note_text="")
        self.assertEqual(response.status, 200)
        self.assertIn("Template reply", html)
        self.assertIn("model unreachable", html)
        self.assertGreater(len(transport.requests), 0)  # attempted, then fell back


if __name__ == "__main__":
    unittest.main()
