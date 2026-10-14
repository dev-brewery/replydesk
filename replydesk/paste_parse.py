"""Owner paste parsing: manual '5 | text' lines or a raw reviews-page copy.

Per ARCHITECTURE §2 (T19). One entry point, `parse_paste`, accepts either
shape:

- Manual lines — the first non-blank line looks like ``5 | text``: the strict
  manual parser applies, behavior and errors unchanged (its single
  implementation lives here; ``app.py`` re-exports both names).
- Page copy — anything else: a heuristic, never-raising parse of a plain-text
  browser copy of a Google Business reviews dialog or a Yelp reviews page.
  This is parsing, not scraping: no network, no platform APIs.

Page mode anchors segments on a star rating (glyph run or conservative numeric
form), drops scaffolding (reviewer names, dates) and known noise (owner
responses, UI strings, friend/review counts) via the auditable pattern tables
below, and returns ``[]`` when fewer than one usable review parses. Dates are
parser input only and never reach a ``Review``; the pinned ``FIXTURE_DATE``
rules are untouched.
"""

import re

from .model import Review

# ---------------------------------------------------------------------------
# Manual mode (moved verbatim from app.py, T19).
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Page-copy mode: auditable pattern tables (module top, like triage.py).
# ---------------------------------------------------------------------------

# Star glyph runs. Full stars: ★ U+2605, ⭐ U+2B50. Empty: ☆ U+2606.
# A half marker (½) floors to the lower whole star by simply not counting.
_FULL_STAR_CHARS = "★\u2b50"
_GLYPH_RUN_RE = re.compile(rf"^[★☆⭐½\s]*[★][★☆⭐½\s]*$")
_HALF_STAR_RE = re.compile(r"[½\u00bd]")

# Conservative numeric forms: '4/5', '4 out of 5', 'Rated 4/5'. Whole numbers
# only, out of 5, so a score like '4.6' or '84/100' never anchors a segment.
_NUMERIC_ANCHOR_RE = re.compile(
    r"^\s*(?:rated\s+)?([1-5])\s*(?:/|out\s+of)\s*5\s*[.:)]?\s*$",
    re.IGNORECASE,
)

# Relative dates ('2 days ago', 'a week ago', 'just now').
_DATE_RE = re.compile(
    r"^(?:just\s+now|a\s+few\s+seconds\s+ago|(?:a|\d+)\s+"
    r"(?:second|minute|hour|day|week|month|year)s?\s+ago)$",
    re.IGNORECASE,
)

# Reviewer names: 2–4 title-case words, short, no digits — the next review's
# byline lands at the tail of the previous segment's text run, so it must be
# dropped there too. Legit review sentences rarely fit this shape.
_NAME_RE = re.compile(r"^(?:[A-Z][\w'.-]*\s+){1,3}[A-Z][\w'.-]*$")

# Calendar dates ('Oct 12', 'October 12', 'Oct 12, 2024', '12/10/2024').
_CALENDAR_DATE_RE = re.compile(
    r"^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"\d{1,2}(?:,?\s*\d{4})?|\d{1,2}/\d{1,2}/\d{2,4})$",
    re.IGNORECASE,
)

# Known noise, dropped wherever it appears: owner responses, UI strings,
# friend/review/photo counts, "N years/months with Google/Yelp" badges.
_NOISE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("owner-response", re.compile(r"(response\s+from\s+(the\s+)?(owner|business)|owner\s+responded)", re.I)),
    ("ui-like", re.compile(r"^(like|share|see\s+more|see\s+less|read\s+more|read\s+less|helpful|translate[^(]*(\([^)]*\))?)$", re.I)),
    ("ui-prompt", re.compile(r"^(share|embed|flag|helpful|order\s+online|get\s+directions|save|claim\s+this\s+business|suggest\s+an\s+edit|write\s+a\s+review|add\s+a\s+photo|not\s+helpful|mark\s+as\s+helpful)$", re.I)),
    ("elite-badge", re.compile(r"^elite\s+\d{4}$", re.I)),
    ("count", re.compile(r"^\d+[+\s]*(friends?|reviews?|photos?|contributions?|followers?)\b", re.I)),
    ("badge", re.compile(r"^\d+\s+(years?|months?)\s+on\s+(google|yelp)\b", re.I)),
    ("local-guide", re.compile(r"^(local\s+guide|\u00b7|\|)+", re.I)),
)


def _is_noise(line: str) -> bool:
    return any(p.search(line) for _, p in _NOISE_PATTERNS)


def _anchor_stars(line: str) -> int | None:
    """Stars if the line anchors a segment, else None. Halves floor down."""
    if _GLYPH_RUN_RE.match(line):
        full = sum(line.count(ch) for ch in _FULL_STAR_CHARS)
        if full:
            return max(1, min(5, full))
        return None  # glyph run with no full star: not a usable anchor
    m = _NUMERIC_ANCHOR_RE.match(line)
    if m:
        return int(m.group(1))
    return None


def _is_scaffolding(line: str) -> bool:
    """Date or reviewer-name lines, recognized then dropped."""
    line = line.strip()
    if _DATE_RE.match(line) or _CALENDAR_DATE_RE.match(line):
        return True
    return bool(len(line) <= 40 and _NAME_RE.match(line))


_MANUAL_FIRST_RE = re.compile(r"^\s*[1-9]\d*\s*\|")


def parse_paste(text: str) -> list[Review]:
    """Parse a paste as manual '5 | text' lines or a raw reviews-page copy.

    Manual mode when the first non-blank line matches 'N |' (strict behavior,
    errors unchanged). Page mode never raises; fewer than one usable review
    returns ``[]``.
    """
    if not text or not text.strip():
        return []
    first = next(line for line in text.splitlines() if line.strip())
    if _MANUAL_FIRST_RE.match(first):
        return parse_reviews(text)

    reviews: list[Review] = []
    stars: int | None = None
    body_lines: list[str] = []
    trailing = False

    def close_segment() -> None:
        nonlocal stars, body_lines, trailing
        if stars is not None:
            body = " ".join(part for part in
                            (" ".join(body_lines)).split())  # collapse whitespace
            if body:
                reviews.append(Review(review_id=f"p{len(reviews) + 1}",
                                      stars=stars, text=body))
        stars = None
        body_lines = []
        trailing = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        anchor = _anchor_stars(line)
        if anchor is not None:
            close_segment()
            stars = anchor
        elif stars is None:
            continue  # scaffolding/noise before the first anchor: dropped
        elif _is_scaffolding(line):
            continue
        elif _is_noise(line):
            trailing = True  # noise line: rest of segment (owner reply text,
            continue         # share prompts) is untrusted and dropped
        elif trailing:
            continue
        else:
            body_lines.append(line)
    close_segment()
    return reviews
