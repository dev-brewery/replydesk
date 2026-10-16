"""T15: refresh canned drafts from a real model run (online).

Runs the demo fixtures through draft.run with a real HttpLLM built from
load_env_config('.env') and writes every verifier-checked outcome back to
replydesk/fixtures/demo/canned_drafts.json:

- per non-human review_id: the final draft text (MODEL / MODEL_RETRY). If an
  outcome is TEMPLATE (model failed verification on both attempts), the
  existing hand-authored canned draft is kept for that id and reported.
- per assist consult: `assist:{review_id}` entries with the model's
  `category|reason` line (real consult outcomes replace canned ones).

The endpoint URL and API key are never printed or written anywhere.
Offline determinism is untouched: the committed fixtures stay the single
input to demo_run(); this tool only re-records them.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from replydesk.draft import run as draft_run  # noqa: E402
from replydesk.fixtures import FIXTURE_DATE, load_demo_fixtures  # noqa: E402
from replydesk.llm import HttpLLM, LLMError, load_env_config  # noqa: E402
from replydesk.model import DraftSource, TriageCategory  # noqa: E402

ENV_PATH = REPO / ".env"
CANNED_PATH = REPO / "replydesk" / "fixtures" / "demo" / "canned_drafts.json"
DEMO_DIR = REPO / "replydesk" / "fixtures" / "demo"


class _RecordingClient:
    """Wraps a client and records the final returned text per key."""

    def __init__(self, inner):
        self._inner = inner
        self.outputs: dict[str, str] = {}

    def complete(self, system, user, *, key, max_tokens):
        text = self._inner.complete(system, user, key=key, max_tokens=max_tokens)
        self.outputs[key] = text  # retry overwrites: final call wins
        return text


def main() -> int:
    config = load_env_config(str(ENV_PATH))
    for name in ("LLM_BASE_URL", "LLM_MODEL"):
        if name not in config:
            print(f"missing {name} in .env; cannot refresh", file=sys.stderr)
            return 1
    client = _RecordingClient(HttpLLM(
        base_url=config["LLM_BASE_URL"],
        model=config["LLM_MODEL"],
        api_key=config.get("LLM_API_KEY", ""),
    ))

    profile, tone_guide, reviews, canned, _provenance = load_demo_fixtures(DEMO_DIR)
    result = draft_run(tone_guide, profile, reviews, client, today=FIXTURE_DATE)

    updated = dict(canned)
    kept_canned: list[str] = []
    written: dict[str, str] = {}

    for draft in result.drafts:
        rid = draft.review_id
        if draft.source in (DraftSource.MODEL, DraftSource.MODEL_RETRY):
            updated[rid] = draft.text
            written[rid] = draft.source.name
        else:
            kept_canned.append(rid)  # TEMPLATE: keep the hand-authored draft

    assist_flips: list[str] = []
    for key, text in client.outputs.items():
        if key.startswith("assist:"):
            updated[key] = " ".join(text.split())
            rid = key[len("assist:"):]
            decision = next(d for d in result.decisions if d.review.review_id == rid)
            if decision.category is TriageCategory.FIX_IT:
                assist_flips.append(rid)

    with open(CANNED_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(updated, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")

    print(f"wrote {CANNED_PATH.relative_to(REPO)}")
    for rid in sorted(written):
        print(f"  {rid}: {written[rid]}")
    for rid in kept_canned:
        print(f"  {rid}: TEMPLATE outcome -> kept existing hand-authored canned draft")
    print(f"  assist entries refreshed: {sorted(k for k in updated if k.startswith('assist:'))}")
    if assist_flips:
        print(f"  assist flipped to fix-it: {sorted(assist_flips)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LLMError, FileNotFoundError) as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
