"""Tests for replydesk.verifier (offline, per ARCHITECTURE §6)."""

import unittest

from replydesk.model import BusinessProfile, Review, ToneGuide
from replydesk.verifier import Verification, verify_draft

PROFILE = BusinessProfile(name="Bluebird Bakery", kind="bakery", city="Fairview")
REVIEW = Review(review_id="r1", stars=4, text="Marlene said the sourdough sold out by 9am.")
TONE = ToneGuide(
    voice="We keep it warm and plain. Thanks for coming by.",
    facts=("we honor refunds", "we open at 7am"),
)


def check(draft: str) -> Verification:
    return verify_draft(draft, tone_guide=TONE, review=REVIEW, profile=PROFILE)


class TestVerifier(unittest.TestCase):
    def test_all_traceable_passes(self):
        v = check("Thanks, Marlene! We open at 7am and we honor refunds.")
        self.assertTrue(v.passed)
        self.assertEqual(v.violations, ())

    def test_invented_number_fails(self):
        v = check("We open at 7am, not 30% later.")
        self.assertFalse(v.passed)
        self.assertIn("untraceable number: '30%'", v.violations)

    def test_unsanctioned_commitment_fails(self):
        v = check("We promise a voucher next visit.")
        self.assertFalse(v.passed)
        self.assertIn("untraceable commitment: 'promise'", v.violations)
        self.assertIn("untraceable commitment: 'voucher'", v.violations)

    def test_invented_name_fails(self):
        v = check("Thanks, Marlene! Alice will restock.")
        self.assertFalse(v.passed)
        self.assertIn("untraceable name: 'Alice'", v.violations)

    def test_sanctioned_commitment_passes(self):
        v = check("We honor refunds when we get it wrong.")
        self.assertTrue(v.passed)

    def test_review_sourced_name_passes(self):
        v = check("Marlene, the sourdough will be fresh.")
        self.assertTrue(v.passed)

    def test_profile_name_and_city_pass(self):
        v = check("Bluebird Bakery in Fairview opens at 7am.")
        self.assertTrue(v.passed)

    def test_star_number_traces(self):
        v = check("Thanks for the 4 stars!")
        self.assertTrue(v.passed)

    def test_invented_star_number_fails(self):
        v = check("Thanks for the 9 stars!")
        self.assertFalse(v.passed)
        self.assertIn("untraceable number: '9'", v.violations)

    def test_small_number_word_traces(self):
        tone = ToneGuide(voice="three words", facts=())
        review = Review(review_id="r2", stars=5, text="fine")
        v = verify_draft(
            "Thanks — back in three days.",
            tone_guide=tone, review=review, profile=PROFILE,
        )
        self.assertTrue(v.passed)

    def test_number_word_not_in_sources_fails(self):
        v = check("Come back for a free refill, all seven days.")
        self.assertFalse(v.passed)
        self.assertIn("untraceable number: 'seven'", v.violations)

    def test_violations_human_readable(self):
        v = check("Marlene, Alice saves you 30% with a coupon.")
        self.assertFalse(v.passed)
        self.assertEqual(
            v.violations,
            ("untraceable number: '30%'", "untraceable commitment: 'coupon'",
             "untraceable name: 'Alice'"),
        )

    def test_frozen(self):
        v = check("We open at 7am.")
        with self.assertRaises(Exception):
            v.passed = False


if __name__ == "__main__":
    unittest.main()
