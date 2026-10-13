"""Local web UI per ARCHITECTURE §2.

Stdlib ``http.server`` bound to the loopback address. Modes:

- offline (default): triage runs; drafts come from the labeled template path
  with an "offline mode" note. Never reads ``.env`` and never opens a socket.
- demo (``--demo``): the committed fixture run, read-only. Degrades with a
  clear message while the fixture set does not exist yet.
- online (``--online``): loads ``.env`` and drafts via ``HttpLLM``, with the
  labeled template fallback on any client error.
"""

import argparse
import http.server
import urllib.parse
from http import HTTPStatus

from replydesk.draft import run as run_pipeline
from replydesk.llm import HttpLLM, LLMError, load_env_config
from replydesk.model import BusinessProfile, Review, RunResult, ToneGuide
from replydesk.render import escape_text, render_run
from replydesk.toneguide import ToneGuideError, parse_tone_guide
from replydesk.triage import triage_all

DEFAULT_HOST = "127.0.0.1"  # loopback only; never a real hostname
DEFAULT_PORT = 8000

VOICE_PLACEHOLDER = "# Voice\nHow I talk to customers...\n\n# Facts I'll stand behind\n- we open at 7am"
REVIEWS_PLACEHOLDER = "5 | best coffee on the block\n2 | my order was cold"

_FORMAT_HINT = "One review per line: <code>5 | review text</code> (stars 1&ndash;5)."
_OFFLINE_NOTE = (
    "Offline mode: triage ran locally; replies below are labeled template "
    "drafts because no model client is configured."
)

# Profile placeholder for owner-pasted runs; the UI is single-business for now.
_DEFAULT_PROFILE = BusinessProfile(name="my business", kind="local shop", city="town")


class ReviewsFormatError(ValueError):
    """A review line is not 'stars | text' with stars in 1..5."""


def parse_reviews(text: str) -> list[Review]:
    """Parse '5 | review text' lines; blank lines are skipped."""
    reviews: list[Review] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        head, sep, body = line.partition("|")
        if not sep:
            raise ReviewsFormatError(
                f"line {lineno}: expected '5 | review text' (missing '|')"
            )
        stars = head.strip()
        if not stars.isdigit() or not 1 <= int(stars) <= 5:
            raise ReviewsFormatError(
                f"line {lineno}: rating {stars!r} is not a whole number from 1 to 5"
            )
        if not body.strip():
            raise ReviewsFormatError(f"line {lineno}: review text is empty")
        reviews.append(
            Review(review_id=f"r{len(reviews) + 1}", stars=int(stars), text=body.strip())
        )
    return reviews


class _OfflineClient:
    """Stand-in client for offline mode: every draft call falls back."""

    def complete(self, system: str, user: str, *, key: str, max_tokens: int) -> str:
        raise LLMError("offline mode: no model client configured (use --online)")


def _owner_run_html(tone_text: str, reviews_text: str, *, error: str = "",
                    offline_note: bool = False, run_result: RunResult | None = None) -> str:
    note_html = ""
    if offline_note:
        note_html = ('<div class="banner">{}</div>'.format(escape_text(_OFFLINE_NOTE)))
    if run_result is not None:
        results = render_run(run_result, title="replydesk results")
        # Re-render the form above the results by stitching the bodies.
        form = _form_html(tone_text, reviews_text, error="")
        return form.replace("</body>", note_html + results.split("<body>", 1)[1])
    return _form_html(tone_text, reviews_text, error=error) .replace(
        "</body>", note_html + "</body>")


_FORM_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:52rem;margin:2rem auto;"
    "padding:0 1rem;color:#222}"
    "textarea{width:100%;min-height:9rem;font:inherit}"
    "label{font-weight:600;display:block;margin-top:1rem}"
    ".hint{color:#666;font-size:.85rem}"
    ".error{color:#a00;font-weight:600}"
    ".banner{background:#fffbdd;border:1px solid #d9d26e;padding:.6rem 1rem;"
    "border-radius:.3rem;margin-top:1rem}"
    "button{margin-top:1rem;padding:.4rem 1.2rem;font:inherit}"
)


def _form_html(tone_text: str, reviews_text: str, *, error: str = "") -> str:
    error_html = ""
    if error:
        error_html = '<p class="error">{}</p>'.format(escape_text(error))
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>replydesk</title><style>{css}</style></head><body>"
        "<h1>replydesk</h1>"
        "<form method=\"post\" action=\"/run\">"
        '<label for="tone">Tone guide</label>'
        '<textarea id="tone" name="tone" placeholder="{ph_voice}">{tone}</textarea>'
        '<p class="hint">Use the headings <code># Voice</code> and '
        "<code># Facts I&#39;ll stand behind</code>.</p>"
        '<label for="reviews">Reviews</label>'
        '<textarea id="reviews" name="reviews" placeholder="{ph_rev}">{reviews}</textarea>'
        '<p class="hint">{hint}</p>'
        "{error}"
        "<button type=\"submit\">Draft replies</button>"
        "</form></body></html>\n"
    ).format(
        ph_voice=escape_text(VOICE_PLACEHOLDER),
        ph_rev=escape_text(REVIEWS_PLACEHOLDER),
        tone=escape_text(tone_text),
        reviews=escape_text(reviews_text),
        hint=_FORMAT_HINT,
        error=error_html,
        css=_FORM_CSS.replace("{", "{{").replace("}", "}}"),
    )


def _demo_unavailable_html(detail: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8"><title>replydesk</title></head>'
        "<body><h1>replydesk</h1>"
        '<div class="banner">Demo fixtures are not available yet ({}). '
        "They are written in a later task; use the default form until then."
        "</div></body></html>\n"
    ).format(escape_text(detail))


class _Handler(http.server.BaseHTTPRequestHandler):
    # Set by make_server: the LLM client for /run and whether to add the
    # offline-mode note. demo_mode serves the fixture run read-only.
    client = None
    offline_note = True
    demo_mode = False
    env_path = ".env"

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path != "/":
            self._send_html("<h1>404</h1>", HTTPStatus.NOT_FOUND)
            return
        if self.demo_mode:
            self._send_html(self._demo_html())
            return
        self._send_html(_form_html(tone_text="", reviews_text=""))

    def _demo_html(self) -> str:
        from replydesk import fixtures

        demo_run = getattr(fixtures, "demo_run", None)
        if demo_run is None:
            return _demo_unavailable_html("demo_run() not implemented yet")
        try:
            return render_run(demo_run(), title="replydesk demo", demo=True)
        except fixtures.FixtureError as exc:
            return _demo_unavailable_html(str(exc))

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_html("<h1>404</h1>", HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(
            self.rfile.read(length).decode("utf-8"), keep_blank_values=True
        )
        tone_text = form.get("tone", [""])[0]
        reviews_text = form.get("reviews", [""])[0]

        if self.demo_mode:
            self._send_html(self._demo_html())
            return
        try:
            tone_guide: ToneGuide = parse_tone_guide(tone_text)
        except ToneGuideError as exc:
            self._send_html(
                _form_html(tone_text, reviews_text, error=str(exc)),
                HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            reviews = parse_reviews(reviews_text)
        except ReviewsFormatError as exc:
            self._send_html(
                _form_html(tone_text, reviews_text, error=str(exc)),
                HTTPStatus.BAD_REQUEST,
            )
            return
        if not reviews:
            self._send_html(
                _form_html(tone_text, reviews_text, error="no reviews entered"),
                HTTPStatus.BAD_REQUEST,
            )
            return

        result = run_pipeline(
            tone_guide, _DEFAULT_PROFILE, reviews, self.client, today=_today()
        )
        page = _owner_run_html(
            tone_text, reviews_text, offline_note=self.offline_note, run_result=result
        )
        self._send_html(page)

    def log_message(self, format: str, *args) -> None:  # silence test noise
        pass


def _today():
    from datetime import date

    return date.today()


def make_server(host: str, port: int, *, client, offline_note: bool,
                demo_mode: bool, env_path: str = ".env") -> http.server.ThreadingHTTPServer:
    """Build the server with handler configuration baked in (for tests too)."""
    handler = type("BoundHandler", (_Handler,), {
        "client": client,
        "offline_note": offline_note,
        "demo_mode": demo_mode,
        "env_path": env_path,
    })
    return http.server.ThreadingHTTPServer((host, port), handler)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="replydesk local web UI")
    parser.add_argument("--demo", action="store_true",
                        help="serve the committed demo fixture run read-only")
    parser.add_argument("--online", action="store_true",
                        help="draft via the configured LLM (reads .env)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args(argv)

    if args.online:
        config = load_env_config(".env")
        client = HttpLLM(config["LLM_BASE_URL"], config["LLM_MODEL"],
                         api_key=config["LLM_API_KEY"])
        offline_note = False
    elif args.demo:
        client = _OfflineClient()  # demo run needs no client
        offline_note = False
    else:
        client = _OfflineClient()
        offline_note = True

    httpd = make_server(args.host, args.port, client=client,
                        offline_note=offline_note, demo_mode=args.demo)
    print(f"replydesk listening on http://{args.host}:{args.port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
