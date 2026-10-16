"""Unit tests for the final_audit pattern scanner (T18).

All patterns and planted text here are synthetic; no real pattern
values are reproduced.
"""
import subprocess
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


class TestHistoryScan(unittest.TestCase):
    """History leg runs against a synthetic temp git repo."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.git("init", "-q")

    def git(self, *args):
        identity = ["-c", "user.name=test", "-c",
                    "user.email=test@example.invalid"]
        subprocess.run(["git", "-C", str(self.dir), *identity, *args],
                       check=True, capture_output=True)

    def commit(self, name: str, text: str):
        (self.dir / name).write_text(text, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-q", "-m", f"add {name}")

    def test_planted_commit_detected(self):
        self.commit("leak.txt", "harmless line\nplanted pattern here\n")
        hits = final_audit.scan_history(["planted.pattern"], self.dir)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[list(hits)[0]], ["planted.pattern"])

    def test_clean_history_clean(self):
        self.commit("clean.txt", "Ridgeline Plumbing, Cedar Falls.\n")
        self.assertEqual(
            final_audit.scan_history(["planted.pattern"], self.dir), {})

    def test_no_patterns_means_no_scan(self):
        self.assertEqual(final_audit.scan_history([], self.dir), {})

    def test_commit_message_hit_detected(self):
        self.git("commit", "-q", "--allow-empty", "-m", "planted pattern")
        hits = final_audit.scan_history(["planted.pattern"], self.dir)
        self.assertEqual(len(hits), 1)


if __name__ == "__main__":
    unittest.main()
