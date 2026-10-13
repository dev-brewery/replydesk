"""replydesk render: RunResult -> one standalone HTML page (ARCHITECTURE §2).

No JS, no external assets, inline CSS only. All user/model text is
HTML-escaped. NEEDS_HUMAN cards show the triage reason and no draft box (A3).
"""

import html
from datetime import date

from .draft import FALLBACK_LABEL
from .model import DraftResult, DraftSource, RunResult, TriageDecision, TriageCategory

__all__ = ["render_run", "escape_text"]

_SOURCE_LABELS = {
    DraftSource.MODEL: "MODEL",
    DraftSource.MODEL_RETRY: "MODEL RETRY",
    DraftSource.TEMPLATE: "TEMPLATE",
}

_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 46rem;
       padding: 0 1rem; color: #1c1c1c; background: #fafafa; }
h1 { font-size: 1.4rem; }
.banner { background: #fff8e1; border: 1px solid #e0c36a; padding: .6rem .9rem;
          border-radius: .4rem; margin-bottom: 1.2rem; }
.card { background: #fff; border: 1px solid #ddd; border-radius: .5rem;
        padding: 1rem 1.2rem; margin-bottom: 1.2rem; }
.stars { color: #c8860a; letter-spacing: .1em; }
.badge { display: inline-block; padding: .15rem .6rem; border-radius: 999px;
         font-size: .8rem; font-weight: 600; margin-left: .5rem; }
.badge-thank_you { background: #e3f4e3; color: #1d6a1d; }
.badge-fix_it { background: #e6eefb; color: #1c4c9c; }
.badge-needs_human { background: #fbe7e7; color: #a11d1d; }
.reason { color: #555; font-size: .9rem; }
.review-text { white-space: pre-wrap; }
.draft { margin-top: .8rem; }
.draft textarea { width: 100%; min-height: 5.5rem; font: inherit;
                  box-sizing: border-box; }
.meta { font-size: .8rem; color: #555; margin-top: .3rem; }
footer { color: #888; font-size: .85rem; margin-top: 2rem; }
"""


def escape_text(text: str) -> str:
    """HTML-escape untrusted text (reviews, drafts, notes)."""
    return html.escape(text, quote=True)


def _stars(stars: int) -> str:
    return "\N{BLACK STAR}" * stars + "\N{WHITE STAR}" * (5 - stars)


def _draft_card(draft: DraftResult) -> str:
    label = _SOURCE_LABELS[draft.source]
    status = "verified" if draft.verified else "NOT verified"
    notes = ""
    if draft.verifier_notes:
        notes = '<div class="meta">Verifier notes: {}</div>'.format(
            escape_text("; ".join(draft.verifier_notes)))
    return (
        '<div class="draft">'
        '<label for="draft-{rid}">{label} draft</label>'
        '<textarea id="draft-{rid}" readonly>{text}</textarea>'
        '<div class="meta">Source: {label} &middot; Verifier: {status}</div>'
        "{notes}</div>"
    ).format(
        rid=escape_text(draft.review_id),
        label=label,
        text=escape_text(draft.text),
        status=status,
        notes=notes,
    )


def _review_card(decision: TriageDecision,
                 drafts_by_review: dict[str, DraftResult]) -> str:
    review = decision.review
    parts = [
        "<div class=\"card\">",
        '<div><span class="stars">{}</span>'
        '<span class="badge badge-{cls}">{name}</span></div>'.format(
            escape_text(_stars(review.stars)),
            cls=escape_text(decision.category.value),
            name=escape_text(decision.category.value.replace("_", " ").upper()),
        ),
        "<p class=\"reason\">Reason: {}</p>".format(escape_text(decision.reason)),
        "<p class=\"review-text\">{}</p>".format(escape_text(review.text)),
    ]
    if decision.category is not TriageCategory.NEEDS_HUMAN:
        draft = drafts_by_review.get(review.review_id)
        if draft is not None:
            parts.append(_draft_card(draft))
    parts.append("</div>")
    return "".join(parts)


def render_run(run: RunResult, *, title: str = "replydesk", demo: bool = False) -> str:
    """Render a RunResult as one standalone HTML page."""
    drafts_by_review = {d.review_id: d for d in run.drafts}
    banner = ""
    if demo:
        banner = ('<div class="banner">This is a <strong>recorded offline run</strong>'
                  " built from demo fixtures &mdash; no live services were used."
                  "</div>")
    generated = escape_text(run.generated_on.isoformat()) if isinstance(
        run.generated_on, date) else escape_text(str(run.generated_on))
    cards = "".join(
        _review_card(decision, drafts_by_review) for decision in run.decisions)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>{title}</title><style>{css}</style></head><body>"
        "<h1>{title}</h1>{banner}"
        '<p class="meta">Business: {business} &middot; Generated: {generated}</p>'
        "{cards}"
        "<footer>replydesk &mdash; offline demo run</footer>"
        "</body></html>\n"
    ).format(
        title=escape_text(title),
        css=_CSS,
        banner=banner,
        business=escape_text(run.profile.name),
        generated=generated,
        cards=cards,
    )


# FALLBACK_LABEL must survive rendering verbatim (ARCHITECTURE §2 note); it is
# plain text with no HTML-special characters, and escaping must not alter it.
assert escape_text(FALLBACK_LABEL) == FALLBACK_LABEL
