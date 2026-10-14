"""Drafting pipeline per ARCHITECTURE §2/§5/§6.

Triage first; NEEDS_HUMAN reviews get no draft. Everything else goes to the
LLM client with the §5 prompt, through the verifier, with exactly one retry
carrying the violations, then a clearly labeled template fallback. Offline
safe: the only network touch is the injected client.
"""

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .llm import LLMError
from .model import (
    BusinessProfile,
    DraftResult,
    DraftSource,
    Review,
    TriageCategory,
    TriageDecision,
    ToneGuide,
    RunResult,
)
from .triage import triage_all
from .verifier import verify_draft

FALLBACK_LABEL = "[Template reply - edit before posting]"

_THANK_YOU_GUIDANCE = (
    "thank-you: write warm thanks, echo one specific detail from the review"
)
_FIX_IT_GUIDANCE = (
    "fix-it: name the problem, own it, no excuses, offer only next steps the facts allow"
)

_SYSTEM_TEMPLATE = (
    "You ghostwrite review replies as the owner of {name}, a {kind} in {city}. "
    "Match this voice exactly: {voice} "
    "Facts you may use, and the only facts you may use: {facts}, plus anything "
    "the review itself says and the star rating. Never invent promises, discounts, "
    "names, policies, times or prices. 40-120 words. Plain text only - no markdown, "
    "no emoji unless the voice shows them, no sign-off unless the voice has one. "
    "Output only the reply."
)

_RETRY_NOTE = (
    "Your previous draft contained unverified claims: {violations}. "
    "Rewrite without them."
)

TRIAGE_ASSIST_SYSTEM = (
    "You triage customer reviews for a small business owner. Classify the review as "
    "either genuine thanks or a problem worth a substantive reply. Answer with exactly "
    "one line in the form 'category|reason', where category is 'thank-you' or 'fix-it' "
    "and the reason is one short clause. Use 'fix-it' whenever the review describes "
    "anything that went wrong or fell short."
)


def _apply_assist(client, decision: TriageDecision) -> TriageDecision:
    """One assist consult for a deterministic THANK_YOU decision.

    Only a well-formed 'fix-it|reason' flips (one-way, toward the cautious
    category). Malformed output or an LLMError leaves the deterministic
    decision unchanged; the assist never blocks or drafts. Stateless apart
    from the client, so safe to run concurrently.
    """
    try:
        output = client.complete(
            TRIAGE_ASSIST_SYSTEM,
            decision.review.text,
            key=f"assist:{decision.review.review_id}",
            max_tokens=512,
        )
    except LLMError:
        return decision
    stripped = output.strip()
    # Output contract is one line; anything multi-line is malformed.
    category, sep, reason = (
        stripped.partition("|") if stripped and "\n" not in stripped
        else ("", "", "")
    )
    if sep and reason.strip() and category.strip().lower() == "fix-it":
        return TriageDecision(
            review=decision.review,
            category=TriageCategory.FIX_IT,
            reason=f"triage assist flip: {reason.strip()}",
        )
    return decision


def _consult_assist(client, decisions: list[TriageDecision]) -> list[TriageDecision]:
    """§5 triage assist, pooled (T22c): one consult per deterministic
    THANK_YOU decision, executed concurrently with results collected in
    review order. Semantics identical to the sequential version.
    """
    adjusted: list[TriageDecision] = []
    targets: list[tuple[int, TriageDecision]] = []
    for index, decision in enumerate(decisions):
        if decision.category is TriageCategory.THANK_YOU:
            targets.append((index, decision))
            adjusted.append(decision)  # placeholder, replaced below
        else:
            adjusted.append(decision)
    if targets:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_apply_assist, client, decision)
                for _, decision in targets
            ]
            for (index, _), future in zip(targets, futures):
                adjusted[index] = future.result()
    return adjusted


def _system_prompt(tone_guide: ToneGuide, profile: BusinessProfile) -> str:
    return _SYSTEM_TEMPLATE.format(
        name=profile.name,
        kind=profile.kind,
        city=profile.city,
        voice=tone_guide.voice,
        facts=", ".join(tone_guide.facts) if tone_guide.facts else "(none)",
    )


def _user_prompt(decision: TriageDecision, *, retry_violations: tuple[str, ...] = ()) -> str:
    guidance = (
        _THANK_YOU_GUIDANCE
        if decision.category is TriageCategory.THANK_YOU
        else _FIX_IT_GUIDANCE
    )
    parts = [guidance, f"Rating: {decision.review.stars}/5", decision.review.text]
    if retry_violations:
        parts.append(_RETRY_NOTE.format(violations="; ".join(retry_violations)))
    return "\n".join(parts)


def template_reply(decision: TriageDecision, profile: BusinessProfile) -> str:
    """Safe fallback text: neutral strings + profile fields + review echo only.

    The returned body passes `verify_draft` (no label here; `run()` prepends
    `FALLBACK_LABEL` on fallback so the marker never trips the name check).
    """
    review = decision.review
    name = profile.name
    stars_word = "star" if review.stars == 1 else "stars"
    if decision.category is TriageCategory.THANK_YOU:
        body = (
            f"Thank you for the kind words about {name}. "
            f"We are glad you took the time to share this. "
            f"You said: \"{review.text}\" You gave this {review.stars} {stars_word}. "
            f"It means a lot to everyone here at {name} in {profile.city}."
        )
    else:
        body = (
            f"Thank you for telling us about this. "
            f"We are sorry your visit to {name} was not what it should have been. "
            f"This is what you shared: \"{review.text}\" You gave this {review.stars} {stars_word}. "
            f"A person at {name} reads every note like yours and will look into it."
        )
    return body


def _fallback(
    decision: TriageDecision,
    profile: BusinessProfile,
    *,
    notes: tuple[str, ...],
) -> DraftResult:
    return DraftResult(
        review_id=decision.review.review_id,
        text=f"{FALLBACK_LABEL} {template_reply(decision, profile)}",
        source=DraftSource.TEMPLATE,
        verified=False,
        verifier_notes=notes,
    )


def _draft_one(
    decision: TriageDecision,
    system: str,
    profile: BusinessProfile,
    client,
    tone_guide: ToneGuide,
) -> DraftResult:
    """Draft+verify+retry+fallback for a single review. Self-contained and
    stateless apart from the client, so it is safe to run concurrently.
    """
    review = decision.review
    try:
        text = client.complete(
            system, _user_prompt(decision), key=review.review_id, max_tokens=800
        )
    except LLMError as exc:
        return _fallback(
            decision, profile, notes=(f"model unreachable: {exc}",)
        )
    verification = verify_draft(
        text, tone_guide=tone_guide, review=review, profile=profile
    )
    if verification.passed:
        return DraftResult(
            review_id=review.review_id,
            text=text,
            source=DraftSource.MODEL,
            verified=True,
            verifier_notes=(),
        )
    # One retry, with the violations quoted back into the prompt.
    try:
        retry_text = client.complete(
            system,
            _user_prompt(decision, retry_violations=verification.violations),
            key=review.review_id,
            max_tokens=800,
        )
    except LLMError as exc:
        return _fallback(
            decision,
            profile,
            notes=(
                "verification failed: " + "; ".join(verification.violations),
                f"model unreachable on retry: {exc}",
            ),
        )
    retry_verification = verify_draft(
        retry_text, tone_guide=tone_guide, review=review, profile=profile
    )
    if retry_verification.passed:
        return DraftResult(
            review_id=review.review_id,
            text=retry_text,
            source=DraftSource.MODEL_RETRY,
            verified=True,
            verifier_notes=(),
        )
    return _fallback(
        decision,
        profile,
        notes=(
            "verification failed: " + "; ".join(retry_verification.violations),
        ),
    )


def run(
    tone_guide: ToneGuide,
    profile: BusinessProfile,
    reviews: Iterable[Review],
    client,
    *,
    today: date,
) -> RunResult:
    """Triage, then draft with verify -> one retry -> labeled fallback.

    Per-review drafting runs in a small thread pool (T22b); results are
    collected in original review order, so output is deterministic. The
    triage assist consults are pooled separately (T22c) and complete before
    the draft pool starts — never nested on one executor — keeping total
    in-flight requests ≤ ~8: it decides the guidance every prompt below
    depends on.
    """
    decisions = _consult_assist(client, triage_all(reviews))
    system = _system_prompt(tone_guide, profile)
    draftable = [
        d for d in decisions if d.category is not TriageCategory.NEEDS_HUMAN
    ]
    if draftable:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_draft_one, d, system, profile, client, tone_guide)
                for d in draftable
            ]
            drafts = [f.result() for f in futures]
    else:
        drafts = []

    return RunResult(
        profile=profile,
        tone_guide=tone_guide,
        decisions=tuple(decisions),
        drafts=tuple(drafts),
        generated_on=today,
    )


__all__ = [
    "FALLBACK_LABEL",
    "RunResult",
    "run",
    "template_reply",
]
