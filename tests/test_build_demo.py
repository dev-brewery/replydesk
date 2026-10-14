"""Tests for tools.build_demo: self-contained, deterministic docs output (T12)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from build_demo import build_demo, demo_run_json  # noqa: E402

from replydesk.fixtures import FIXTURE_DATE, demo_run  # noqa: E402


class BuildDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = demo_run()

    def test_build_writes_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path, json_path = build_demo(tmp)
            self.assertEqual(html_path, Path(tmp) / "index.html")
            self.assertEqual(json_path, Path(tmp) / "demo_run.json")
            self.assertTrue(html_path.is_file())
            self.assertTrue(json_path.is_file())

    def test_html_is_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path, _ = build_demo(tmp)
            text = html_path.read_text(encoding="utf-8")
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("fetch(", text)
        self.assertNotIn("<script", text.lower())
        self.assertIn("<style>", text)

    def test_html_carries_demo_banner_and_pinned_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path, _ = build_demo(tmp)
            text = html_path.read_text(encoding="utf-8")
        self.assertIn("recorded offline run", text)
        self.assertIn(FIXTURE_DATE.isoformat(), text)

    def test_json_matches_run_and_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, json_path = build_demo(tmp)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["generated_on"], FIXTURE_DATE.isoformat())
        self.assertEqual(len(payload["decisions"]), len(self.result.decisions))
        self.assertEqual(len(payload["drafts"]), len(self.result.drafts))

    def test_determinism_two_runs_equal_bytes(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            build_demo(a)
            build_demo(b)
            for name in ("index.html", "demo_run.json"):
                self.assertEqual(
                    (Path(a) / name).read_bytes(),
                    (Path(b) / name).read_bytes(),
                    f"{name} not byte-identical across runs",
                )

    def test_cname_survives_rebuild(self):
        # T17: Pages serves the custom domain from docs/CNAME; the demo build
        # must leave it in place when regenerating docs/.
        with tempfile.TemporaryDirectory() as tmp:
            cname = Path(tmp) / "CNAME"
            cname.write_bytes(b"replydeskhq.tech")
            build_demo(tmp)
            self.assertEqual(cname.read_bytes(), b"replydeskhq.tech")

    def test_json_serializer_deterministic(self):
        self.assertEqual(demo_run_json(self.result), demo_run_json(self.result))


if __name__ == "__main__":
    unittest.main()
