"""Tests for replydesk.fixtures: pinned date and demo fixture loader (offline)."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from replydesk.fixtures import FIXTURE_DATE, FixtureError, load_demo_fixtures
from replydesk.model import BusinessProfile, Review, ToneGuide


def write_demo_dir(base: Path, *, reviews=None, canned=None, profile=None, tone=None):
    (base / "demo_profile.json").write_text(
        json.dumps(profile or {"name": "Sample Cafe", "kind": "cafe", "city": "Sampletown"}),
        encoding="utf-8",
    )
    (base / "tone_guide.md").write_text(tone or "# Voice\nWarm.\n", encoding="utf-8")
    (base / "reviews.json").write_text(
        json.dumps(
            reviews
            if reviews is not None
            else [{"review_id": "r1", "stars": 5, "text": "Great latte."}]
        ),
        encoding="utf-8",
    )
    (base / "canned_drafts.json").write_text(
        json.dumps(canned if canned is not None else {"r1": "Thank you!"}),
        encoding="utf-8",
    )


class TestFixtureDate(unittest.TestCase):
    def test_fixture_date_is_pinned(self):
        self.assertEqual(FIXTURE_DATE, date(2026, 10, 12))


class TestLoadDemoFixtures(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(
                demo,
                reviews=[
                    {"review_id": "r1", "stars": 5, "text": "Great latte.", "date": "2026-10-01"},
                    {"review_id": "r2", "stars": 2, "text": "Cold soup."},
                ],
                canned={"r1": "Thanks!", "r2": "Sorry!"},
            )
            profile, tone, reviews, canned, _prov = load_demo_fixtures(demo)
            self.assertIsInstance(profile, BusinessProfile)
            self.assertEqual(profile.name, "Sample Cafe")
            self.assertEqual(profile.city, "Sampletown")
            self.assertIsInstance(tone, ToneGuide)
            self.assertEqual(len(reviews), 2)
            self.assertIsInstance(reviews[0], Review)
            self.assertEqual(reviews[1].review_id, "r2")
            self.assertEqual(canned, {"r1": "Thanks!", "r2": "Sorry!"})

    def test_date_defaults_to_fixture_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(demo)  # entry without a date key
            _, _, reviews, _, _ = load_demo_fixtures(demo)
            self.assertEqual(len(reviews), 1)

    def test_missing_directory(self):
        with self.assertRaises(FixtureError) as ctx:
            load_demo_fixtures("Zz-Not-A-Real-Dir-Qq")
        self.assertIn("not found", str(ctx.exception))

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            (demo / "reviews.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("demo_profile.json", str(ctx.exception))

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            (demo / "demo_profile.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_profile_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(demo, profile={"name": "Sample Cafe", "kind": "cafe"})
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("city", str(ctx.exception))

    def test_bad_stars(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(demo, reviews=[{"review_id": "r1", "stars": 9, "text": "hm"}])
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("stars", str(ctx.exception))

    def test_review_date_after_fixture_date_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(
                demo,
                reviews=[{"review_id": "r1", "stars": 5, "text": "x", "date": "2026-10-13"}],
            )
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("FIXTURE_DATE", str(ctx.exception))

    def test_duplicate_review_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            dup = {"review_id": "r1", "stars": 5, "text": "x"}
            write_demo_dir(demo, reviews=[dup, dict(dup)], canned={"r1": "a"})
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("duplicate", str(ctx.exception))

    def test_canned_draft_missing_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(demo, canned={})
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("r1", str(ctx.exception))

    def test_empty_reviews_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(demo, reviews=[], canned={})
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("non-empty", str(ctx.exception))

    def test_provenance_key_is_not_a_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(
                demo,
                canned={
                    "r1": "Thanks!",
                    "provenance": {
                        "r1": {
                            "source": "template",
                            "note": "kept canned: model failed verification twice",
                        }
                    },
                },
            )
            _, _, _, canned, prov = load_demo_fixtures(demo)
            self.assertEqual(canned, {"r1": "Thanks!"})
            self.assertEqual(
                prov,
                {"r1": {
                    "source": "template",
                    "note": "kept canned: model failed verification twice",
                }},
            )

    def test_absent_provenance_yields_empty_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(demo)
            _, _, _, canned, prov = load_demo_fixtures(demo)
            self.assertEqual(canned, {"r1": "Thank you!"})
            self.assertEqual(prov, {})

    def test_provenance_bad_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(
                demo,
                canned={"r1": "Thanks!", "provenance": {
                    "r1": {"source": "oracle", "note": "n"}}},
            )
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("source", str(ctx.exception))

    def test_provenance_bad_shape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(
                demo, canned={"r1": "Thanks!", "provenance": {"r1": "template"}}
            )
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("provenance", str(ctx.exception))

    def test_provenance_missing_note_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            write_demo_dir(
                demo,
                canned={"r1": "Thanks!", "provenance": {
                    "r1": {"source": "template"}}},
            )
            with self.assertRaises(FixtureError) as ctx:
                load_demo_fixtures(demo)
            self.assertIn("note", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
