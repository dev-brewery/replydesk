"""T27: /api/auth/* routes — bearer sessions, route-aware preflight, rate limit.

In-process ThreadingHTTPServer on an ephemeral loopback port (T22 pattern),
tempfile accounts DB, stub LLM client. Offline: no .env read, no socket
beyond loopback.
"""

import http.client
import json
import tempfile
import threading
import unittest

import replydesk.api as api
from replydesk.accounts import AccountStore
from replydesk.api import ALLOWED_ORIGINS, CAPS, make_api_server

_HOST = "127.0.0.1"  # loopback only

# RFC 5737 documentation address (XFF): never a real client IP.
_TEST_IP = "203.0.113.9"

_NAME = "Test Owner"
_EMAIL = "owner@example.test"
_PASSWORD = "correct horse battery"


class _TemplateClient:
    """Raises the one failure type the pipeline degrades on (LLMError)."""

    def complete(self, system, user, *, key, max_tokens):
        from replydesk.llm import LLMError

        raise LLMError("stub endpoint down")


class _AuthClient:
    """Requests against one server; returns (status, payload_or_text, headers)."""

    def __init__(self, port):
        self.port = port

    def request(self, method="POST", path="/api/auth/signup", body=None,
                origin=None, token=None, xff=None, scheme="Token"):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        if token:
            headers["Authorization"] = f"{scheme} {token}"
        if xff:
            headers["X-Forwarded-For"] = xff
        data = json.dumps(body).encode("utf-8") if body is not None else None
        conn = http.client.HTTPConnection(_HOST, self.port, timeout=10)
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return resp.status, payload, dict(resp.getheaders())


class AuthRoutesTest(unittest.TestCase):
    """Each test gets its own server + fresh tempfile accounts DB."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AccountStore(f"{self.tmp.name}/accounts.db")
        self.httpd = make_api_server(_HOST, 0, _TemplateClient(),
                                     accounts=self.store)
        self.port = self.httpd.server_address[1]
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.api = _AuthClient(self.port)

    def signup(self, **overrides):
        body = {"name": _NAME, "email": _EMAIL, "password": _PASSWORD}
        origin = overrides.pop("origin", None)
        xff = overrides.pop("xff", _TEST_IP)
        body.update(overrides)
        return self.api.request(body=body, origin=origin, xff=xff)

    # -- full round trip ----------------------------------------------------

    def test_signup_login_me_logout_round_trip(self):
        status, payload, _ = self.signup()
        self.assertEqual(status, 201)
        user = payload["user"]
        self.assertEqual(user["email"], _EMAIL)
        self.assertEqual(user["name"], _NAME)
        self.assertEqual(user["plan"], "founding_trial")
        self.assertEqual(user["plan_status"], "trial_active")
        self.assertIn("token", payload)
        self.assertNotIn("password_hash", json.dumps(payload))

        status, payload, _ = self.api.request(
            path="/api/auth/login",
            body={"email": _EMAIL.upper(), "password": _PASSWORD})
        self.assertEqual(status, 200)
        token = payload["token"]

        status, payload, _ = self.api.request(
            method="GET", path="/api/auth/me", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["email"], _EMAIL)

        status, payload, headers = self.api.request(
            method="POST", path="/api/auth/logout", token=token)
        self.assertEqual(status, 204)
        self.assertIsNone(payload)

        status, payload, _ = self.api.request(
            method="GET", path="/api/auth/me", token=token)
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Please sign in.")

    def test_signup_validation_and_duplicate(self):
        cases = [
            ({"name": "", "email": _EMAIL, "password": _PASSWORD},
             "Please enter your name."),
            ({"name": _NAME, "email": "not-an-email",
              "password": _PASSWORD},
             "Please enter a valid email address."),
            ({"name": _NAME, "email": _EMAIL, "password": "short"},
             "Password must be at least 8 characters."),
        ]
        for body, message in cases:
            with self.subTest(body=body):
                status, payload, _ = self.signup(**body)
                self.assertEqual(status, 400)
                self.assertEqual(payload["error"], message)
        # Duplicate is case-insensitive (§13: COLLATE NOCASE).
        status, _, _ = self.signup()
        self.assertEqual(status, 201)
        status, payload, _ = self.signup(email=_EMAIL.upper())
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"],
                         "An account with that email already exists.")

    def test_wrong_password_is_generic_401(self):
        self.signup()
        status, payload, _ = self.api.request(
            path="/api/auth/login",
            body={"email": _EMAIL, "password": "not the password"})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Wrong email or password.")
        # Unknown email: same generic message, no enumeration.
        status, payload, _ = self.api.request(
            path="/api/auth/login",
            body={"email": "nobody@example.test", "password": _PASSWORD})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Wrong email or password.")

    def test_auth_caps_join_the_caps_table(self):
        self.assertEqual(CAPS["MAX_NAME_CHARS"], 60)
        self.assertEqual(CAPS["MAX_EMAIL_CHARS"], 254)
        self.assertEqual(CAPS["MAX_PASSWORD_CHARS"], 1024)
        status, payload, _ = self.signup(name="x" * (CAPS["MAX_NAME_CHARS"] + 1))
        self.assertEqual(status, 400)
        self.assertIn("MAX_NAME_CHARS", payload["error"])

    def test_malformed_auth_body_is_400(self):
        conn = http.client.HTTPConnection(_HOST, self.port, timeout=10)
        conn.request("POST", "/api/auth/signup", body=b"{not json",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        payload = json.loads(resp.read())
        conn.close()
        self.assertEqual(resp.status, 400)
        self.assertEqual(payload["error"], "malformed JSON")

    # -- bearer auth --------------------------------------------------------

    def test_me_requires_bearer(self):
        status, payload, _ = self.api.request(method="GET", path="/api/auth/me")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Please sign in.")
        status, payload, _ = self.api.request(
            method="GET", path="/api/auth/me", token="not-a-real-token")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Please sign in.")

    def test_bearer_scheme_is_case_insensitive(self):
        _, signup, _ = self.signup()
        token = signup["token"]
        status, _, _ = self.api.request(
            method="GET", path="/api/auth/me", token=token, scheme="token")
        self.assertEqual(status, 200)

    def test_logout_requires_valid_session(self):
        status, payload, _ = self.api.request(
            method="POST", path="/api/auth/logout", token="bogus-token")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Please sign in.")

    # -- preflight is route-aware -------------------------------------------

    def test_preflight_auth_routes_allow_authorization(self):
        status, _, headers = self.api.request(
            method="OPTIONS", path="/api/auth/signup",
            origin=ALLOWED_ORIGINS[0])
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Headers"],
                         "Content-Type, Authorization")
        self.assertEqual(headers["Access-Control-Allow-Methods"],
                         "GET, POST, OPTIONS")

    def test_preflight_draft_route_has_no_authorization(self):
        conn = http.client.HTTPConnection(_HOST, self.port, timeout=10)
        conn.request("OPTIONS", "/api/draft",
                     headers={"Origin": ALLOWED_ORIGINS[0]})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.getheader("Access-Control-Allow-Headers"),
                         "Content-Type")

    def test_auth_responses_echo_allowlisted_origin(self):
        status, _, headers = self.signup(origin=ALLOWED_ORIGINS[0])
        self.assertEqual(status, 201)
        self.assertEqual(headers["Access-Control-Allow-Origin"],
                         ALLOWED_ORIGINS[0])
        # Errors carry the same policy.
        status, _, headers = self.signup(password="short",
                                         origin=ALLOWED_ORIGINS[0])
        self.assertEqual(status, 400)
        self.assertEqual(headers["Access-Control-Allow-Origin"],
                         ALLOWED_ORIGINS[0])

    # -- signup rate limit --------------------------------------------------

    def test_sixth_signup_in_window_is_rate_limited(self):
        real_clock = api.rate_clock
        clock = {"t": 1000.0}
        api.rate_clock = lambda: clock["t"]
        self.addCleanup(setattr, api, "rate_clock", real_clock)
        for i in range(api.SIGNUP_RATE_LIMIT):
            status, _, _ = self.signup(email=f"user{i}@example.test")
            self.assertEqual(status, 201)
        status, payload, _ = self.signup(
            email="user6@example.test")
        self.assertEqual(status, 429)
        self.assertEqual(payload["error"],
                         "Too many sign-ups from this address. Try again later.")
        # Sliding window: after 60 minutes the next signup is allowed again.
        clock["t"] += api.SIGNUP_WINDOW_SECONDS + 1
        status, _, _ = self.signup(email="user6@example.test")
        self.assertEqual(status, 201)
        # A different XFF IP is not limited by the first IP's attempts.
        status, _, _ = self.signup(email="user7@example.test",
                                   xff="203.0.113.10")
        self.assertEqual(status, 201)

    # -- degraded / unchanged behavior --------------------------------------

    def test_accounts_none_auth_is_503_health_stays_200(self):
        httpd = make_api_server(_HOST, 0, None, accounts=None)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        client = _AuthClient(port)
        status, payload, _ = client.request(
            body={"name": _NAME, "email": _EMAIL, "password": _PASSWORD})
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "service unavailable")
        status, payload, _ = client.request(method="GET", path="/api/auth/me")
        self.assertEqual(status, 503)
        status, payload, _ = client.request(method="GET", path="/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})

    def test_draft_and_health_unchanged(self):
        from tests.test_api import _valid_body

        status, payload, _ = self.api.request(
            method="GET", path="/api/health")
        self.assertEqual(status, 200)
        conn = http.client.HTTPConnection(_HOST, self.port, timeout=10)
        conn.request("POST", "/api/draft", body=_valid_body(),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        payload = json.loads(resp.read())
        conn.close()
        # The dummy client fails inside the pipeline, which must degrade to
        # labeled template drafts — /api/draft is unchanged by T27.
        self.assertEqual(resp.status, 200)
        self.assertTrue(all(d["source"] == "template"
                            for d in payload["drafts"]))

    def test_unknown_auth_path_is_404(self):
        status, payload, _ = self.api.request(
            path="/api/auth/unknown",
            body={"name": _NAME, "email": _EMAIL, "password": _PASSWORD})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not found")


if __name__ == "__main__":
    unittest.main()
