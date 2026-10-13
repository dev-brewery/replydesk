"""T11 acceptance: the committed demo fixture set drives a full offline run.

Loads `replydesk/fixtures/demo/`, runs `demo_run()` (FixtureLLM, no network),
and asserts the counts, verifier outcomes, needs-a-human handling, pinned date,
and the canned triage-assist outcomes (one flip, one confirm) per ARCHITECTURE
§5/§7.
"""

import json
import unittest
from datetime import date
from pathlib import Path

from replydesk import fixtures as fixtures_pkg
from replydesk.fixtures import FIXTURE_DATE, demo_run, load_demo_fixtures
from replydesk.model import DraftSource, TriageCategory

DEMO_DIR = Path(fixtures_pkg.__file__).resolve().parent / "demo"
NON_HUMAN_SOURCES = (DraftSource.MODEL, DraftSource.MODEL_RETRY)


class DemoFixtureSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = demo_run()
        cls.decisions = {d.review.review_id: d for d in cls.result.decisions}
        cls.drafts = {d.review_id: d for d in cls.result.drafts}

    def test_eight_decisions_and_pinned_date(self):
        self.assertEqual(len(self.result.decisions), 8)
        self.assertEqual(self.result.generated_on, FIXTURE_DATE)

    def test_every_non_human_review_has_a_verified_draft(self):
        self.assertEqual(len(self.result.drafts), 6)
        for decision in self.result.decisions:
            if decision.category is TriageCategory.NEEDS_HUMAN:
                self.assertNotIn(decision.review.review_id, self.drafts)
                continue
            draft = self.drafts[decision.review.review_id]
            self.assertTrue(draft.verified, decision.review.review_id)
            self.assertEqual(draft.verifier_notes, ())
            self.assertIn(draft.source, NON_HUMAN_SOURCES)

    def test_needs_a_human_reviews_carry_reasons(self):
        needs = [
            d for d in self.result.decisions if d.category is TriageCategory.NEEDS_HUMAN
        ]
        self.assertEqual(
            sorted(d.review.review_id for d in needs),
            ["human-legal", "human-refund"],
        )
        for decision in needs:
            self.assertIn("matched pattern", decision.reason)

    def test_assist_flips_a_thank_you_to_fix_it(self):
        flipped = self.decisions["ty-2"]
        self.assertIs(flipped.category, TriageCategory.FIX_IT)
        self.assertIn("assist", flipped.reason.lower())

    def test_assist_consult_confirms_a_thank_you(self):
        confirmed = self.decisions["ty-1"]
        self.assertIs(confirmed.category, TriageCategory.THANK_YOU)
        self.assertIn("no rule matched", confirmed.reason)

    def test_reviews_exercise_every_group_and_respect_the_pinned_date(self):
        raw = json.loads((DEMO_DIR / "reviews.json").read_text(encoding="utf-8"))
        self.assertEqual(len(raw), 8)
        categories = {
            "ty-1": TriageCategory.THANK_YOU,
            "ty-2": TriageCategory.FIX_IT,      # assist flip
            "ty-3": TriageCategory.THANK_YOU,
            "fx-1": TriageCategory.FIX_IT,
            "fx-2": TriageCategory.FIX_IT,
            "fx-3": TriageCategory.FIX_IT,
            "human-legal": TriageCategory.NEEDS_HUMAN,
            "human-refund": TriageCategory.NEEDS_HUMAN,
        }
        for entry in raw:
            self.assertEqual(
                self.decisions[entry["review_id"]].category,
                categories[entry["review_id"]],
                entry["review_id"],
            )
            self.assertLessEqual(
                date.fromisoformat(entry["date"]), FIXTURE_DATE
            )

    def test_canned_drafts_carry_assist_entries_for_every_thank_you(self):
        canned = json.loads(
            (DEMO_DIR / "canned_drafts.json").read_text(encoding="utf-8")
        )
        for review_id, decision in self.decisions.items():
            if decision.category is TriageCategory.THANK_YOU:
                self.assertIn(f"assist:{review_id}", canned)
                self.assertIn("|", canned[f"assist:{review_id}"])

    def test_loader_round_trip_on_the_committed_set(self):
        profile, tone_guide, reviews, canned = load_demo_fixtures(DEMO_DIR)
        self.assertEqual(profile.name, "Ridgeline Plumbing")
        self.assertEqual(profile.kind, "plumbing contractor")
        self.assertEqual(profile.city, "Cedar Falls")
        self.assertEqual(len(reviews), 8)
        self.assertEqual(len(canned), 11)  # 8 drafts + 3 assist entries


if __name__ == "__main__":
    unittest.main()
