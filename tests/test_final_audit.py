"""Unit tests for the final_audit pattern scanner (T18).

All patterns and planted text here are synthetic; no real pattern
values are reproduced.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import final_audit  # noqa: E402


class TestPatternScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, rel: str, text: str) -> Path:
        p = self.dir / rel
        p.write_text(text, encoding="utf-8")
        return p

    def test_planted_pattern_caught(self):
        f = self.write("leak.md", "The planted pattern is in this line.\n")
        pats = final_audit.load_patterns(self.write(
            ".privacy-patterns", "# comment\nplanted.pattern\n"))
        hits = final_audit.scan_files(pats, [f.relative_to(self.dir)], self.dir)
        self.assertIn(f.relative_to(self.dir), hits)
        self.assertEqual(hits[f.relative_to(self.dir)], ["planted.pattern"])

    def test_clean_file_passes(self):
        f = self.write("clean.md", "Ridgeline Plumbing, Cedar Falls.\n")
        pats = final_audit.load_patterns(self.write(
            ".privacy-patterns", "nowhere-town\nlan\\.prefix\\.\n"))
        self.assertEqual(final_audit.scan_files(pats, [f.relative_to(self.dir)],
                                                self.dir), {})

    def test_case_insensitive_and_multiline(self):
        f = self.write("cfg.txt", "host = lan.prefix.77\nok\n")
        hits = final_audit.scan_text(["lan\\.prefix\\."], f.read_text())
        self.assertEqual(hits, ["lan\\.prefix\\."])

    def test_comments_and_blanks_stripped(self):
        pats = final_audit.load_patterns(self.write(
            ".privacy-patterns", "# note\n\n  \npattern-one\n"))
        self.assertEqual(pats, ["pattern-one"])

    def test_missing_pattern_file_means_no_patterns(self):
        self.assertEqual(final_audit.load_patterns(self.dir / "nope"), [])


if __name__ == "__main__":
    unittest.main()
