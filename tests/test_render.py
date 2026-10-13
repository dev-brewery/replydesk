"""Tests for replydesk.render: standalone HTML output (T09)."""

import unittest
from datetime import date

from replydesk.draft import FALLBACK_LABEL
from replydesk.model import (
    BusinessProfile,
    DraftResult,
    DraftSource,
    Review,
    RunResult,
    ToneGuide,
    TriageCategory,
    TriageDecision,
)
from replydesk.render import render_run


def _run(*, review_text: str = "Great coffee, friendly staff!",
         reason: str = "positive feedback",
         draft: DraftResult | None = None) -> RunResult:
    review = Review(review_id="r1", stars=5, text=review_text)
    decisions = (TriageDecision(
        review=review, category=TriageCategory.THANK_YOU, reason=reason),)
    drafts = (draft,) if draft is not None else ()
    return RunResult(
        profile=BusinessProfile(name="Corner Cup", kind="coffee shop", city="Springfield"),
        tone_guide=ToneGuide(voice="warm", facts=("oat milk",)),
        decisions=decisions,
        drafts=drafts,
        generated_on=date(2026, 10, 13),
    )


def _model_draft() -> DraftResult:
    return DraftResult(
        review_id="r1",
        text="Thanks so much for the kind words!",
        source=DraftSource.MODEL,
        verified=True,
        verifier_notes=(),
    )


class TestRenderRun(unittest.TestCase):
    def test_review_text_escaped(self):
        page = render_run(_run(review_text="<script>alert('x')</script>"))
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_draft_text_escaped(self):
        draft = DraftResult(
            review_id="r1", text="<img src=x onerror=alert(1)>",
            source=DraftSource.MODEL, verified=True, verifier_notes=())
        page = render_run(_run(draft=draft))
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x", page)

    def test_needs_human_card_no_textarea(self):
        review = Review(review_id="r2", stars=1, text="Never delivered my order.")
        decision = TriageDecision(
            review=review, category=TriageCategory.NEEDS_HUMAN,
            reason="refund request needs a person")
        draft = DraftResult(
            review_id="r2", text="sorry", source=DraftSource.MODEL,
            verified=True, verifier_notes=())
        run = RunResult(
            profile=BusinessProfile(name="Corner Cup", kind="coffee shop", city="Springfield"),
            tone_guide=ToneGuide(voice="warm", facts=()),
            decisions=(decision,), drafts=(draft,), generated_on=date(2026, 10, 13))
        page = render_run(run)
        self.assertIn("refund request needs a person", page)
        self.assertNotIn("<textarea", page)

    def test_thank_you_card_has_textarea(self):
        page = render_run(_run(draft=_model_draft()))
        self.assertIn("<textarea", page)
        self.assertIn("Thanks so much for the kind words!", page)

    def test_source_labels(self):
        sources = {
            DraftSource.MODEL: "MODEL",
            DraftSource.MODEL_RETRY: "MODEL RETRY",
            DraftSource.TEMPLATE: "TEMPLATE",
        }
        for source, label in sources.items():
            draft = DraftResult(
                review_id="r1", text="hi", source=source,
                verified=False, verifier_notes=("missing fact",))
            page = render_run(_run(draft=draft))
            self.assertIn(label, page)

    def test_template_label_verbatim(self):
        draft = DraftResult(
            review_id="r1", text=f"{FALLBACK_LABEL} You're welcome back anytime!",
            source=DraftSource.TEMPLATE, verified=False,
            verifier_notes=("offline template",))
        page = render_run(_run(draft=draft))
        self.assertIn(FALLBACK_LABEL, page)

    def test_verifier_status_and_notes(self):
        draft = DraftResult(
            review_id="r1", text="hi", source=DraftSource.MODEL,
            verified=False, verifier_notes=("unsupported claim",))
        page = render_run(_run(draft=draft))
        self.assertIn("NOT verified", page)
        self.assertIn("unsupported claim", page)
        ok = _model_draft()
        page_ok = render_run(_run(draft=ok))
        self.assertIn("verified", page_ok)

    def test_no_external_asset_links(self):
        page = render_run(_run(draft=_model_draft()), demo=True)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_demo_banner(self):
        self.assertIn("recorded offline run", render_run(_run(), demo=True))
        self.assertNotIn("recorded offline run", render_run(_run(), demo=False))

    def test_stars_and_badge(self):
        page = render_run(_run())
        self.assertIn("THANK YOU", page)
        self.assertIn("badge-thank_you", page)
        self.assertIn("★★★★★", page)

    def test_custom_title_escaped(self):
        page = render_run(_run(), title="<b>tt</b>")
        self.assertIn("&lt;b&gt;tt&lt;/b&gt;", page)
        self.assertNotIn("<title><b>", page)


if __name__ == "__main__":
    unittest.main()
