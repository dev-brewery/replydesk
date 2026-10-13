"""replydesk fixtures: pinned fixture date and demo fixture loader.

Per ARCHITECTURE §7: `FIXTURE_DATE` is pinned so all committed demo output is
byte-deterministic. `load_demo_fixtures` schema-validates a demo directory
(`demo_profile.json`, `tone_guide.md`, `reviews.json`, `canned_drafts.json`)
and returns typed objects. Offline only: this module never reads `.env` or
local config.
"""

import json
from datetime import date
from pathlib import Path

from ..model import BusinessProfile, Review, ToneGuide

FIXTURE_DATE = date(2026, 10, 12)  # pinned; all fixture review dates <= this

_REQUIRED_FILES = ("demo_profile.json", "tone_guide.md", "reviews.json", "canned_drafts.json")


class FixtureError(ValueError):
    """Raised when a demo fixture directory is missing or malformed."""


def _load_json(path: Path, what: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FixtureError(f"demo fixture directory missing {what}: {path}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FixtureError(f"{what} is not valid JSON ({path}): {exc}") from None


def _require(mapping, key, what: str):
    if not isinstance(mapping, dict) or key not in mapping:
        raise FixtureError(f"{what} is missing required key {key!r}")
    return mapping[key]


def _require_str(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FixtureError(f"{what} must be a non-empty string")
    return value


def load_demo_fixtures(demo_dir) -> tuple[BusinessProfile, ToneGuide, list[Review], dict[str, str]]:
    """Load and schema-validate a demo fixture directory.

    Returns (BusinessProfile, ToneGuide, list[Review], {review_id: canned_draft}).
    Raises FixtureError with a clear message on any malformed input.
    """
    directory = Path(demo_dir)
    if not directory.is_dir():
        raise FixtureError(f"demo fixture directory not found: {directory}")

    profile_raw = _load_json(directory / "demo_profile.json", "demo_profile.json")
    reviews_raw = _load_json(directory / "reviews.json", "reviews.json")
    canned_raw = _load_json(directory / "canned_drafts.json", "canned_drafts.json")
    try:
        tone_text = (directory / "tone_guide.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FixtureError(
            f"demo fixture directory missing tone_guide.md: {directory / 'tone_guide.md'}"
        ) from None
    except UnicodeDecodeError as exc:
        raise FixtureError(f"tone_guide.md is not valid UTF-8: {exc}") from None

    profile = BusinessProfile(
        name=_require_str(_require(profile_raw, "name", "demo_profile.json"), "demo_profile.json 'name'"),
        kind=_require_str(_require(profile_raw, "kind", "demo_profile.json"), "demo_profile.json 'kind'"),
        city=_require_str(_require(profile_raw, "city", "demo_profile.json"), "demo_profile.json 'city'"),
    )

    if not isinstance(reviews_raw, list) or not reviews_raw:
        raise FixtureError("reviews.json must be a non-empty JSON list")
    reviews = []
    for i, entry in enumerate(reviews_raw):
        what = f"reviews.json entry {i}"
        review_id = _require_str(_require(entry, "review_id", what), f"{what} 'review_id'")
        stars = _require(entry, "stars", what)
        if not isinstance(stars, int) or isinstance(stars, bool) or not 1 <= stars <= 5:
            raise FixtureError(f"{what} 'stars' must be an integer in 1..5")
        text = _require_str(_require(entry, "text", what), f"{what} 'text'")
        fixture_day = entry.get("date", FIXTURE_DATE)
        if isinstance(fixture_day, str):
            try:
                fixture_day = date.fromisoformat(fixture_day)
            except ValueError:
                raise FixtureError(f"{what} 'date' must be an ISO date (YYYY-MM-DD)") from None
        if not isinstance(fixture_day, date):
            raise FixtureError(f"{what} 'date' must be an ISO date (YYYY-MM-DD)")
        if fixture_day > FIXTURE_DATE:
            raise FixtureError(
                f"{what} 'date' {fixture_day.isoformat()} is after the pinned FIXTURE_DATE "
                f"{FIXTURE_DATE.isoformat()}"
            )
        reviews.append(Review(review_id=review_id, stars=stars, text=text))

    ids = [r.review_id for r in reviews]
    if len(ids) != len(set(ids)):
        raise FixtureError("reviews.json contains duplicate review_id values")

    if not isinstance(canned_raw, dict):
        raise FixtureError("canned_drafts.json must be a JSON object of review_id -> draft")
    canned: dict[str, str] = {}
    for key, draft in canned_raw.items():
        what = f"canned_drafts.json entry {key!r}"
        _require_str(key, "canned_drafts.json key")
        canned[key] = _require_str(draft, what)
    missing = set(ids) - set(canned)
    if missing:
        raise FixtureError(f"canned_drafts.json is missing drafts for review_ids: {sorted(missing)}")

    tone_guide = ToneGuide(voice=tone_text, facts=())
    return profile, tone_guide, reviews, canned
