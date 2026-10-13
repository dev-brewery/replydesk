"""Tests for replydesk.triage — deterministic rules per ARCHITECTURE §4."""

import unittest

from replydesk.model import Review, TriageCategory
from replydesk.triage import RULE_TABLE, triage, triage_all


def r(stars: int, text: str, review_id: str = "r1") -> Review:
    return Review(review_id=review_id, stars=stars, text=text)


class NeedsHumanTests(unittest.TestCase):
    def test_one_star_refund_demand(self):
        d = triage(r(1, "I want my money back, this is unacceptable"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("refund-dispute", d.reason)

    def test_legal_threat_at_five_stars(self):
        d = triage(r(5, "Lovely place, but pay up or I will sue"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("legal", d.reason)

    def test_legal_group_patterns(self):
        for text in ("call my lawyer", "small claims court", "cease and desist letter"):
            with self.subTest(text=text):
                self.assertIs(triage(r(2, text)).category, TriageCategory.NEEDS_HUMAN)

    def test_safety_health(self):
        d = triage(r(2, "I got sick after eating here, went to the hospital"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("safety-health", d.reason)

    def test_personal_discrimination(self):
        d = triage(r(3, "The staff was RACIST to my friend"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("personal", d.reason)

    def test_personal_staff_by_name(self):
        d = triage(r(4, "Great food. I spoke to Dave about it."))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("personal", d.reason)

    def test_personal_staff_role_named_trade_roles(self):
        d = triage(r(3, "the tech named Dave was dismissive"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("personal", d.reason)

        d = triage(r(3, "the plumber named Marlene rushed the job"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("personal", d.reason)

        # lowercase generic role without a name is not personal
        d = triage(r(2, "spoke to the manager and nothing happened"))
        self.assertIs(d.category, TriageCategory.FIX_IT)

    def test_personal_bereavement(self):
        d = triage(r(2, "Came here after my mother passed, service was cold"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)
        self.assertIn("personal", d.reason)

    def test_needs_human_beats_complaint_words(self):
        d = triage(r(5, "Great, but if I don't get a refund I will sue"))
        self.assertIs(d.category, TriageCategory.NEEDS_HUMAN)


class FixItTests(unittest.TestCase):
    def test_plain_two_star(self):
        d = triage(r(2, "Meh experience, nothing worth writing home about"))
        self.assertIs(d.category, TriageCategory.FIX_IT)
        self.assertIn("2 stars", d.reason)

    def test_five_star_with_complaint_word_is_fix_it(self):
        d = triage(r(5, "Amazing! Only note: my order was late by a bit."))
        self.assertIs(d.category, TriageCategory.FIX_IT)
        self.assertIn("complaint", d.reason)

    def test_complaint_patterns(self):
        for text in ("it was broken", "never arrived", "place was dirty",
                     "I was overcharged", "wrong order given"):
            with self.subTest(text=text):
                self.assertIs(triage(r(5, text)).category, TriageCategory.FIX_IT)


class ThankYouTests(unittest.TestCase):
    def test_plain_five_star_thanks(self):
        d = triage(r(5, "Wonderful pastries, friendly service, will come again"))
        self.assertIs(d.category, TriageCategory.THANK_YOU)
        self.assertIn("thank-you", d.reason)

    def test_four_star_no_complaint(self):
        self.assertIs(triage(r(4, "Really solid coffee")).category,
                      TriageCategory.THANK_YOU)


class GeneralTests(unittest.TestCase):
    def test_reasons_are_non_empty_strings(self):
        reviews = [
            r(1, "refund now or I sue"),
            r(2, "food made me sick"),
            r(3, "racist staff"),
            r(4, "my toast was cold"),
            r(5, "absolutely delightful"),
        ]
        for d in triage_all(reviews):
            self.assertIsInstance(d.reason, str)
            self.assertTrue(d.reason)

    def test_every_group_and_star_fallthrough_reachable(self):
        categories = {cat for cat, _, _ in RULE_TABLE}
        self.assertEqual(categories, {TriageCategory.NEEDS_HUMAN, TriageCategory.FIX_IT})

    def test_triage_all_preserves_order_and_review(self):
        reviews = [r(5, "great"), r(1, "demand a refund"), r(2, "it was late")]
        decisions = triage_all(reviews)
        self.assertEqual([d.review for d in decisions], reviews)
        self.assertEqual([d.category for d in decisions],
                         [TriageCategory.THANK_YOU, TriageCategory.NEEDS_HUMAN,
                          TriageCategory.FIX_IT])


if __name__ == "__main__":
    unittest.main()
