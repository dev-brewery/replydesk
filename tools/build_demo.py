"""replydesk demo build: offline fixtures -> committed GitHub Pages demo.

Per ARCHITECTURE §8 (T12, rehomed T22d): load the demo fixtures, run the
offline pipeline (`demo_run()`), and write two byte-deterministic files into
`docs/demo/`:

- `index.html`     — self-contained page via `render_run(demo=True)`: inline
                     CSS, no JS, no external assets, demo banner, pinned-date
                     stamp. Renders identically opened locally or on Pages.
- `demo_run.json`  — the committed fixture output (triage decisions + drafts)
                     for anyone auditing the demo.

Stdlib only, no network, no `.env` / local config reads. Determinism comes
from the pinned `FIXTURE_DATE`; re-running overwrites both files identically.
"""

import json
import sys
from pathlib import Path

# Make the repo root importable when run as `py tools/build_demo.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from replydesk import api
from replydesk.fixtures import FIXTURE_DATE, demo_run  # noqa: E402
from replydesk.render import render_run  # noqa: E402

_DEMO_TITLE = "replydesk — demo run"

# T22d: top nav injected into the recorded demo page — links back to the
# product, which now lives at the domain root. Deterministic: inserted at a
# fixed point, same bytes every run. The recorded demo page itself is
# render_run output; this wrapper is the only place the nav is added.
_NAV_HTML = (
    '<nav class="topnav">replydesk &mdash; '
    '<a href="/">&larr; back to replydesk</a></nav>'
)


def demo_run_json(run) -> str:
    """Serialize a demo RunResult deterministically (pinned date, sorted keys).

    Thin wrapper over ``replydesk.api.runresult_json`` plus the demo-only
    ``profile`` block, so the committed ``docs/`` output stays byte-identical.
    """
    payload = json.loads(api.runresult_json(run))
    payload["profile"] = {
        "name": run.profile.name,
        "kind": run.profile.kind,
        "city": run.profile.city,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


def build_demo(out_dir) -> tuple[Path, Path]:
    """Run the demo pipeline and write index.html + demo_run.json in out_dir
    (the product build targets docs/demo/).

    Returns the two written paths. Byte-deterministic: same fixtures in,
    same bytes out, across runs.
    """
    run = demo_run()
    if run.generated_on != FIXTURE_DATE:
        raise RuntimeError(
            f"demo run generated_on {run.generated_on} != pinned FIXTURE_DATE {FIXTURE_DATE}"
        )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = render_run(run, title=_DEMO_TITLE, demo=True)
    if "</head><body>" not in html:  # defensive: render_run contract change
        raise RuntimeError("render_run output missing '</head><body>' anchor")
    html = html.replace("</head><body>", "</head><body>" + _NAV_HTML, 1)
    html_path = out / "index.html"
    json_path = out / "demo_run.json"
    html_path.write_bytes(html.encode("utf-8"))
    json_path.write_bytes(demo_run_json(run).encode("utf-8"))
    return html_path, json_path


def main() -> int:
    demo_dir = _REPO_ROOT / "docs" / "demo"
    html_path, json_path = build_demo(demo_dir)
    print(f"wrote {html_path} ({html_path.stat().st_size} bytes)")
    print(f"wrote {json_path} ({json_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
