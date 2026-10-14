"""Dedicated unit tests for the §5 triage assist (T14a).

The consult itself shipped with T11; this module pins its contract in
isolation, per ARCHITECTURE §5 as amended 2026-10-14: assist budget 512,
consulted exactly once per deterministic THANK_YOU star-fall-through,
`key="assist:<review_id>"`, one-way `fix-it` flip, everything else
(malformed output, needs-a-human token, LLMError, fixture miss) leaves the
deterministic decision standing. Offline only — recording stub clients.
"""

import unittest
from datetime import date

from replydesk.draft import TRIAGE_ASSIST_SYSTEM, run
from replydesk.llm import FixtureLLM, LLMError
from replydesk.model import (
    BusinessProfile,
    DraftSource,
    Review,
    ToneGuide,
    TriageCategory,
)

PROFILE = BusinessProfile(name="Bluefin Coffee", kind="coffee shop", city="Harborview")
TONE = ToneGuide(voice="Warm, plain, a little dry humor. Short sentences.", facts=())
TODAY = date(2026, 10, 14)

GOOD_THANKS = (
    "Thank you for the kind words about our coffee. "
    "We are glad you enjoyed your visit and hope you come by again soon."
)
GOOD_FIXIT = (
    "We are sorry the order came out wrong. "
    "We will check the ticket line and make it right on your next visit."
)

# 5 stars, no complaint pattern -> the star fall-through THANK_YOU.
TY_1 = Review(review_id="ty-1", stars=5, text="Great coffee and friendly service.")
TY_2 = Review(review_id="ty-2", stars=4, text="Lovely spot, will come back.")
# 1 star complaint -> FIX_IT deterministically.
FIX = Review(review_id="fix-1", stars=1, text="The order was wrong and cold.")
# Legal threat -> NEEDS_HUMAN deterministically.
HUMAN = Review(review_id="hum-1", stars=1, text="I will sue and I called a lawyer already.")


class RecordingStub:
    """Records every complete() call; serves queued replies by key, then raises."""

    def __init__(self, replies=None, error="stub exhausted"):
        self.replies = dict(replies or {})
        self.error = error
        self.calls = []

    def complete(self, system, user, *, key, max_tokens):
        self.calls.append({"system": system, "user": user, "key": key,
                           "max_tokens": max_tokens})
        queue = self.replies.get(key)
        if queue:
            return queue.pop(0)
        raise LLMError(self.error)

    def assist_calls(self, review_id):
        return [c for c in self.calls if c["key"] == f"assist:{review_id}"]


def _ty_decision(client, review=TY_1):
    """Run the pipeline over one thank-you review; return (decision, result)."""
    result = run(TONE, PROFILE, [review], client, today=TODAY)
    decisions = [d for d in result.decisions if d.review.review_id == review.review_id]
    assert len(decisions) == 1
    return decisions[0], result


class TestConsultWiring(unittest.TestCase):
    def test_consulted_exactly_once_with_key_and_budget(self):
        client = RecordingStub()
        decision, _ = _ty_decision(client)
        calls = client.assist_calls(TY_1.review_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["key"], "assist:ty-1")
        self.assertEqual(calls[0]["max_tokens"], 512)
        self.assertEqual(calls[0]["system"], TRIAGE_ASSIST_SYSTEM)
        self.assertEqual(calls[0]["user"], TY_1.text)
        # Deterministic decision unchanged (stub raises after recording).
        self.assertEqual(decision.category, TriageCategory.THANK_YOU)

    def test_fix_it_never_consulted(self):
        client = RecordingStub(replies={"fix-1": [GOOD_FIXIT]})
        _ = run(TONE, PROFILE, [FIX], client, today=TODAY)
        self.assertFalse([c for c in client.calls if c["key"].startswith("assist:")])
        self.assertTrue(client.calls)  # only draft calls, no consults

    def test_needs_human_never_consulted(self):
        client = RecordingStub()
        _ = run(TONE, PROFILE, [HUMAN], client, today=TODAY)
        self.assertEqual(client.calls, [])

    def test_one_consult_per_thank_you_review(self):
        client = RecordingStub()
        _ = run(TONE, PROFILE, [TY_1, TY_2], client, today=TODAY)
        self.assertEqual([c["key"] for c in client.calls if c["key"].startswith("assist:")],
                         ["assist:ty-1", "assist:ty-2"])


class TestFlip(unittest.TestCase):
    def test_well_formed_fix_it_flips_with_assist_reason(self):
        client = RecordingStub(replies={
            "assist:ty-1": ["fix-it|the review names a wrong order"],
            "ty-1": [GOOD_THANKS],
        })
        decision, result = _ty_decision(client)
        self.assertEqual(decision.category, TriageCategory.FIX_IT)
        self.assertEqual(decision.reason, "triage assist flip: the review names a wrong order")
        # The flipped review drafts with fix-it guidance.
        draft_calls = [c for c in client.calls if c["key"] == "ty-1"]
        self.assertEqual(len(draft_calls), 1)
        self.assertTrue(draft_calls[0]["user"].startswith("fix-it:"))
        draft = result.drafts[0]
        self.assertEqual(draft.review_id, "ty-1")
        self.assertEqual(draft.source, DraftSource.MODEL)
        self.assertTrue(draft.verified)

    def test_flip_reason_carries_model_line_in_template_fallback(self):
        client = RecordingStub(replies={"assist:ty-2": ["fix-it|cold food mentioned"]})
        decision, _ = _ty_decision(client, review=TY_2)
        self.assertEqual(decision.category, TriageCategory.FIX_IT)
        self.assertIn("cold food mentioned", decision.reason)
        self.assertIn("assist", decision.reason.lower())


class TestMalformedOutput(unittest.TestCase):
    def test_malformed_outputs_leave_decision_standing(self):
        cases = {
            "garbage": "this is not a classification at all",
            "empty": "",
            "whitespace": "   \n  ",
            "multi-line": "fix-it|first line\nsecond line",
            "needs-a-human token": "needs-a-human|escalate this one",
            "thank-you token": "thank-you|genuine thanks",
            "bare token": "fix-it",
            "missing reason": "fix-it|",
        }
        for name, output in cases.items():
            with self.subTest(case=name):
                client = RecordingStub(replies={"assist:ty-1": [output]})
                decision, _ = _ty_decision(client)
                self.assertEqual(decision.category, TriageCategory.THANK_YOU)
                self.assertEqual(
                    decision.reason,
                    "no rule matched; 5 stars >= 4 -> thank-you",
                )  # deterministic reason intact


class TestErrorsAndFixtures(unittest.TestCase):
    def test_raising_client_leaves_decision_standing(self):
        client = RecordingStub(error="endpoint down")
        decision, result = _ty_decision(client)
        self.assertEqual(decision.category, TriageCategory.THANK_YOU)
        # The run itself never blocks: the review still drafts (template fallback).
        self.assertEqual(len(result.drafts), 1)
        self.assertEqual(result.drafts[0].source, DraftSource.TEMPLATE)

    def test_fixturellm_serves_canned_assist_when_present(self):
        client = FixtureLLM({
            "assist:ty-1": "fix-it|mentions a wrong order",
            "ty-1": GOOD_FIXIT,
        })
        decision, _ = _ty_decision(client)
        self.assertEqual(decision.category, TriageCategory.FIX_IT)
        self.assertIn("wrong order", decision.reason)

    def test_fixturellm_miss_is_graceful(self):
        client = FixtureLLM({})
        decision, result = _ty_decision(client)
        self.assertEqual(decision.category, TriageCategory.THANK_YOU)
        self.assertEqual(len(result.drafts), 1)
        self.assertEqual(result.drafts[0].source, DraftSource.TEMPLATE)


if __name__ == "__main__":
    unittest.main()
