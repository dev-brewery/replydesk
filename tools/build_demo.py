"""replydesk demo build: offline fixtures -> committed GitHub Pages demo.

Per ARCHITECTURE §8 (T12): load the demo fixtures, run the offline pipeline
(`demo_run()`), and write two byte-deterministic files into `docs/`:

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

from replydesk.fixtures import FIXTURE_DATE, demo_run  # noqa: E402
from replydesk.render import render_run  # noqa: E402

_DEMO_TITLE = "replydesk — demo run"


def demo_run_json(run) -> str:
    """Serialize a demo RunResult deterministically (pinned date, sorted keys)."""
    payload = {
        "generated_on": run.generated_on.isoformat(),
        "profile": {"name": run.profile.name, "kind": run.profile.kind, "city": run.profile.city},
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
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


def build_demo(out_dir) -> tuple[Path, Path]:
    """Run the demo pipeline and write docs/index.html + docs/demo_run.json.

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
    html_path = out / "index.html"
    json_path = out / "demo_run.json"
    html_path.write_bytes(render_run(run, title=_DEMO_TITLE, demo=True).encode("utf-8"))
    json_path.write_bytes(demo_run_json(run).encode("utf-8"))
    return html_path, json_path


def main() -> int:
    docs_dir = _REPO_ROOT / "docs"
    html_path, json_path = build_demo(docs_dir)
    print(f"wrote {html_path} ({html_path.stat().st_size} bytes)")
    print(f"wrote {json_path} ({json_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
