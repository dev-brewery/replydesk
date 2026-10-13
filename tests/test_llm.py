"""Tests for replydesk.llm — urlopen patched, zero sockets."""

import io
import json
import tempfile
import urllib.error
import unittest
from unittest import mock

from replydesk.llm import FixtureLLM, HttpLLM, LLMError, load_env_config


def _resp(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    return io.BytesIO(body)


def _ok_payload(content: str = "hello draft") -> dict:
    return {"choices": [{"message": {"content": content}}]}


class FixtureLLMTests(unittest.TestCase):
    def test_returns_by_key(self):
        fx = FixtureLLM({"rev-1": "Thanks so much!", "rev-2": "Sorry about that."})
        self.assertEqual(fx.complete("sys", "usr", key="rev-1", max_tokens=400),
                         "Thanks so much!")

    def test_missing_key_clear_error(self):
        fx = FixtureLLM({"rev-1": "x"})
        with self.assertRaises(LLMError) as ctx:
            fx.complete("sys", "usr", key="rev-9", max_tokens=400)
        self.assertIn("rev-9", str(ctx.exception))

    def test_no_network_attribute(self):
        fx = FixtureLLM({})
        self.assertFalse(hasattr(fx, "urlopen"))


class HttpLLMTests(unittest.TestCase):
    def _client(self, **kw) -> HttpLLM:
        defaults = dict(base_url="https://fake.example/v1", model="fake-model")
        defaults.update(kw)
        return HttpLLM(**defaults)

    def test_success(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=_resp(_ok_payload("a fine reply"))):
            out = self._client().complete("sys", "usr", key="rev-1", max_tokens=400)
        self.assertEqual(out, "a fine reply")

    def test_retry_then_success(self):
        responses = [mock.Mock(side_effect=urllib.error.URLError("boom")),
                     mock.Mock(side_effect=urllib.error.URLError("boom")),
                     _resp(_ok_payload("third time works"))]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            out = self._client(attempts=3).complete("s", "u", key="k", max_tokens=10)
        self.assertEqual(out, "third time works")

    def test_final_failure_raises_llm_error(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("down")):
            with self.assertRaises(LLMError) as ctx:
                self._client(attempts=3).complete("s", "u", key="k", max_tokens=10)
        self.assertIn("3 attempts", str(ctx.exception))

    def test_body_carries_policy_fields(self):
        req_holder = {}
        with mock.patch("urllib.request.urlopen", side_effect=_capture(req_holder)):
            self._client(api_key="fake-key").complete(
                "sys prompt", "usr prompt", key="rev-1", max_tokens=400)
        body = json.loads(req_holder["data"].decode("utf-8"))
        self.assertEqual(body["model"], "fake-model")
        self.assertEqual(body["max_tokens"], 400)
        self.assertEqual(body["temperature"], 0.3)
        self.assertEqual(body["extra_body"]["thinking"]["value"], "low")
        self.assertEqual(body["messages"][0]["content"], "sys prompt")
        self.assertEqual(body["messages"][1]["content"], "usr prompt")
        self.assertIn("fake.example/v1/chat/completions",
                      req_holder["full_url"])

    def test_bearer_header_only_with_key(self):
        cases = []
        for api_key in ("fake-key", ""):
            req_holder = {}
            with mock.patch("urllib.request.urlopen",
                            side_effect=_capture(req_holder)):
                self._client(api_key=api_key).complete(
                    "s", "u", key="k", max_tokens=10)
            cases.append(req_holder["headers"].get("authorization"))
        self.assertEqual(cases[0], "Bearer fake-key")
        self.assertIsNone(cases[1])

    def test_http_error_becomes_llm_error(self):
        def raise_http(req, timeout=None):
            raise urllib.error.HTTPError("https://fake.example/v1/chat/completions",
                                         500, "oops", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=raise_http):
            with self.assertRaises(LLMError):
                self._client(attempts=1).complete("s", "u", key="k", max_tokens=10)

    def test_exception_text_has_no_url_or_key(self):
        secrets = ("https://fake.example", "fake.example", "sk-secret-123", "/v1")
        scenarios = [
            urllib.error.URLError("down"),
            urllib.error.HTTPError("https://fake.example/v1/chat/completions",
                                   401, "denied", {}, io.BytesIO(b"")),
            RuntimeError("weird"),
        ]
        for scenario in scenarios:
            with mock.patch("urllib.request.urlopen", side_effect=scenario):
                try:
                    self._client(api_key="sk-secret-123", attempts=2).complete(
                        "s", "u", key="k", max_tokens=10)
                except LLMError as exc:
                    text = str(exc)
                    for s in secrets:
                        self.assertNotIn(s, text)
                except Exception as exc:  # pragma: no cover
                    self.fail(f"non-LLMError escaped: {exc!r}")

    def test_malformed_response_raises_llm_error(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=_resp({"unexpected": True})):
            with self.assertRaises(LLMError):
                self._client(attempts=1).complete("s", "u", key="k", max_tokens=10)


def _capture(holder: dict):
    def _inner(req, timeout=None):
        holder["data"] = req.data
        holder["full_url"] = req.full_url
        holder["headers"] = {k.lower(): v for k, v in req.header_items()}
        # Request.add_unredirected_header items only materialize via Request header
        # access; include the explicit Authorization if set.
        auth = req.headers.get("Authorization") or req.get_header("Authorization")
        if auth:
            holder["headers"]["authorization"] = auth
        return _resp(_ok_payload())
    return _inner


class LoadEnvConfigTests(unittest.TestCase):
    def _write(self, text: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(text)
            return fh.name

    def test_parses_comments_and_blank_lines(self):
        path = self._write(
            "# a comment\n"
            "\n"
            "LLM_BASE_URL=https://fake.example/v1\n"
            "# another\n"
            "\n"
            "LLM_MODEL=fake-model\n"
        )
        cfg = load_env_config(path)
        self.assertEqual(cfg, {"LLM_BASE_URL": "https://fake.example/v1",
                               "LLM_MODEL": "fake-model"})

    def test_quoted_values_unquoted(self):
        path = self._write(
            'LLM_BASE_URL="https://fake.example/v1"\n'
            "LLM_API_KEY='sk-fake'\n"
        )
        cfg = load_env_config(path)
        self.assertEqual(cfg["LLM_BASE_URL"], "https://fake.example/v1")
        self.assertEqual(cfg["LLM_API_KEY"], "sk-fake")

    def test_unrecognized_keys_ignored(self):
        path = self._write("OTHER=x\nLLM_MODEL=m\n")
        self.assertEqual(load_env_config(path), {"LLM_MODEL": "m"})


if __name__ == "__main__":
    unittest.main()
