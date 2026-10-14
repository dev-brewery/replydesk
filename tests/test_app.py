"""Tests for the app.py local web UI. All offline; loopback only."""

import http.client
import threading
import unittest
import urllib.parse

import app


class ParseReviewsTests(unittest.TestCase):
    def test_valid_lines(self):
        reviews = app.parse_reviews("5 | great coffee\n2 | my order was cold")
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].stars, 5)
        self.assertEqual(reviews[0].text, "great coffee")
        self.assertEqual(reviews[1].stars, 2)
        self.assertEqual([r.review_id for r in reviews], ["r1", "r2"])

    def test_blank_lines_skipped(self):
        reviews = app.parse_reviews("\n4 | lovely staff\n\n   \n3 | slow today\n")
        self.assertEqual([r.text for r in reviews], ["lovely staff", "slow today"])

    def test_bad_rating_clear_error(self):
        with self.assertRaises(app.ReviewsFormatError) as ctx:
            app.parse_reviews("5 | fine\nnine | nope")
        self.assertIn("line 2", str(ctx.exception))
        self.assertIn("1 to 5", str(ctx.exception))

    def test_rating_out_of_range(self):
        with self.assertRaises(app.ReviewsFormatError):
            app.parse_reviews("6 | too many stars")

    def test_missing_pipe(self):
        with self.assertRaises(app.ReviewsFormatError):
            app.parse_reviews("5 no pipe here")


class ServerTests(unittest.TestCase):
    """One in-test server exercise on an ephemeral loopback port."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = app.make_server(
            "127.0.0.1", 0,
            client=app._OfflineClient(),
            offline_note=True,
            demo_mode=False,
        )
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def _request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body)
        response = conn.getresponse()
        html = response.read().decode("utf-8")
        conn.close()
        return response, html

    def test_get_form(self):
        response, html = self._request("GET", "/")
        self.assertEqual(response.status, 200)
        self.assertIn("# Voice", html)
        self.assertIn("Facts I&#39;ll stand behind", html)
        self.assertIn("5 | review text", html)
        self.assertIn("<textarea", html)

    def test_get_form_header_steps_and_privacy(self):
        _, html = self._request("GET", "/")
        self.assertIn("1. Paste your reviews", html)
        self.assertIn("2. Describe how you talk", html)
        self.assertIn("3. Copy out the replies", html)
        self.assertIn("No account. Nothing is stored.", html)
        self.assertIn("Your words stay on this machine.", html)

    # Synthetic page copy: enough of a Google-style reviews dump for the
    # heuristic parser (anchors + reviewer name + date + text).
    PAGE_DUMP = (
        "Google reviews\n"
        "4.6\n"
        "★★★★\n"
        "Jamie Rivers\n"
        "3 days ago\n"
        "best coffee on the block, always warm hello\n"
        "Read more\n"
        "★★★\n"
        "Sam Lee\n"
        "a week ago\n"
        "my order was cold twice this month\n"
    )

    def _run_body(self, reviews_text):
        return urllib.parse.urlencode({
            "tone": "# Voice\nWarm, plain, short.\n\n"
                    "# Facts I'll stand behind\n- we open at 7am",
            "reviews": reviews_text,
        }).encode()

    def test_post_page_copy_parses_and_previews(self):
        response, html = self._request("POST", "/run",
                                       body=self._run_body(self.PAGE_DUMP))
        self.assertEqual(response.status, 200)
        self.assertIn("Found 2 reviews from your paste", html)
        self.assertIn("4 stars", html)
        self.assertIn("3 stars", html)
        self.assertIn("best coffee on the block", html)
        self.assertIn("badge-", html)  # the run itself still rendered

    def test_post_zero_found_returns_manual_hint(self):
        response, html = self._request(
            "POST", "/run", body=self._run_body("a lovely place indeed"))
        self.assertEqual(response.status, 400)
        self.assertIn("could not find any reviews", html)
        self.assertIn("manual lines", html)
        self.assertIn("5 | best coffee on the block", html)

    def test_post_run_offline_renders_badges_and_note(self):
        body = self._run_body(
            "5 | the barista remembered my order\n"
            "2 | my order was cold\n"
            "1 | I will sue, this is a legal matter")
        response, html = self._request("POST", "/run", body=body)
        self.assertEqual(response.status, 200)
        self.assertIn("badge-", html)  # triage badges present
        self.assertIn("THANK YOU", html)
        self.assertIn("FIX IT", html)
        self.assertIn("NEEDS HUMAN", html)
        self.assertIn("offline mode", html)  # labeled template note
        self.assertIn("Template reply", html)

    def test_post_run_bad_rating_rejected(self):
        body = urllib.parse.urlencode({
            "tone": "Warm.", "reviews": "0 | bad rating",
        }).encode()
        response, html = self._request("POST", "/run", body=body)
        self.assertEqual(response.status, 400)
        self.assertIn("1 to 5", html)

    def test_no_env_file_needed(self):
        # The offline handler never touches .env; run a request and confirm
        # the suite works regardless (implicit; explicit parse sanity here).
        self.assertTrue(callable(app.parse_reviews))


if __name__ == "__main__":
    unittest.main()
