"""T02: construct every model type; assert frozen-ness and exact field names."""

import dataclasses
import unittest
from datetime import date

from replydesk.model import (
    BusinessProfile,
    DraftResult,
    DraftSource,
    Review,
    RunResult,
    TriageCategory,
    TriageDecision,
    ToneGuide,
    field_names,
)


class TestEnums(unittest.TestCase):
    def test_triage_category_members(self):
        self.assertEqual(
            {m.name for m in TriageCategory},
            {"THANK_YOU", "FIX_IT", "NEEDS_HUMAN"},
        )

    def test_draft_source_members(self):
        self.assertEqual(
            {m.name for m in DraftSource},
            {"MODEL", "MODEL_RETRY", "TEMPLATE"},
        )


class TestFieldNames(unittest.TestCase):
    def test_exact_field_names(self):
        expected = {
            Review: ("review_id", "stars", "text"),
            ToneGuide: ("voice", "facts"),
            BusinessProfile: ("name", "kind", "city"),
            TriageDecision: ("review", "category", "reason"),
            DraftResult: ("review_id", "text", "source", "verified", "verifier_notes"),
            RunResult: (
                "profile", "tone_guide", "decisions", "drafts", "generated_on",
            ),
        }
        for cls, names in expected.items():
            self.assertEqual(field_names(cls), names, cls.__name__)
            self.assertTrue(dataclasses.is_dataclass(cls), cls.__name__)

    def test_all_frozen(self):
        for cls in (
            Review, ToneGuide, BusinessProfile, TriageDecision,
            DraftResult, RunResult,
        ):
            self.assertTrue(
                cls.__dataclass_params__.frozen, f"{cls.__name__} not frozen"
            )


class TestConstruction(unittest.TestCase):
    def build_run_result(self) -> RunResult:
        review = Review(review_id="r1", stars=5, text="Great coffee.")
        profile = BusinessProfile(name="Demo Cafe", kind="coffee shop", city="Springville")
        tone = ToneGuide(voice="Warm and brief.", facts=("we open at 7am",))
        decision = TriageDecision(
            review=review, category=TriageCategory.THANK_YOU, reason="positive"
        )
        draft = DraftResult(
            review_id="r1",
            text="Thanks so much!",
            source=DraftSource.MODEL,
            verified=True,
            verifier_notes=(),
        )
        return RunResult(
            profile=profile,
            tone_guide=tone,
            decisions=(decision,),
            drafts=(draft,),
            generated_on=date(2026, 10, 12),
        )

    def test_construct_every_type(self):
        result = self.build_run_result()
        self.assertEqual(result.profile.name, "Demo Cafe")
        self.assertEqual(result.decisions[0].category, TriageCategory.THANK_YOU)
        self.assertEqual(result.drafts[0].source, DraftSource.MODEL)
        self.assertEqual(result.generated_on, date(2026, 10, 12))

    def test_frozen_assignment_raises(self):
        result = self.build_run_result()
        review = result.decisions[0].review
        draft = result.drafts[0]
        tone = result.tone_guide
        profile = result.profile
        with self.assertRaises(dataclasses.FrozenInstanceError):
            review.stars = 1
        with self.assertRaises(dataclasses.FrozenInstanceError):
            tone.voice = "x"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            profile.name = "x"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            draft.text = "x"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.generated_on = date(2026, 1, 1)


if __name__ == "__main__":
    unittest.main()
