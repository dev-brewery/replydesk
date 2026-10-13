"""Offline tests for the tone guide parser."""

import unittest

from replydesk.toneguide import ToneGuideError, parse_tone_guide


class ParseToneGuideTest(unittest.TestCase):
    def test_both_headings_bullets(self):
        text = (
            "# Voice\n"
            "Friendly, warm, plain words. Short sentences.\n"
            "# Facts I'll stand behind\n"
            "- we open at 7am\n"
            "- free refill on the large drip\n"
        )
        g = parse_tone_guide(text)
        self.assertIn("Friendly, warm", g.voice)
        self.assertEqual(g.facts, ("we open at 7am", "free refill on the large drip"))

    def test_no_headings_all_voice(self):
        g = parse_tone_guide("Just talk like a neighbor.")
        self.assertEqual(g.voice, "Just talk like a neighbor.")
        self.assertEqual(g.facts, ())

    def test_facts_as_prose_sentences(self):
        text = "# Facts I'll stand behind\nWe use local beans. All cups are ceramic.\n"
        g = parse_tone_guide(text)
        self.assertEqual(g.facts, ("We use local beans", "All cups are ceramic"))

    def test_voice_heading_only(self):
        g = parse_tone_guide("# Voice\nCheerful and brief.\n")
        self.assertEqual(g.voice, "Cheerful and brief.")
        self.assertEqual(g.facts, ())

    def test_empty_raises(self):
        with self.assertRaises(ToneGuideError):
            parse_tone_guide("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(ToneGuideError):
            parse_tone_guide("  \n\t\n")


if __name__ == "__main__":
    unittest.main()
