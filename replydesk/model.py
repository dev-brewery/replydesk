"""replydesk data model: enums and frozen dataclasses per ARCHITECTURE §2."""

from dataclasses import dataclass, fields
from datetime import date
from enum import Enum


class TriageCategory(Enum):
    THANK_YOU = "thank_you"
    FIX_IT = "fix_it"
    NEEDS_HUMAN = "needs_human"


class DraftSource(Enum):
    MODEL = "model"
    MODEL_RETRY = "model_retry"
    TEMPLATE = "template"


@dataclass(frozen=True)
class Review:
    review_id: str
    stars: int
    text: str


@dataclass(frozen=True)
class ToneGuide:
    voice: str
    facts: tuple[str, ...]


@dataclass(frozen=True)
class BusinessProfile:
    name: str
    kind: str
    city: str


@dataclass(frozen=True)
class TriageDecision:
    review: Review
    category: TriageCategory
    reason: str


@dataclass(frozen=True)
class DraftResult:
    review_id: str
    text: str
    source: DraftSource
    verified: bool
    verifier_notes: tuple[str, ...]


@dataclass(frozen=True)
class RunResult:
    profile: BusinessProfile
    tone_guide: ToneGuide
    decisions: tuple[TriageDecision, ...]
    drafts: tuple[DraftResult, ...]
    generated_on: date


def field_names(cls) -> tuple[str, ...]:
    """Exact dataclass field names, for drift-guard tests."""
    return tuple(f.name for f in fields(cls))
