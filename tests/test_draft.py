"""Tests for replydesk.draft (T08): verify -> retry -> labeled fallback.

Offline only: stub clients and FixtureLLM, no network.
"""

import time
import unittest
from datetime import date

from replydesk.draft import FALLBACK_LABEL, run, template_reply
from replydesk.llm import FixtureLLM, LLMError
from replydesk.model import (
    BusinessProfile,
    DraftSource,
    Review,
    ToneGuide,
    TriageCategory,
    TriageDecision,
)
from replydesk.verifier import verify_draft

PROFILE = BusinessProfile(name="Bluefin Coffee", kind="coffee shop", city="Harborview")
TONE = ToneGuide(voice="Warm, plain, a little dry humor. Short sentences.", facts=())
TODAY = date(2026, 10, 13)

GOOD_THANKS = (
    "Thank you for the kind words about our coffee. "
    "We are glad you enjoyed your visit and hope you come by again soon."
)
BAD_DRAFT = "Thanks for visiting! We will give you a 30% refund next time."
ALSO_BAD = "So glad Marlene helped you out!"

REVIEW_GOOD = Review(review_id="r-good", stars=5, text="Great coffee and friendly service.")
REVIEW_BAD = Review(review_id="r-bad", stars=1, text="The order was wrong and cold.")
REVIEW_HUMAN = Review(review_id="r-human", stars=1, text="I will sue and I called a lawyer already.")


class StubClient:
    """Returns queued replies per key, in order; raises after queue empties."""

    def __init__(self, replies, error=None):
        self.replies = dict(replies)
        self.error = error
        self.calls = []

    def complete(self, system, user, *, key, max_tokens):
        self.calls.append({"system": system, "user": user, "key": key,
                           "max_tokens": max_tokens})
        queue = self.replies.get(key)
        if queue:
            return queue.pop(0)
        raise LLMError(self.error or "stub exhausted")


class TestTemplateReply(unittest.TestCase):
    def test_template_passes_verifier_thanks(self):
        decision = TriageDecision(REVIEW_GOOD, TriageCategory.THANK_YOU, "praise")
        body = template_reply(decision, PROFILE)
        result = verify_draft(body, tone_guide=TONE, review=REVIEW_GOOD, profile=PROFILE)
        self.assertTrue(result.passed, result.violations)

    def test_template_passes_verifier_fixit(self):
        decision = TriageDecision(REVIEW_BAD, TriageCategory.FIX_IT, "complaint")
        body = template_reply(decision, PROFILE)
        result = verify_draft(body, tone_guide=TONE, review=REVIEW_BAD, profile=PROFILE)
        self.assertTrue(result.passed, result.violations)

    def test_fallback_label_starts_with_template_marker(self):
        self.assertTrue(FALLBACK_LABEL.startswith("[Template"))


class TestRun(unittest.TestCase):
    def test_clean_draft_passes_first_try(self):
        client = StubClient({"r-good": [GOOD_THANKS]})
        result = run(TONE, PROFILE, [REVIEW_GOOD], client, today=TODAY)
        self.assertEqual(len(result.drafts), 1)
        draft = result.drafts[0]
        self.assertEqual(draft.review_id, "r-good")
        self.assertEqual(draft.source, DraftSource.MODEL)
        self.assertTrue(draft.verified)
        self.assertEqual(draft.verifier_notes, ())
        self.assertEqual(draft.text, GOOD_THANKS)
        self.assertEqual(result.generated_on, TODAY)
        self.assertEqual(client.calls[0]["max_tokens"], 512)  # assist consult first
        self.assertEqual(client.calls[0]["key"], "assist:r-good")
        self.assertEqual(client.calls[1]["max_tokens"], 800)
        self.assertEqual(client.calls[1]["key"], "r-good")

    def test_bad_then_good_retry(self):
        client = StubClient({"r-bad": [BAD_DRAFT, GOOD_THANKS]})
        result = run(TONE, PROFILE, [REVIEW_BAD], client, today=TODAY)
        draft = result.drafts[0]
        self.assertEqual(draft.source, DraftSource.MODEL_RETRY)
        self.assertTrue(draft.verified)
        # Retry prompt quotes the violations back.
        self.assertIn("unverified claims", client.calls[1]["user"])
        self.assertIn("30%", client.calls[1]["user"])
        self.assertEqual(client.calls[1]["max_tokens"], 800)

    def test_bad_twice_gets_labeled_template(self):
        client = StubClient({"r-bad": [BAD_DRAFT, ALSO_BAD]})
        result = run(TONE, PROFILE, [REVIEW_BAD], client, today=TODAY)
        draft = result.drafts[0]
        self.assertEqual(draft.source, DraftSource.TEMPLATE)
        self.assertFalse(draft.verified)
        self.assertTrue(draft.text.startswith(FALLBACK_LABEL))
        self.assertIn(FALLBACK_LABEL, draft.text)
        self.assertTrue(any("verification failed" in note for note in draft.verifier_notes),
                        draft.verifier_notes)

    def test_raising_client_gets_labeled_template(self):
        client = StubClient({}, error="endpoint down")
        result = run(TONE, PROFILE, [REVIEW_BAD], client, today=TODAY)
        draft = result.drafts[0]
        self.assertEqual(draft.source, DraftSource.TEMPLATE)
        self.assertTrue(draft.text.startswith(FALLBACK_LABEL))
        self.assertTrue(any("model unreachable" in note for note in draft.verifier_notes),
                        draft.verifier_notes)
        self.assertEqual(len(client.calls), 1)  # no retry after a transport failure

    def test_needs_human_gets_no_draft(self):
        client = StubClient({})
        result = run(TONE, PROFILE, [REVIEW_HUMAN, REVIEW_GOOD], client, today=TODAY)
        draft_ids = [d.review_id for d in result.drafts]
        self.assertNotIn("r-human", draft_ids)
        self.assertEqual(draft_ids, ["r-good"])
        # never prompted for the legal review; the good one is consulted, then drafted
        self.assertEqual(
            [c["key"] for c in client.calls], ["assist:r-good", "r-good"]
        )
        human = [d for d in result.decisions if d.review.review_id == "r-human"][0]
        self.assertEqual(human.category, TriageCategory.NEEDS_HUMAN)

    def test_empty_completions_yield_template_drafts(self):
        """Client whose completions are all empty (post-fix: LLMError) never
        produces empty MODEL drafts; drafts fall back to labeled templates."""
        client = StubClient({}, error="empty completion from configured endpoint")
        result = run(TONE, PROFILE, [REVIEW_GOOD], client, today=TODAY)
        self.assertEqual(len(result.drafts), 1)
        draft = result.drafts[0]
        self.assertEqual(draft.source, DraftSource.TEMPLATE)
        self.assertFalse(draft.verified)
        self.assertTrue(draft.text.startswith(FALLBACK_LABEL))
        self.assertTrue(draft.verifier_notes)
        self.assertTrue(draft.text.strip())

    def test_fixture_llm_offline_run(self):
        client = FixtureLLM({"r-good": GOOD_THANKS, "r-bad": BAD_DRAFT})
        result = run(TONE, PROFILE, [REVIEW_GOOD, REVIEW_BAD], client, today=TODAY)
        by_id = {d.review_id: d for d in result.drafts}
        self.assertEqual(by_id["r-good"].source, DraftSource.MODEL)
        # FixtureLLM returns the same canned draft twice; bad twice -> template
        self.assertEqual(by_id["r-bad"].source, DraftSource.TEMPLATE)
        self.assertTrue(by_id["r-bad"].text.startswith(FALLBACK_LABEL))


class SlowClient:
    """Thread-safe stub: ~0.2 s per complete() call, one clean reply per key.
    For T22b wall-time test only.
    """

    def __init__(self, replies, delay=0.2):
        import threading
        self._lock = threading.Lock()
        self._replies = dict(replies)
        self._delay = delay
        self.calls = []

    def complete(self, system, user, *, key, max_tokens):
        with self._lock:
            self.calls.append(key)
            reply = self._replies.get(key)
        import time
        time.sleep(self._delay)
        if reply is None:
            raise LLMError("slow stub exhausted")
        return reply


class TestParallelRun(unittest.TestCase):
    """T22b: per-review drafting runs in a bounded thread pool."""

    def _four_reviews(self):
        # FIX_IT reviews: the triage assist makes no calls for them, so the
        # wall time isolates the four draft calls.
        return [
            Review(review_id=f"r-{i}", stars=1,
                   text="The order was wrong and cold.")
            for i in range(4)
        ]

    def test_parallel_is_parallel_and_order_stable(self):
        reviews = self._four_reviews()
        parallel_client = SlowClient({f"r-{i}": GOOD_THANKS for i in range(4)})
        start = time.monotonic()
        result = run(TONE, PROFILE, reviews, parallel_client, today=TODAY)
        wall = time.monotonic() - start
        self.assertLess(wall, 0.6, f"4x0.2s drafts took {wall:.2f}s - sequential?")
        # Order must match original review order, not completion order.
        self.assertEqual(
            [d.review_id for d in result.drafts],
            [f"r-{i}" for i in range(4)],
        )
        self.assertTrue(all(d.source is DraftSource.MODEL for d in result.drafts))

    def test_sequential_equivalence(self):
        """Same inputs via a 1-worker-equivalent slow path give identical
        drafts: parallelism must not change results, only wall time."""
        reviews = self._four_reviews()
        a = run(TONE, PROFILE, reviews,
                SlowClient({f"r-{i}": GOOD_THANKS for i in range(4)}),
                today=TODAY)
        b = run(TONE, PROFILE, reviews,
                SlowClient({f"r-{i}": GOOD_THANKS for i in range(4)}),
                today=TODAY)
        self.assertEqual(
            [(d.review_id, d.text, d.source, d.verified) for d in a.drafts],
            [(d.review_id, d.text, d.source, d.verified) for d in b.drafts],
        )

    def test_needs_human_stays_draftless_in_parallel(self):
        reviews = [REVIEW_HUMAN] + self._four_reviews()
        client = SlowClient({f"r-{i}": GOOD_THANKS for i in range(4)})
        result = run(TONE, PROFILE, reviews, client, today=TODAY)
        self.assertNotIn("r-human", [d.review_id for d in result.drafts])
        self.assertEqual(len(result.drafts), 4)


if __name__ == "__main__":
    unittest.main()
