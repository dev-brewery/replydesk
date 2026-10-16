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
import os
import re
import threading
import urllib.parse
from http import HTTPStatus

from replydesk.draft import run as run_pipeline
from replydesk.llm import HttpLLM, LLMError, load_env_config
from replydesk.model import BusinessProfile, Review, RunResult, ToneGuide
from replydesk.paste_parse import ReviewsFormatError, parse_reviews, parse_paste  # noqa: F401
from replydesk.render import escape_text, render_run
from replydesk.toneguide import ToneGuideError, parse_tone_guide
from replydesk.triage import triage_all

DEFAULT_HOST = "127.0.0.1"  # loopback only; never a real hostname
DEFAULT_PORT = 8000
DEFAULT_ACCOUNTS_DB = "data/accounts.db"


class LazyAccountStore:
    """AccountStore built on the first auth request, not at startup (§13).

    The path comes from the ACCOUNTS_DB environment variable only (never
    ``load_env_config`` — the container carries no .env file by design,
    lesson a3a1cb9). A server that never receives an auth request never
    touches the filesystem; the store creates a missing directory itself.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._store = None
        self._lock = threading.Lock()

    def _get(self):
        with self._lock:
            if self._store is None:
                from replydesk.accounts import AccountStore

                self._store = AccountStore(self._path)
            return self._store

    def __getattr__(self, name):
        return getattr(self._get(), name)

VOICE_PLACEHOLDER = "# Voice\nHow I talk to customers...\n\n# Facts I'll stand behind\n- we open at 7am"
REVIEWS_PLACEHOLDER = "5 | best coffee on the block\n2 | my order was cold"

_HEADER_STEPS = (
    "1. Paste your reviews &mdash; open your Google or Yelp reviews page, "
    "select all, copy, paste it here (or type lines like <code>5 | your "
    "review</code>). 2. Describe how you talk. 3. Copy out the replies you "
    "like."
)
_PRIVACY_LINE = ("No account. Nothing is stored. Nothing is posted without you. "
                 "Your words stay on this machine.")
_FORMAT_HINT = ("One review per line: <code>5 | review text</code> "
                "(stars 1&ndash;5) &mdash; or just paste the whole page above.")
_ZERO_FOUND_HINT = (
    "We could not find any reviews in that paste. Try typing manual lines "
    "instead, one per line, like: <code>5 | best coffee on the block</code>."
)
_OFFLINE_NOTE = (
    "Offline mode: triage ran locally; replies below are labeled template "
    "drafts because no model client is configured."
)
# Shown when --online was requested but the client could not be built; the run
# degrades to the same labeled template path, with the reason. Never contains
# endpoint URLs, keys, or file contents — only the failure class.
_ONLINE_DEGRADED_NOTE = (
    "Online mode unavailable ({}): triage ran locally; replies below are "
    "labeled template drafts."
)

# Profile placeholder for owner-pasted runs; the UI is single-business for now.
_DEFAULT_PROFILE = BusinessProfile(name="my business", kind="local shop", city="town")





class _OfflineClient:
    """Stand-in client for offline mode: every draft call falls back."""

    def complete(self, system: str, user: str, *, key: str, max_tokens: int) -> str:
        raise LLMError("offline mode: no model client configured (use --online)")


def _found_preview_html(reviews: list) -> str:
    """Found-reviews preview: rating + first line of each parsed review."""
    items = "".join(
        '<li>{} stars &mdash; {}</li>'.format(
            r.stars, escape_text(r.text.split(".")[0][:120] or r.text))
        for r in reviews
    )
    return (
        '<div class="preview"><p><strong>Found {} reviews from your paste'
        "&mdash; check them below.</strong></p><ul>{}</ul></div>"
    ).format(len(reviews), items)


def _owner_run_html(tone_text: str, reviews_text: str, *, error: str = "",
                    note_text: str = "", run_result: RunResult | None = None,
                    found: list | None = None) -> str:
    note_html = ""
    if found is not None:
        note_html += _found_preview_html(found)
    if note_text:
        note_html += ('<div class="banner">{}</div>'.format(escape_text(note_text)))
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
    ".privacy{background:#eef7ee;border:1px solid #9dc99d;padding:.6rem 1rem;"
    "border-radius:.3rem;margin-top:1rem;font-weight:600}"
    ".preview ul{margin:.4rem 0 0 1.2rem;padding:0;color:#444}"
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
        '<p class="steps">' + _HEADER_STEPS + "</p>"
        '<div class="privacy">' + _PRIVACY_LINE + "</div>"
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
        css=_FORM_CSS,  # braces in a format value are inserted verbatim
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
    # Set by make_server: the LLM client for /run and the banner note to show
    # on results ("" for none). demo_mode serves the fixture run read-only.
    client = None
    note_text = _OFFLINE_NOTE
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
        # Page paste first; manual 'N |' lines fall back to the strict
        # parser so their precise errors are kept.
        try:
            reviews = parse_paste(reviews_text)
        except ReviewsFormatError:
            reviews = []
        if not reviews:
            first = next((l for l in reviews_text.splitlines() if l.strip()), "")
            if re.match(r"^\s*\d+\s*\|", first):  # manual-shaped: keep precise errors
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
                _form_html(tone_text, reviews_text, error=_ZERO_FOUND_HINT),
                HTTPStatus.BAD_REQUEST,
            )
            return

        result = run_pipeline(
            tone_guide, _DEFAULT_PROFILE, reviews, self.client, today=_today()
        )
        page = _owner_run_html(
            tone_text, reviews_text, note_text=self.note_text, run_result=result,
            found=reviews,
        )
        self._send_html(page)

    def log_message(self, format: str, *args) -> None:  # silence test noise
        pass


def _today():
    from datetime import date

    return date.today()


def make_server(host: str, port: int, *, client, offline_note: bool = False,
                note_text: str = "", demo_mode: bool = False,
                env_path: str = ".env") -> http.server.ThreadingHTTPServer:
    """Build the server with handler configuration baked in (for tests too).

    ``offline_note=True`` is shorthand for the default offline banner;
    ``note_text`` overrides the banner text (used for degraded --online).
    """
    if offline_note and not note_text:
        note_text = _OFFLINE_NOTE
    handler = type("BoundHandler", (_Handler,), {
        "client": client,
        "note_text": note_text,
        "demo_mode": demo_mode,
        "env_path": env_path,
    })
    return http.server.ThreadingHTTPServer((host, port), handler)


def online_client(env_path: str):
    """Build the online client from an .env file.

    Returns ``(HttpLLM, None)`` on success, or ``(None, reason)`` on any
    configuration failure (missing file, missing/blank values, bad values).
    The reason names only the failure class — never file contents, URLs, or
    keys — so it is safe to print and render.
    """
    try:
        config = load_env_config(env_path)
    except OSError:
        return None, f"could not read {env_path}"
    missing = [name for name in ("LLM_BASE_URL", "LLM_MODEL")
               if not config.get(name)]
    if missing:
        return None, f"{env_path} is missing {', '.join(missing)}"
    try:
        return HttpLLM(
            config["LLM_BASE_URL"], config["LLM_MODEL"],
            api_key=config.get("LLM_API_KEY", ""),
        ), None
    except Exception as exc:  # defensive: bad values must not crash startup
        return None, f"invalid client configuration ({exc.__class__.__name__})"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="replydesk local web UI")
    parser.add_argument("--demo", action="store_true",
                        help="serve the committed demo fixture run read-only")
    parser.add_argument("--online", action="store_true",
                        help="draft via the configured LLM (reads .env)")
    parser.add_argument("--serve-api", action="store_true",
                        help="serve the /api/draft JSON bridge (implies online; "
                             "starts even if the client cannot be built, "
                             "answering 503)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--env", default=".env",
                        help="path to the .env file (online mode only)")
    args = parser.parse_args(argv)

    if args.serve_api:
        from replydesk.api import make_api_server

        client, degraded = online_client(args.env)
        if degraded is None:
            print("api mode: /api/draft drafting via the configured endpoint")
        else:
            print(f"api mode: online client unavailable ({degraded}); "
                  "every /api/draft will answer 503")
        # §13: ACCOUNTS_DB from the environment only — never load_env_config.
        accounts = LazyAccountStore(
            os.environ.get("ACCOUNTS_DB", DEFAULT_ACCOUNTS_DB))
        httpd = make_api_server(args.host, args.port, client, accounts=accounts)
        print(f"replydesk api listening on http://{args.host}:{args.port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
        return

    note_text = ""
    if args.online:
        client, degraded = online_client(args.env)
        if degraded is None:
            print("online mode: drafting via the configured endpoint")
        else:
            # Every --online startup failure degrades to the labeled template
            # path with a clear note; the app never crashes on configuration.
            print(f"online mode unavailable ({degraded}); "
                  "falling back to labeled template drafts")
            client = _OfflineClient()
            note_text = _ONLINE_DEGRADED_NOTE.format(degraded)
    elif args.demo:
        client = _OfflineClient()  # demo run needs no client
    else:
        client = _OfflineClient()
        note_text = _OFFLINE_NOTE

    httpd = make_server(args.host, args.port, client=client,
                        note_text=note_text, demo_mode=args.demo)
    print(f"replydesk listening on http://{args.host}:{args.port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":  # pragma: no cover
    main()
