"""LLM clients: LLMClient protocol, HttpLLM, FixtureLLM, .env config loader.

HttpLLM speaks OpenAI-compatible /chat/completions over urllib.request with a
300 s timeout, temperature 0.3, explicit max_tokens, and at most 3 transport
attempts. Endpoint URLs and keys never appear in exception text. Offline code
paths never touch load_env_config; FixtureLLM does zero network.
"""

import json
import urllib.error
import urllib.request
from typing import Mapping, Protocol, runtime_checkable


class LLMError(Exception):
    """Any transport or protocol failure after final retry."""


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, key: str, max_tokens: int) -> str:
        ...


class FixtureLLM:
    """Offline client: returns canned completions looked up by `key` (review_id)."""

    def __init__(self, mapping: Mapping[str, str]):
        self._mapping = dict(mapping)

    def complete(self, system: str, user: str, *, key: str, max_tokens: int) -> str:
        if key not in self._mapping:
            raise LLMError(
                f"FixtureLLM: no canned completion for key {key!r}; "
                f"available keys: {sorted(self._mapping)}"
            )
        return self._mapping[key]


class HttpLLM:
    """OpenAI-compatible /chat/completions client over urllib.request."""

    def __init__(self, base_url: str, model: str, api_key: str = "",
                 timeout: float = 300.0, attempts: int = 3):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._attempts = attempts

    def complete(self, system: str, user: str, *, key: str, max_tokens: int) -> str:
        body = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            # OpenAI convention merges extra_body fields into the TOP LEVEL of
            # the JSON body; sending them nested makes servers ignore them.
            "thinking": {"type": "enabled", "value": "low"},
        }).encode("utf-8")

        last_exc: Exception | None = None
        for _ in range(self._attempts):
            try:
                return self._one_call(body)
            except Exception as exc:  # transport or protocol failure
                last_exc = exc
        raise LLMError(
            f"LLM call failed after {self._attempts} attempts "
            f"against configured endpoint (key={key!r}): {last_exc}"
        )

    def _one_call(self, body: bytes) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            f"{self._base_url}/chat/completions", data=body,
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Swallow the body; never let the endpoint URL or key leak.
            raise LLMError(f"HTTP {exc.code} from configured endpoint") from None
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("malformed response from configured endpoint") from None
        if not content or not content.strip():
            # Empty content in an otherwise-OK response is retryable (thinking
            # consumed the budget); never return an empty completion.
            raise LLMError("empty completion from configured endpoint")
        return content


def load_env_config(env_path: str) -> dict:
    """Parse an .env-style file: KEY=value lines, # comments, blank lines allowed.

    Recognizes LLM_BASE_URL, LLM_MODEL, LLM_API_KEY. Quoted values are unquoted.
    Only online mode calls this.
    """
    wanted = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
    config: dict = {}
    with open(env_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if name in wanted and value != "":
                config[name] = value
    return config
