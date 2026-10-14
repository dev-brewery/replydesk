"""T21b tests for the docs/ SPA shell (static assertions on index.html).

The honest copy must render verbatim, all three sign-up fields must exist,
and the page must stay self-contained: no external URLs, relative rd.js load.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "docs" / "index.html"
APP_JS = REPO / "docs" / "app.js"
RD_JS = REPO / "docs" / "rd.js"

HONEST_COPY = (
    "Your account lives in this browser for now \u2014 we'll"
    " move it to the service at launch."
)


class SpaShellTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.app = APP_JS.read_text(encoding="utf-8")

    def test_honest_copy_verbatim(self):
        self.assertIn(HONEST_COPY, self.html)

    def test_three_signup_fields(self):
        for field in ("name", "email", "password"):
            self.assertRegex(
                self.html,
                rf'<input id="su-{field}" name="{field}"',
                f"sign-up field {field} missing")

    def test_no_external_urls(self):
        self.assertNotRegex(self.html, r"https?://")
        self.assertNotRegex(self.app, r"https?://")

    def test_relative_script_loads(self):
        self.assertIn('<script src="rd.js?v=6"></script>', self.html)
        self.assertIn('<script src="app.js?v=6"></script>', self.html)

    def test_header_and_pricing_copy(self):
        self.assertIn("review replies in your own voice", self.html)
        self.assertIn("$9/month, first month free", self.html)
        self.assertIn("No card needed", self.html)

    def test_header_links_recorded_demo(self):
        # T22d: the product (domain root) links to the recorded demo at /demo/.
        self.assertIn('href="/demo/"', self.html)
        self.assertIn("see a recorded demo", self.html)

    def test_workspace_controls_wired(self):
        # T21c replaced the placeholder card with real workspace controls.
        self.assertIn('id="tone"', self.html)
        self.assertIn('id="reviews"', self.html)
        self.assertIn("Preview\n          found reviews", self.html)

    def test_app_js_is_dom_glue_only(self):
        # app.js must not reimplement logic — it consumes rd.* helpers.
        self.assertIn("rd.createAccount", self.app)
        self.assertIn("rd.login", self.app)
        self.assertIn("rd.logout", self.app)
        self.assertIn("rd.sessionEmail", self.app)

    def test_rd_js_exposes_auth_helpers(self):
        rd = RD_JS.read_text(encoding="utf-8")
        for fn in ("hashPassword", "equalHex", "createAccount", "login",
                   "logout", "sessionEmail", "randomSaltHex"):
            self.assertIn(fn, rd)
        self.assertIn("PBKDF2_ITERATIONS = 100000", rd)


if __name__ == "__main__":
    unittest.main()
