"""Offline tests for the T23 tunnel helpers (replydesk.tunnel).

File-level only: the service.json writer and the cloudflared URL parser.
No test here downloads anything, starts any process, or opens a socket —
the orchestrator runs tools/run_tunnel.* live in the session window.
"""

import json
import tempfile
import unittest
from pathlib import Path

from replydesk.tunnel import parse_tunnel_url, write_service_json

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestScriptShapes(unittest.TestCase):
    """File-level acceptance: the scripts carry the quick-tunnel command
    shape and the failure -> unavailable path; the runbook names the lead
    time. No script is executed here."""

    def load(self, rel):
        return (_REPO_ROOT / rel).read_text(encoding="utf-8")

    def test_scripts_have_quick_tunnel_command(self):
        for rel in ("tools/run_tunnel.sh", "tools/run_tunnel.ps1"):
            text = self.load(rel)
            self.assertIn("tunnel", text)
            self.assertIn("--url", text)
            self.assertIn("--no-autoupdate", text)
            self.assertIn("trycloudflare", text)

    def test_scripts_fail_to_unavailable(self):
        for rel in ("tools/run_tunnel.sh", "tools/run_tunnel.ps1"):
            text = self.load(rel)
            self.assertIn("unavailable", text)
            self.assertIn("exit 1", text)

    def test_stop_mode_writes_unavailable(self):
        self.assertIn("-Stop", self.load("tools/run_tunnel.sh"))
        self.assertIn("-Stop", self.load("tools/run_tunnel.ps1"))

    def test_runbook_names_lead_time_and_flip_back(self):
        text = self.load("tools/TUNNEL.md")
        self.assertIn("15 min", text)
        self.assertIn("unavailable", text)
        self.assertIn("stop", text.lower())


class TestParseTunnelUrl(unittest.TestCase):
    def test_real_quick_tunnel_line(self):
        line = ("2024-10-01T12:00:00Z INF +--------------------------------------------------------------------------------------------+\n"
                "2024-10-01T12:00:00Z INF |  https://booklet-vienna-facts-award.trycloudflare.com                                       |\n")
        self.assertEqual(parse_tunnel_url(line),
                         "https://booklet-vienna-facts-award.trycloudflare.com")

    def test_noisy_output_finds_url(self):
        text = ("some preamble\n"
                "INF Registered tunnel connection\n"
                "trycloudflare.com is mentioned bare here\n"
                "INF |  https://a1b2c3d4.trycloudflare.com  |\n")
        self.assertEqual(parse_tunnel_url(text), "https://a1b2c3d4.trycloudflare.com")

    def test_returns_none_without_url(self):
        self.assertIsNone(parse_tunnel_url("INF Starting quick tunnel\nno url here\n"))

    def test_empty_input(self):
        self.assertIsNone(parse_tunnel_url(""))

    def test_first_url_wins(self):
        text = ("https://first-one.trycloudflare.com\n"
                "https://second-two.trycloudflare.com\n")
        self.assertEqual(parse_tunnel_url(text), "https://first-one.trycloudflare.com")


class TestWriteServiceJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "service.json"

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_live_roundtrip(self):
        write_service_json("live", "https://x-y-z.trycloudflare.com", self.path)
        data = self.read()
        self.assertEqual(data["status"], "live")
        self.assertEqual(data["url"], "https://x-y-z.trycloudflare.com")

    def test_unavailable_forces_null_url(self):
        write_service_json("unavailable", "https://stale.trycloudflare.com", self.path)
        data = self.read()
        self.assertEqual(data, {"status": "unavailable", "url": None})

    def test_output_is_valid_json_file(self):
        write_service_json("live", "https://abc-def.trycloudflare.com", self.path)
        # json.loads above already proves validity; check pretty-printing shape.
        text = self.path.read_text(encoding="utf-8")
        self.assertIn('"status": "live"', text)

    def test_live_without_url_rejected(self):
        with self.assertRaises(ValueError):
            write_service_json("live", None, self.path)

    def test_bad_status_rejected(self):
        with self.assertRaises(ValueError):
            write_service_json("available", None, self.path)

    def test_creates_parent_dirs(self):
        nested = Path(self.tmp.name) / "a" / "b" / "service.json"
        write_service_json("unavailable", path=nested)
        self.assertEqual(json.loads(nested.read_text(encoding="utf-8"))["url"], None)


if __name__ == "__main__":
    unittest.main()
