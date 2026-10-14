"""T24b tests for the /help/ page (static assertions on docs/help/index.html).

The help page must cover the Google and Yelp copy-paste paths, the manual
line format, the trust block, and support — and stay self-contained apart
from the support repo link. The product page must link to it.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELP = REPO / "docs" / "help" / "index.html"
INDEX = REPO / "docs" / "index.html"

TRUST_COPY = (
    "You never give replydesk your Google or Yelp password \u2014 you only"
    " paste text you can already see. Nothing is posted anywhere. Your"
    " account lives in your browser. Your reviews go only to the drafting"
    " model configured by the operator."
)


def _normalized(html: str) -> str:
    """Collapse markup: entities to text, all whitespace runs to one space."""
    return re.sub(r"\s+", " ",
                  html.replace("&mdash;", "\u2014").replace("&amp;", "&"))


class HelpPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HELP.exists():
            raise AssertionError("docs/help/index.html does not exist")
        cls.html = HELP.read_text(encoding="utf-8")
        cls.flat = _normalized(cls.html)
        cls.index = INDEX.read_text(encoding="utf-8")

    def test_back_link_to_product(self):
        self.assertIn('href="/"', self.html)
        self.assertIn("back to replydesk", self.html)

    def test_google_section(self):
        self.assertIn("Google", self.html)
        self.assertIn("reviews panel", self.html)
        self.assertIn("Ctrl+A", self.html)
        self.assertIn("Cmd+C", self.html)

    def test_google_phone_path(self):
        self.assertIn("Google Maps app", self.html)
        self.assertIn("Reviews", self.html)

    def test_yelp_section(self):
        self.assertIn("Yelp", self.html)
        self.assertIn("Reviews", self.html)
        self.assertGreaterEqual(self.html.lower().count("paste"), 3)

    def test_manual_line_format(self):
        self.assertIn("5 | best coffee on the block", self.html)
        self.assertIn("one review per line", self.html)

    def test_what_happens_next(self):
        self.assertIn("Found N reviews", self.html)
        self.assertIn("Draft replies", self.html)
        self.assertIn("no invented facts", self.html)
        self.assertIn("legal threats", self.html)
        self.assertIn("safety claims", self.html)
        self.assertIn("refund disputes", self.html)
        self.assertIn("personal matters", self.flat)
        self.assertIn("the reason why", self.flat)

    def test_trust_block_verbatim(self):
        self.assertIn(TRUST_COPY, self.flat)

    def test_support_links_repo_only(self):
        self.assertIn("https://github.com/dev-brewery/replydesk", self.html)

    def test_no_external_assets(self):
        # Only allowed external URL is the support repo link.
        import re
        urls = re.findall(r"https?://[^\s\"'<>]+", self.html)
        self.assertEqual(urls, ["https://github.com/dev-brewery/replydesk"])
        self.assertNotIn("<script", self.html)

    def test_no_real_business_names(self):
        self.assertNotIn("Brewery", self.html.replace(
            "github.com/dev-brewery/replydesk", ""))

    def test_product_links_to_help(self):
        self.assertRegex(self.index, r'<a href="/help/">[^<]*How do')
        # Header link too.
        self.assertIn('href="/help/"', self.index)
        self.assertIn(">Help</a>", self.index)

    def test_zero_found_hint_links_help(self):
        self.assertIn('id="zero-found-hint"', self.index)
        # Both in-page help links come after the reviews textarea.
        self.assertIn('id="reviews"', self.index)
        self.assertEqual(self.index.count('href="/help/"'), 3)


if __name__ == "__main__":
    unittest.main()
