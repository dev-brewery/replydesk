"""JSON generation bridge per ARCHITECTURE §12.

``app.py --serve-api`` runs a ``ThreadingHTTPServer`` exposing one endpoint,
``POST /api/draft``, that runs the existing online pipeline and returns the
serialized run. Stdlib only, loopback bind (the tunnel reaches it locally).

- Request caps are validated against the auditable ``CAPS`` table; violations
  return 400/413 JSON errors naming the cap. User text is never echoed.
- CORS: ``Access-Control-Allow-Origin`` echoes the request origin only if it is
  in ``ALLOWED_ORIGINS``; no wildcard, no credentials.
- The pipeline already degrades to labeled template drafts on model failure;
  the bridge never crashes on a run and never leaks endpoint/key material.
- Logs carry method, path, status, and review counts only — never review or
  tone text.
"""

import http.server
import json
import re
import time
from collections import deque
from http import HTTPStatus

from replydesk.accounts import DuplicateEmailError, user_json
from replydesk.draft import run as run_pipeline
from replydesk.model import BusinessProfile, Review
from replydesk.toneguide import ToneGuideError, parse_tone_guide

# One auditable table per ARCHITECTURE §2.
CAPS = {"MAX_BODY_BYTES": 262_144, "MAX_TONE_CHARS": 4_000, "MAX_REVIEWS": 20,
        "MAX_REVIEW_CHARS": 2_000, "MAX_PROFILE_CHARS": 60,
        "MAX_NAME_CHARS": 60, "MAX_EMAIL_CHARS": 254, "MAX_PASSWORD_CHARS": 1024}

# Signup rate limit (§13): 5 per IP per rolling 60-minute window, in-memory.
SIGNUP_RATE_LIMIT = 5
SIGNUP_WINDOW_SECONDS = 3600.0

# The SPA's email shape regex (docs/rd.js), mirrored server-side so both
# sides reject the same addresses with the same words.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def rate_clock() -> float:
    """Injectable monotonic clock for the signup rate limiter (tests monkeypatch)."""
    return time.monotonic()

# Browser-facing allowlist only (CORS constrains browsers, not scripts). The
# Pages fallback origin hosts the same SPA; loopback covers local verification.
ALLOWED_ORIGINS = (
    "https://replydeskhq.tech",
    "https://dev-brewery.github.io",
    "http://127.0.0.1",
)

_REVIEW_ID_RE = re.compile(r"^[a-z0-9-]{1,16}$")

_PROFILE_FIELDS = ("name", "kind", "city")

# The API is single-business; an omitted profile falls back to the same
# placeholder the local UI uses.
_DEFAULT_PROFILE = BusinessProfile(name="my business", kind="local shop", city="town")


def _caps_error(cap: str) -> str:
    return f"{cap} exceeded (cap: {CAPS[cap]})"


def runresult_json(run, note: str = "") -> str:
    """Serialize a RunResult for the API and demo output (sorted keys).

    The profile block is included (it is the caller's own input, echoed back);
    ``tools.build_demo.demo_run_json`` is therefore a thin alias. ``note``
    optionally adds an explanatory note (e.g. degradation reason).
    """
    payload = {
        "generated_on": run.generated_on.isoformat(),
        "profile": {
            "name": run.profile.name,
            "kind": run.profile.kind,
            "city": run.profile.city,
        },
        "decisions": [
            {
                "review_id": d.review.review_id,
                "stars": d.review.stars,
                "category": d.category.value,
                "reason": d.reason,
            }
            for d in run.decisions
        ],
        "drafts": [
            {
                "review_id": d.review_id,
                "source": d.source.value,
                "verified": d.verified,
                "text": d.text,
                **(({"verifier_notes": list(d.verifier_notes)})
                   if d.verifier_notes else {}),
            }
            for d in run.drafts
        ],
    }
    if note:
        payload["note"] = note
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


class _RequestError(Exception):
    """A request that must be answered with a JSON error status."""

    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _validate_profile(raw) -> BusinessProfile:
    if raw is None:
        return _DEFAULT_PROFILE
    if not isinstance(raw, dict):
        raise _RequestError(HTTPStatus.BAD_REQUEST, "profile must be an object")
    values = {}
    for field in _PROFILE_FIELDS:
        value = raw.get(field, "")
        if not isinstance(value, str):
            raise _RequestError(HTTPStatus.BAD_REQUEST, "profile fields must be strings")
        if len(value) > CAPS["MAX_PROFILE_CHARS"]:
            raise _RequestError(
                HTTPStatus.BAD_REQUEST, _caps_error("MAX_PROFILE_CHARS"))
        values[field] = value or {"name": "my business", "kind": "local shop",
                                  "city": "town"}[field]
    return BusinessProfile(**values)


def _validate_reviews(raw) -> list[Review]:
    if not isinstance(raw, list) or not raw:
        raise _RequestError(HTTPStatus.BAD_REQUEST, "reviews must be a non-empty array")
    if len(raw) > CAPS["MAX_REVIEWS"]:
        raise _RequestError(HTTPStatus.BAD_REQUEST, _caps_error("MAX_REVIEWS"))
    reviews = []
    for item in raw:
        if not isinstance(item, dict):
            raise _RequestError(HTTPStatus.BAD_REQUEST,
                                "each review must be an object")
        review_id = item.get("review_id")
        if not isinstance(review_id, str) or not _REVIEW_ID_RE.match(review_id):
            raise _RequestError(
                HTTPStatus.BAD_REQUEST,
                "review_id must match ^[a-z0-9-]{1,16}$")
        stars = item.get("stars")
        if not isinstance(stars, int) or isinstance(stars, bool) \
                or not 1 <= stars <= 5:
            raise _RequestError(HTTPStatus.BAD_REQUEST,
                                "stars must be an integer 1-5")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise _RequestError(HTTPStatus.BAD_REQUEST, "text must be a non-empty string")
        if len(text) > CAPS["MAX_REVIEW_CHARS"]:
            raise _RequestError(HTTPStatus.BAD_REQUEST, _caps_error("MAX_REVIEW_CHARS"))
        reviews.append(Review(review_id=review_id, stars=stars, text=text))
    return reviews


def _parse_request(body: bytes):
    """Validate one /api/draft request body.

    Returns ``(tone_guide, profile, reviews)`` or raises ``_RequestError``.
    Pure request validation: independent of the model client, so a degraded
    server can still answer 400 for malformed input (A9: behavior must not
    depend on whether a local .env exists).
    """
    if len(body) > CAPS["MAX_BODY_BYTES"]:
        raise _RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            _caps_error("MAX_BODY_BYTES"))
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _RequestError(HTTPStatus.BAD_REQUEST, "malformed JSON")
    if not isinstance(payload, dict):
        raise _RequestError(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
    tone_text = payload.get("tone")
    if not isinstance(tone_text, str):
        raise _RequestError(HTTPStatus.BAD_REQUEST, "tone must be a string")
    if len(tone_text) > CAPS["MAX_TONE_CHARS"]:
        raise _RequestError(HTTPStatus.BAD_REQUEST, _caps_error("MAX_TONE_CHARS"))
    profile = _validate_profile(payload.get("profile"))
    reviews = _validate_reviews(payload.get("reviews"))
    try:
        tone_guide = parse_tone_guide(tone_text)
    except ToneGuideError:
        raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid tone guide")
    return tone_guide, profile, reviews


def handle_draft(client, body: bytes) -> tuple[HTTPStatus, str]:
    """Run the pipeline for one /api/draft request body.

    Returns ``(status, json_text)``. Never raises; any unexpected pipeline
    failure becomes a 500 naming only the failure class.
    """
    try:
        tone_guide, profile, reviews = _parse_request(body)
        run = run_pipeline(tone_guide, profile, reviews, client,
                           today=profile_date())
        return HTTPStatus.OK, runresult_json(run)
    except _RequestError as exc:
        return exc.status, json.dumps({"error": exc.message}) + "\n"
    except Exception as exc:  # defensive: never crash, never leak details
        return (HTTPStatus.INTERNAL_SERVER_ERROR,
                json.dumps({"error": f"internal error ({exc.__class__.__name__})"})
                + "\n")


def profile_date():
    from datetime import date

    return date.today()


class _ApiHandler(http.server.BaseHTTPRequestHandler):
    # Set by make_api_server; None means the online client could not be built
    # and every /api/draft answers 503. Auth routes degrade the same way when
    # the accounts store is None.
    client = None
    accounts = None
    # Per-server signup rate-limit state ({ip: deque[timestamps]}); reset on
    # restart by design (§13).
    signup_attempts = {}

    # -- auth helpers -------------------------------------------------------

    def _bearer_token(self) -> str | None:
        """Parse ``Authorization: Token <t>`` (scheme case-insensitive)."""
        header = self.headers.get("Authorization") or ""
        parts = header.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "token":
            return None
        token = parts[1].strip()
        if not token or len(token) > 64:
            return None
        return token

    def _client_ip(self) -> str:
        # Last X-Forwarded-For value: Caddy appends the address it observed,
        # and only Caddy can reach the unpublished container port (§13).
        xff = self.headers.get("X-Forwarded-For")
        if xff:
            last = xff.split(",")[-1].strip()
            if last:
                return last
        return str(self.client_address[0])

    def _signup_rate_limited(self, ip: str) -> bool:
        attempts = type(self).signup_attempts
        cutoff = rate_clock() - SIGNUP_WINDOW_SECONDS
        seen = attempts.get(ip)
        if seen is None:
            seen = attempts[ip] = deque()
        while seen and seen[0] <= cutoff:
            seen.popleft()
        if len(seen) >= SIGNUP_RATE_LIMIT:
            return True
        seen.append(rate_clock())
        return False

    def _send_empty(self, status: HTTPStatus,
                    *, cors_origin: str | None = None) -> None:
        self.send_response(status)
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _auth_error(self, status: HTTPStatus, message: str, origin) -> None:
        self._send_json(status, json.dumps({"error": message}) + "\n",
                        cors_origin=origin)
        self._log(status)

    def _require_account_store(self, origin):
        if self.accounts is None:
            # Drain the small auth body so the client can read the 503
            # instead of hitting a reset mid-upload.
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if 0 < length <= 10 * CAPS["MAX_BODY_BYTES"]:
                while length > 0:
                    chunk = self.rfile.read(min(length, 65536))
                    if not chunk:
                        break
                    length -= len(chunk)
            self._auth_error(HTTPStatus.SERVICE_UNAVAILABLE,
                             "service unavailable", origin)
            return None
        return self.accounts

    def _auth_json_body(self, origin):
        """Read and parse one auth POST body, or send the error and return None."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._auth_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length",
                             origin)
            return None
        if length > CAPS["MAX_BODY_BYTES"]:
            self.close_connection = True
            self._auth_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                             _caps_error("MAX_BODY_BYTES"), origin)
            return None
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._auth_error(HTTPStatus.BAD_REQUEST, "malformed JSON", origin)
            return None
        if not isinstance(payload, dict):
            self._auth_error(HTTPStatus.BAD_REQUEST, "body must be a JSON object",
                             origin)
            return None
        return payload

    def _handle_auth_post(self, origin) -> None:
        if self.path == "/api/auth/signup":
            self._auth_signup(origin)
        elif self.path == "/api/auth/login":
            self._auth_login(origin)
        elif self.path == "/api/auth/logout":
            self._auth_logout(origin)
        else:
            self._auth_error(HTTPStatus.NOT_FOUND, "not found", origin)

    def _auth_signup(self, origin) -> None:
        accounts = self._require_account_store(origin)
        if accounts is None:
            return
        ip = self._client_ip()
        if self._signup_rate_limited(ip):
            self._auth_error(
                HTTPStatus.TOO_MANY_REQUESTS,
                "Too many sign-ups from this address. Try again later.", origin)
            return
        payload = self._auth_json_body(origin)
        if payload is None:
            return
        try:
            name, email, password = _validate_signup(payload)
            user = accounts.create_user(name, email, password)
        except _RequestError as exc:
            self._auth_error(exc.status, exc.message, origin)
            return
        except DuplicateEmailError as exc:
            self._auth_error(HTTPStatus.CONFLICT, str(exc), origin)
            return
        token = accounts.issue_session(user.id)
        self._send_json(HTTPStatus.CREATED,
                        json.dumps({"token": token, "user": user_json(user)},
                                   sort_keys=True) + "\n",
                        cors_origin=origin)
        self._log(HTTPStatus.CREATED)

    def _auth_login(self, origin) -> None:
        accounts = self._require_account_store(origin)
        if accounts is None:
            return
        payload = self._auth_json_body(origin)
        if payload is None:
            return
        email = payload.get("email")
        password = payload.get("password")
        user = None
        if isinstance(email, str) and isinstance(password, str):
            user = accounts.authenticate(email, password)
        if user is None:
            # One generic message: no account enumeration.
            self._auth_error(HTTPStatus.UNAUTHORIZED, "Wrong email or password.",
                             origin)
            return
        token = accounts.issue_session(user.id)
        self._send_json(HTTPStatus.OK,
                        json.dumps({"token": token, "user": user_json(user)},
                                   sort_keys=True) + "\n",
                        cors_origin=origin)
        self._log(HTTPStatus.OK)

    def _auth_logout(self, origin) -> None:
        accounts = self._require_account_store(origin)
        if accounts is None:
            return
        token = self._bearer_token()
        user = accounts.validate_session(token) if token else None
        if user is None:
            self._auth_error(HTTPStatus.UNAUTHORIZED, "Please sign in.", origin)
            return
        accounts.revoke_session(token)
        self._send_empty(HTTPStatus.NO_CONTENT, cors_origin=origin)
        self._log(HTTPStatus.NO_CONTENT)

    def _auth_me(self, origin) -> None:
        accounts = self._require_account_store(origin)
        if accounts is None:
            return
        token = self._bearer_token()
        user = accounts.validate_session(token) if token else None
        if user is None:
            self._auth_error(HTTPStatus.UNAUTHORIZED, "Please sign in.", origin)
            return
        self._send_json(HTTPStatus.OK,
                        json.dumps({"user": user_json(user)}, sort_keys=True)
                        + "\n",
                        cors_origin=origin)
        self._log(HTTPStatus.OK)

    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            return origin
        return None

    def _send_json(self, status: HTTPStatus, text: str,
                   *, cors_origin: str | None = None) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.end_headers()
        self.wfile.write(data)

    def _log(self, status: int, count: int | None = None) -> None:
        # Status + counts only; never request bodies or review text.
        extra = f" reviews={count}" if count is not None else ""
        print(f"api: {self.command} {self.path} -> {status}{extra}")

    def do_OPTIONS(self) -> None:
        origin = self._cors_origin()
        is_auth = self.path.startswith("/api/auth/")
        if not is_auth and self.path != "/api/draft":
            self._send_json(HTTPStatus.NOT_FOUND, '{"error": "not found"}\n')
            return
        # Route-aware preflight: only the auth routes may send Authorization.
        allow_headers = ("Content-Type, Authorization" if is_auth
                         else "Content-Type")
        allow_methods = "GET, POST, OPTIONS" if is_auth else "POST, OPTIONS"
        self.send_response(HTTPStatus.NO_CONTENT)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", allow_methods)
        self.send_header("Access-Control-Allow-Headers", allow_headers)
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self._log(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            # Cheap, authless liveness probe for the container healthcheck.
            self._send_json(HTTPStatus.OK, '{"ok": true}\n',
                            cors_origin=self._cors_origin())
            self._log(HTTPStatus.OK)
            return
        if self.path == "/api/auth/me":
            self._auth_me(self._cors_origin())
            return
        self._send_json(HTTPStatus.NOT_FOUND, '{"error": "not found"}\n')
        self._log(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        origin = self._cors_origin()
        if self.path.startswith("/api/auth/"):
            self._handle_auth_post(origin)
            return
        if self.path != "/api/draft":
            self._send_json(HTTPStatus.NOT_FOUND, '{"error": "not found"}\n')
            self._log(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0:
            self._send_json(HTTPStatus.BAD_REQUEST,
                            '{"error": "invalid Content-Length"}\n',
                            cors_origin=origin)
            return
        if length > CAPS["MAX_BODY_BYTES"]:
            # Drain (within a sane ceiling) so the client can read the 413
            # instead of hitting a connection abort mid-upload; beyond the
            # ceiling just close the connection.
            if length <= 10 * CAPS["MAX_BODY_BYTES"]:
                while length > 0:
                    chunk = self.rfile.read(min(length, 65536))
                    if not chunk:
                        break
                    length -= len(chunk)
            else:
                self.close_connection = True
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                json.dumps({"error": _caps_error("MAX_BODY_BYTES")}) + "\n",
                cors_origin=origin)
            self._log(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(length)
        if self.client is None:
            # Degraded: request validation still applies (malformed input
            # keeps its 400); only a draftable body gets the 503.
            try:
                _parse_request(body)
            except _RequestError as exc:
                self._send_json(exc.status,
                                json.dumps({"error": exc.message}) + "\n",
                                cors_origin=origin)
                self._log(exc.status)
                return
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE,
                            '{"error": "service unavailable"}\n',
                            cors_origin=origin)
            self._log(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        status, text = handle_draft(self.client, body)
        count = None
        if status == HTTPStatus.OK:
            try:
                count = len(json.loads(text)["decisions"])
            except (ValueError, KeyError):  # defensive
                count = None
        self._send_json(status, text, cors_origin=origin)
        self._log(status, count)

    def log_message(self, format: str, *args) -> None:  # silence default noise
        pass


def make_api_server(host: str, port: int, client,
                    accounts=None) -> http.server.ThreadingHTTPServer:
    """Build the bridge server.

    ``client=None`` starts degraded (drafts answer 503); ``accounts=None``
    leaves the auth routes at 503 while everything else is unchanged (§13).
    """
    handler = type("BoundApiHandler", (_ApiHandler,),
                   {"client": client, "accounts": accounts,
                    "signup_attempts": {}})
    return http.server.ThreadingHTTPServer((host, port), handler)


def _validate_signup(payload: dict) -> tuple[str, str, str]:
    """Validate a signup body; strings mirror the SPA verbatim (§11/§13)."""
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise _RequestError(HTTPStatus.BAD_REQUEST, "Please enter your name.")
    if len(name) > CAPS["MAX_NAME_CHARS"]:
        raise _RequestError(HTTPStatus.BAD_REQUEST,
                            _caps_error("MAX_NAME_CHARS"))
    raw_email = payload.get("email")
    if not isinstance(raw_email, str):
        raise _RequestError(HTTPStatus.BAD_REQUEST,
                            "Please enter a valid email address.")
    email = raw_email.strip().lower()
    if len(email) > CAPS["MAX_EMAIL_CHARS"]:
        raise _RequestError(HTTPStatus.BAD_REQUEST,
                            _caps_error("MAX_EMAIL_CHARS"))
    if not _EMAIL_RE.match(email):
        raise _RequestError(HTTPStatus.BAD_REQUEST,
                            "Please enter a valid email address.")
    password = payload.get("password")
    if not isinstance(password, str) or len(password) < 8:
        raise _RequestError(HTTPStatus.BAD_REQUEST,
                            "Password must be at least 8 characters.")
    if len(password) > CAPS["MAX_PASSWORD_CHARS"]:
        raise _RequestError(HTTPStatus.BAD_REQUEST,
                            _caps_error("MAX_PASSWORD_CHARS"))
    return name.strip(), email, password
