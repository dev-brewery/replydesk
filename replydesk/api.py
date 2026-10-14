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
from http import HTTPStatus

from replydesk.draft import run as run_pipeline
from replydesk.model import BusinessProfile, Review
from replydesk.toneguide import ToneGuideError, parse_tone_guide

# One auditable table per ARCHITECTURE §2.
CAPS = {"MAX_BODY_BYTES": 262_144, "MAX_TONE_CHARS": 4_000, "MAX_REVIEWS": 20,
        "MAX_REVIEW_CHARS": 2_000, "MAX_PROFILE_CHARS": 60}

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


def handle_draft(client, body: bytes) -> tuple[HTTPStatus, str]:
    """Run the pipeline for one /api/draft request body.

    Returns ``(status, json_text)``. Never raises; any unexpected pipeline
    failure becomes a 500 naming only the failure class.
    """
    try:
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
    # and every /api/draft answers 503.
    client = None

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
        if self.path != "/api/draft":
            self._send_json(HTTPStatus.NOT_FOUND, '{"error": "not found"}\n')
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self._log(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        self._send_json(HTTPStatus.NOT_FOUND, '{"error": "not found"}\n')
        self._log(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/draft":
            self._send_json(HTTPStatus.NOT_FOUND, '{"error": "not found"}\n')
            self._log(HTTPStatus.NOT_FOUND)
            return
        origin = self._cors_origin()
        if self.client is None:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE,
                            '{"error": "service unavailable"}\n',
                            cors_origin=origin)
            self._log(HTTPStatus.SERVICE_UNAVAILABLE)
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


def make_api_server(host: str, port: int, client) -> http.server.ThreadingHTTPServer:
    """Build the bridge server; ``client=None`` starts degraded (all 503)."""
    handler = type("BoundApiHandler", (_ApiHandler,), {"client": client})
    return http.server.ThreadingHTTPServer((host, port), handler)
