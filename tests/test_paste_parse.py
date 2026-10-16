"""T19 tests for replydesk.paste_parse (all synthetic; A10 — no real pages)."""

import unittest

from replydesk.model import Review
from replydesk.paste_parse import ReviewsFormatError, parse_paste, parse_reviews


GOOGLE_DUMP = """\
Riverside Coffee Bar
4.2
1,048 reviews
Coffee shop \u00b7 Open until 6 PM

Jordyn Ellis
12 reviews\u00b76 friends
\u2605\u2605\u2605\u2605\u2605
2 days ago
The cortado here is the best in town and the baristas remember my order.

Marcus Hale
3 reviews
\u2605\u2605\u2605
a week ago
Waited twenty minutes on a Tuesday and the milk was scorched twice.

Priya Nair
81 reviews\u00b7140 friends
\u2605\u2605\u2605\u2605
October 12
Great pastries and the back patio is quiet in the mornings.
Owner responded
Response from the owner
Thanks for the kind words about our afternoon staff, Priya!
See more
Like
Share
"""

YELP_DUMP = """\
Riverside Coffee Bar
4.2 star rating
1048 reviews

Sasha B.
Elite 2024
Portland, OR
4/5
10/2/2024
Solid drip coffee and the staff fixed my order without any fuss.

Devon K.
2 friends
12 reviews
3/5
Updated review: still a solid latte, though the line moves slowly at 8am.
"""

HALF_STAR_DUMP = """\
Reviewer A
\u2605\u2605\u2605\u00bd
a day ago
Half-star floors down to three, and this text is the body.
"""


class ManualLinesTests(unittest.TestCase):
    def test_manual_lines_parse_unchanged(self):
        reviews = parse_paste("5 | great coffee\n2 | my order was cold")
        self.assertEqual(
            [Review("r1", 5, "great coffee"), Review("r2", 2, "my order was cold")],
            reviews,
        )

    def test_manual_error_cases_still_raise(self):
        with self.assertRaises(ReviewsFormatError):
            parse_paste("5 | fine\nnine | nope")
        with self.assertRaises(ReviewsFormatError):
            parse_paste("6 | too many stars")
        with self.assertRaises(ReviewsFormatError):
            parse_paste("5 | ")

    def test_empty_input(self):
        self.assertEqual([], parse_paste(""))
        self.assertEqual([], parse_paste("  \n \n"))


class GoogleShapeTests(unittest.TestCase):
    def test_three_reviews_with_correct_stars_and_text(self):
        reviews = parse_paste(GOOGLE_DUMP)
        self.assertEqual(3, len(reviews))
        self.assertEqual([5, 3, 4], [r.stars for r in reviews])
        self.assertEqual([f"p{i}" for i in (1, 2, 3)], [r.review_id for r in reviews])
        self.assertEqual(
            "The cortado here is the best in town and the baristas remember my order.",
            reviews[0].text,
        )
        self.assertEqual(
            "Waited twenty minutes on a Tuesday and the milk was scorched twice.",
            reviews[1].text,
        )
        self.assertEqual(
            "Great pastries and the back patio is quiet in the mornings.",
            reviews[2].text,
        )

    def test_dates_and_names_never_in_text(self):
        for review in parse_paste(GOOGLE_DUMP):
            self.assertNotIn("ago", review.text)
            self.assertNotIn("October 12", review.text)
            self.assertNotIn("Jordyn", review.text)
            self.assertNotIn("friends", review.text)

    def test_owner_response_dropped(self):
        for review in parse_paste(GOOGLE_DUMP):
            self.assertNotIn("Thanks for the kind words", review.text)
            self.assertNotIn("Owner responded", review.text)

    def test_ui_noise_dropped(self):
        texts = " ".join(r.text for r in parse_paste(GOOGLE_DUMP))
        for token in ("See more", "Like", "Share", "1,048 reviews"):
            self.assertNotIn(token, texts)


class YelpShapeTests(unittest.TestCase):
    def test_two_reviews_numeric_anchors(self):
        reviews = parse_paste(YELP_DUMP)
        self.assertEqual(2, len(reviews))
        self.assertEqual([4, 3], [r.stars for r in reviews])
        self.assertEqual(
            "Solid drip coffee and the staff fixed my order without any fuss.",
            reviews[0].text,
        )
        self.assertEqual(
            "Updated review: still a solid latte, though the line moves slowly at 8am.",
            reviews[1].text,
        )
        self.assertNotIn("10/2/2024", reviews[0].text)
        self.assertNotIn("Elite 2024", reviews[0].text)

    def test_rated_form_anchors(self):
        reviews = parse_paste("Rated 4 out of 5.\nGood service, quick fix.")
        self.assertEqual(1, len(reviews))
        self.assertEqual(4, reviews[0].stars)
        self.assertEqual("Good service, quick fix.", reviews[0].text)


class RobustnessTests(unittest.TestCase):
    def test_half_star_floors_down(self):
        reviews = parse_paste(HALF_STAR_DUMP)
        self.assertEqual(1, len(reviews))
        self.assertEqual(3, reviews[0].stars)

    def test_garbage_only_returns_empty_never_raises(self):
        for garbage in ("hello world\nno stars here", "\u2605\u2606 3.9", "12345", "---"):
            with self.subTest(garbage=garbage):
                self.assertEqual([], parse_paste(garbage))

    def test_segment_without_usable_text_discarded(self):
        reviews = parse_paste("\u2605\u2605\u2605\u2605\u2605\n2 days ago")
        self.assertEqual([], reviews)

    def test_anchor_without_text_keeps_others(self):
        reviews = parse_paste(
            "Ann Lee\n\u2605\u2605\u2605\u2605\n3 days ago\nLovely staff.\n"
            "\u2605\u2605\nQuick service but cramped."
        )
        self.assertEqual(2, len(reviews))
        self.assertEqual(4, reviews[0].stars)
        self.assertEqual("Lovely staff.", reviews[0].text)
        self.assertEqual(2, reviews[1].stars)

    def test_no_empty_star_run_ignored(self):
        reviews = parse_paste("\u2606\u2606\u2606\njust decoration text")
        self.assertEqual([], reviews)


class GooglePrivateUseStarTests(unittest.TestCase):
    """Real Google Maps page copies carry star rows of U+E838 (PUA)."""

    E838 = "\ue838"
    FILLER = "\ue8dc\ue80d\ue5d4\ue88e"

    def test_pua_star_run_parses_five(self):
        text = ("Reviewer One\n12 reviews\n" + self.E838 * 5
                + "\n2 days ago\nGreat coffee and quick service.\n")
        reviews = parse_paste(text)
        self.assertEqual(1, len(reviews))
        self.assertEqual(5, reviews[0].stars)

    def test_pua_run_with_filler_counts_only_stars(self):
        text = ("Reviewer Two\n" + self.FILLER + self.E838 * 4
                + "\na week ago\nNice pastries.\n")
        reviews = parse_paste(text)
        self.assertEqual(1, len(reviews))
        self.assertEqual(4, reviews[0].stars)

    def test_mixed_regular_and_pua_stars_both_count(self):
        text = ("Reviewer Three\n" + "\u2605\u2605" + self.E838 * 2
                + "\nOctober 12\nQuiet patio.\n")
        reviews = parse_paste(text)
        self.assertEqual(1, len(reviews))
        self.assertEqual(4, reviews[0].stars)

    def test_pua_run_without_full_star_stays_unusable(self):
        text = self.FILLER + "\njust decoration text"
        self.assertEqual([], parse_paste(text))

    def test_three_probe_shapes(self):
        meta_full = ("Riverside Coffee Bar\n4.2\n1,048 reviews\n"
                     "Coffee shop \u00b7 Open until 6 PM\n\n"
                     "Jordyn Ellis\n12 reviews\n" + self.E838 * 5
                     + "\n2 days ago\nThe cortado is great.\n")
        no_meta = ("Jordyn Ellis\n" + self.E838 * 5
                   + "\n2 days ago\nThe cortado is great.\n")
        reviews_meta = ("Jordyn Ellis\n12 reviews \u00b7 3 photos\n"
                        + self.E838 * 5
                        + "\n2 days ago\nThe cortado is great.\n")
        for label, text in (("full", meta_full), ("no-meta", no_meta),
                            ("reviews-photos", reviews_meta)):
            with self.subTest(shape=label):
                reviews = parse_paste(text)
                self.assertEqual(1, len(reviews))
                self.assertEqual(5, reviews[0].stars)
                self.assertEqual("The cortado is great.", reviews[0].text)


# Synthetic manager-view shape (T25): literal word 'star' rows, fused icon
# ligature, owner's own dashboard chrome.
MANAGER_VIEW_ONE = """Reviews
5.0
star
star
star
star
star
(
1 review
)

All

Replied

Unreplied

Jordan Blakeopen_in_new
Local Guide · 22 reviews · 17 photos
starstarstarstarstar Sep 19, 2024
Great service and quick turnaround! 😀
"""

MANAGER_VIEW_TWO = """Reviews
5.0
star
star
star
star
star
(
2 reviews
)

All
Replied
Unreplied

Jordan Blakeopen_in_new
Local Guide · 4 reviews · 2 photos
starstarstarstarstar Sep 19, 2024
Great service and quick turnaround!

Casey Kimopen_in_new
Local Guide · 9 reviews
starstarstar Oct 2, 2024
Waited twenty minutes and the order was wrong.
"""

MANAGER_VIEW_SUMMARY_ONLY = """Reviews
5.0
star
star
star
star
star
(
0 reviews
)

All
Replied
Unreplied
"""


class ManagerViewTests(unittest.TestCase):
    """T25: Google Business Profile manager copy (synthetic, A10-safe)."""

    def test_one_review_manager_shape(self):
        reviews = parse_paste(MANAGER_VIEW_ONE)
        self.assertEqual(1, len(reviews))
        self.assertEqual(5, reviews[0].stars)
        self.assertEqual("Great service and quick turnaround! 😀",
                         reviews[0].text)
        self.assertNotIn("Sep 19, 2024", reviews[0].text)

    def test_three_star_variant(self):
        reviews = parse_paste(
            "Casey Kimopen_in_new\nLocal Guide · 9 reviews\n"
            "starstarstar Oct 2, 2024\nWaited twenty minutes and the order was wrong.")
        self.assertEqual([3], [r.stars for r in reviews])
        self.assertEqual("Waited twenty minutes and the order was wrong.",
                         reviews[0].text)

    def test_two_reviews_back_to_back(self):
        reviews = parse_paste(MANAGER_VIEW_TWO)
        self.assertEqual(
            [(5, "Great service and quick turnaround!"),
             (3, "Waited twenty minutes and the order was wrong.")],
            [(r.stars, r.text) for r in reviews],
        )

    def test_summary_block_only_yields_nothing(self):
        self.assertEqual([], parse_paste(MANAGER_VIEW_SUMMARY_ONLY))

    def test_star_word_line_without_date_anchors(self):
        reviews = parse_paste("Sam Reyes\nstarstarstarstar\nLoved the pastries.")
        self.assertEqual([4], [r.stars for r in reviews])

    def test_maps_shape_still_parses(self):
        reviews = parse_paste(GOOGLE_DUMP)
        self.assertEqual(3, len(reviews))
        self.assertEqual([5, 3, 4], [r.stars for r in reviews])

    def test_manual_lines_still_parse(self):
        reviews = parse_paste("5 | great coffee\n2 | my order was cold")
        self.assertEqual(2, len(reviews))


class AppReexportTests(unittest.TestCase):
    def test_app_reexports_all_three_names(self):
        import app

        self.assertIs(app.parse_paste, parse_paste)
        self.assertIs(app.parse_reviews, parse_reviews)
        self.assertIs(app.ReviewsFormatError, ReviewsFormatError)

    def test_parse_reviews_implementation_moved(self):
        self.assertEqual([Review("r1", 5, "ok")], parse_reviews("5 | ok"))


if __name__ == "__main__":
    unittest.main()
