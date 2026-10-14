"""A5 fact-grounding check: every fact token in a draft must trace to a source.

Pure and deterministic (regex + sets, stdlib only). Numbers, capitalized names,
and commitment/policy phrases in the draft must appear (case-insensitive) in the
source texts: tone guide voice + facts, review text, profile fields, star rating.
Commitments are sanctioned only by the SAME commitment word appearing in a source.
"""

import re
from dataclasses import dataclass

from .model import BusinessProfile, Review, ToneGuide

# Commitment / policy trigger words (lowercase). A draft occurrence is sanctioned
# only if the SAME word also appears in a source text.
COMMITMENT_WORDS = (
    "we'll", "we will", "promise", "guarantee", "refund", "discount", "free",
    "on the house", "voucher", "coupon", "comp", "replace", "remake", "% off",
    "next time", "come back", "call us", "email us", "reach out", "stop by",
)

# Capitalized tokens that are sentence-initial courtesy words, not names.
NAME_STOPLIST = {
    "i", "i'm", "we", "we're", "thanks", "thank", "hi", "hello", "please",
    "sorry", "ok", "okay", "hey", "yes", "no", "so", "and", "but", "if",
    "the", "a", "an", "it", "this", "that", "you", "your", "our", "my",
    "he", "she", "they", "what", "when", "where", "why", "how", "hope",
    "glad", "happy", "great", "good", "wow", "oh", "dear", "sincerely",
}

_NUMBER_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:am|pm|%|percent)?"   # digits, clock times, percents
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|"
    r"hundred|half|dozen)\b",
    re.IGNORECASE,
)

_NAME_RE = re.compile(r"\b[A-Z][a-z']*\b")

_COMMITMENT_RES = tuple(
    (w, re.compile(r"\b" + re.escape(w).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE))
    for w in COMMITMENT_WORDS
)


def _sources(tone_guide: ToneGuide, review: Review, profile: BusinessProfile) -> str:
    return "\n".join(
        [
            tone_guide.voice,
            "\n".join(tone_guide.facts),
            review.text,
            str(review.stars),
            profile.name,
            profile.kind,
            profile.city,
        ]
    )


def _trace_number(token: str, sources_lower: str) -> bool:
    # Token must appear as a standalone token: '9' does not trace to '9am'.
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(token)}(?![0-9A-Za-z])", sources_lower) is not None


def _trace_name(token: str, sources_lower: str) -> bool:
    return token.lower() in sources_lower


def _find_commitments(text: str) -> list[str]:
    """Longest-match first so 'on the house' isn't also reported as 'free' etc."""
    found: list[tuple[int, str]] = []
    spans: list[tuple[int, int]] = []
    for word, rx in _COMMITMENT_RES:
        for m in rx.finditer(text):
            if not any(s <= m.start() and m.end() <= e for s, e in spans):
                spans.append((m.start(), m.end()))
                found.append((m.start(), word))
    return [w for _, w in sorted(found)]


@dataclass(frozen=True)
class Verification:
    passed: bool
    violations: tuple[str, ...]


def verify_draft(
    draft_text: str,
    *,
    tone_guide: ToneGuide,
    review: Review,
    profile: BusinessProfile,
) -> Verification:
    """Check that numbers, names, and commitments in the draft trace to sources."""
    if not draft_text or not draft_text.strip():
        # An empty draft must never pass vacuously (defense in depth).
        return Verification(passed=False, violations=("empty draft",))
    sources = _sources(tone_guide, review, profile)
    sources_lower = sources.lower()
    violations: list[str] = []

    for m in _NUMBER_RE.finditer(draft_text):
        token = m.group(0).strip()
        if not _trace_number(token, sources_lower):
            violations.append(f"untraceable number: '{token}'")

    # Commitments first, so names inside matched commitment phrases
    # ("We" in "We'll") aren't double-reported.
    commitment_spans: list[tuple[int, int]] = []
    for word, rx in _COMMITMENT_RES:
        for m in rx.finditer(draft_text):
            if not any(s <= m.start() and m.end() <= e for s, e in commitment_spans):
                commitment_spans.append((m.start(), m.end()))
                if word not in sources_lower:
                    shown = m.group(0).lower()
                    violations.append(f"untraceable commitment: '{shown}'")

    for m in _NAME_RE.finditer(draft_text):
        if any(s <= m.start() and m.end() <= e for s, e in commitment_spans):
            continue
        token = m.group(0)
        if token.lower() in NAME_STOPLIST:
            continue
        if not _trace_name(token, sources_lower):
            violations.append(f"untraceable name: '{token}'")

    return Verification(passed=not violations, violations=tuple(violations))


__all__ = ["Verification", "verify_draft"]
