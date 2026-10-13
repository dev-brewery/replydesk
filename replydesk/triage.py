"""Deterministic triage rules per ARCHITECTURE §4.

Ordered rule groups, first match wins. NEEDS_HUMAN groups checked before
complaint patterns, which are checked before star rating — a false "safe" on
a legal threat is the worst failure mode, so the table below is the single
auditable source of truth.
"""

import re
from typing import Iterable

from .model import Review, TriageCategory, TriageDecision

STAFF_ROLES = (
    "waiter", "waitress", "barista", "cashier", "manager", "server", "clerk",
    "staffer", "tech", "technician", "plumber", "mechanic", "installer",
    "contractor", "electrician", "hvac", "driver", "rep", "agent", "employee",
    "worker",
)
STAFF_ROLE_NAMED_PATTERN = (
    r"(?:the )?(?:" + "|".join(STAFF_ROLES) + r") named [A-Z][a-z]+"
)



# Lowercase regexes, matched case-insensitively against the review text.
# Group order IS the priority order; within a group, pattern order decides
# which pattern name lands in the reason.
RULE_TABLE: tuple[tuple[TriageCategory, str, tuple[str, ...]], ...] = (
    (
        TriageCategory.NEEDS_HUMAN,
        "legal",
        (
            "lawyer",
            "attorney",
            r"\bsue\b",
            "suing",
            r"\bcourt\b",
            "legal action",
            "small claims",
            "cease and desist",
        ),
    ),
    (
        TriageCategory.NEEDS_HUMAN,
        "safety-health",
        (
            "food poisoning",
            "sick after",
            "got sick",
            "illness",
            "injury",
            "injured",
            "ambulance",
            r"\ber\b",
            "hospital",
            "allergic reaction",
            "health department",
            "hazard",
            "blood",
            "glass in",
            "hair in my food",
            "mold",
        ),
    ),
    (
        TriageCategory.NEEDS_HUMAN,
        "refund-dispute",
        (
            "refund",
            "money back",
            "charged twice",
            "double charged",
            "chargeback",
            "dispute the charge",
            "credit card dispute",
        ),
    ),
    (
        TriageCategory.NEEDS_HUMAN,
        "personal",
        (
            "discriminat",
            "racist",
            "sexist",
            "homophobic",
            "harass",
            "assault",
            "my mother passed",
            "funeral",
            # staff member referenced by a capitalized name
            r"spoke to [A-Z][a-z]+",
            STAFF_ROLE_NAMED_PATTERN,
        ),
    ),
    (
        TriageCategory.FIX_IT,
        "complaint",
        (
            "broken",
            "cold",
            "late",
            "rude",
            "wrong order",
            "never arrived",
            "dirty",
            "overcharged",
            "ignored",
            "cancelled",
        ),
    ),
)


# Patterns that reference capitalization (staff names) must be matched
# case-sensitively, so they are skipped for the IGNORECASE pass.
# Patterns that reference capitalization (staff names) must be matched
# case-sensitively, so they are skipped for the IGNORECASE pass.
CASE_SENSITIVE = (r"spoke to [A-Z][a-z]+", STAFF_ROLE_NAMED_PATTERN,)


def _match(text: str, pattern: str) -> bool:
    if pattern in CASE_SENSITIVE:
        return re.search(pattern, text) is not None
    return re.search(pattern, text, re.IGNORECASE) is not None


def triage(review: Review) -> TriageDecision:
    """Triage one review deterministically; first match wins."""
    for category, group, patterns in RULE_TABLE:
        for pattern in patterns:
            if _match(review.text, pattern):
                return TriageDecision(
                    review=review,
                    category=category,
                    reason=f"{group}: matched pattern '{pattern}'",
                )
    # Fall through: star rating decides. >= 4 is thank-you, <= 3 fix-it.
    if review.stars >= 4:
        return TriageDecision(
            review=review,
            category=TriageCategory.THANK_YOU,
            reason=f"no rule matched; {review.stars} stars >= 4 -> thank-you",
        )
    return TriageDecision(
        review=review,
        category=TriageCategory.FIX_IT,
        reason=f"no rule matched; {review.stars} stars <= 3 -> fix-it",
    )


def triage_all(reviews: Iterable[Review]) -> list[TriageDecision]:
    """Triage every review, in input order."""
    return [triage(r) for r in reviews]
