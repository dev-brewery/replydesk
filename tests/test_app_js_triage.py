"""T21d tests for docs/rd.js triage + template ports — node-driven, offline.

Mirrors tests/test_triage.py probes against rd.triageReview (every rule group,
star fall-through, case-sensitive staff-name patterns) and checks
rd.templateReply against the Python draft.template_reply output for the same
decision + profile (golden parity). Skips cleanly if node is absent.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RD_JS = REPO / "docs" / "rd.js"

PROBES = [
    # (stars, text, expected category, expected reason substring)
    (1, "I want my money back, this is unacceptable", "needs_human", "refund-dispute"),
    (5, "Lovely place, but pay up or I will sue", "needs_human", "legal"),
    (2, "call my lawyer", "needs_human", "legal"),
    (2, "small claims court", "needs_human", "legal"),
    (2, "cease and desist letter", "needs_human", "legal"),
    (2, "I got sick after eating here, went to the hospital", "needs_human",
     "safety-health"),
    (3, "The staff was RACIST to my friend", "needs_human", "personal"),
    (4, "Great food. I spoke to Dave about it.", "needs_human", "personal"),
    (3, "the tech named Dave was dismissive", "needs_human", "personal"),
    (3, "the plumber named Marlene rushed the job", "needs_human", "personal"),
    # lowercase generic role without a name is not personal
    (2, "spoke to the manager and nothing happened", "fix_it",
     "2 stars <= 3 -> fix-it"),
    (2, "Came here after my mother passed, service was cold", "needs_human",
     "personal"),
    (5, "Great, but if I don't get a refund I will sue", "needs_human", "legal"),
    (2, "Meh experience, nothing worth writing home about", "fix_it",
     "2 stars <= 3 -> fix-it"),
    (5, "Amazing! Only note: my order was late by a bit.", "fix_it", "complaint"),
    (5, "it was broken", "fix_it", "complaint"),
    (5, "never arrived", "fix_it", "complaint"),
    (5, "place was dirty", "fix_it", "complaint"),
    (5, "I was overcharged", "fix_it", "complaint"),
    (5, "wrong order given", "fix_it", "complaint"),
    (5, "Wonderful pastries, friendly service, will come again", "thank_you",
     "5 stars >= 4 -> thank-you"),
    (4, "Solid experience overall", "thank_you", "thank-you"),
]

# Reason formatting parity: first match reports the pattern source text.
REASON_CASES = [
    (1, "I want my money back, this is unacceptable",
     "refund-dispute: matched pattern 'money back'"),
    (5, "pay up or I will sue", "legal: matched pattern '\\bsue\\b'"),
    (4, "Great food. I spoke to Dave about it.",
     "personal: matched pattern 'spoke to [A-Z][a-z]+'"),
]

DRIVER_TEMPLATE = r"""
'use strict';
const assert = require('assert');
require(process.argv[2]);
const rd = globalThis.rd;

const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

test('triage mirrors the Python table', () => {
  for (const [stars, text, category, reasonPart] of payload.probes) {
    const d = rd.triageReview({ review_id: 'r1', stars: stars, text: text });
    assert.strictEqual(d.category, category, text);
    assert.ok(d.reason.includes(reasonPart), text + ' -> ' + d.reason);
    assert.strictEqual(d.review.review_id, 'r1');
  }
});

test('reasons are formatted identically to Python', () => {
  for (const [stars, text, reason] of payload.reason_cases) {
    assert.strictEqual(
      rd.triageReview({ review_id: 'r1', stars: stars, text: text }).reason,
      reason);
  }
});

test('template reply golden parity with Python', () => {
  for (const [stars, text, profile, expected] of payload.template_cases) {
    const d = rd.triageReview({ review_id: 'r1', stars: stars, text: text });
    assert.strictEqual(rd.templateReply(d, profile), expected);
  }
});

test('template label matches Python FALLBACK_LABEL', () => {
  assert.strictEqual(rd.FALLBACK_LABEL, payload.fallback_label);
});

test('no invented facts: template only echoes review text and profile fields', () => {
  const review = { review_id: 'r1', stars: 2,
                   text: 'The order was late and cold.' };
  const profile = { name: 'The Corner Bakery', city: 'Springfield' };
  const body = rd.templateReply(rd.triageReview(review), profile);
  assert.ok(body.includes(review.text));
  assert.ok(body.includes(profile.name));
  if (rd.triageReview(review).category === 'thank_you') {
    assert.ok(body.includes(profile.city));
  }
  // every fact in the body comes from the review or the profile
  const allowed = new Set((review.text + ' ' + JSON.stringify(profile))
    .toLowerCase().match(/[a-z]+/g));
  for (const w of body.toLowerCase().match(/[a-z]+/g) || []) {
    if (!/^(thank|you|for|the|kind|words|about|we|are|glad|took|time|to|share|this|said|gave|star|stars|it|means|a|lot|everyone|here|at|in|telling|us|sorry|your|visit|was|not|what|should|have|been|is|shared|person|reads|every|note|like|yours|and|will|look|into)$/.test(w)) {
      assert.ok(allowed.has(w), 'invented fact: ' + w);
    }
  }
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed += 1; console.error('FAIL', name, e.message); }
}
if (failed) process.exit(1);
console.log('OK ' + tests.length + ' tests');
"""


def _golden_template_cases() -> list:
    from replydesk.draft import template_reply
    from replydesk.model import BusinessProfile, Review, TriageCategory, \
        TriageDecision

    def build(stars, text, profile):
        review = Review(review_id="r1", stars=stars, text=text)
        if stars >= 4 and not any(
                p in text.lower()
                for p in ("sue", "refund", "money back", "late", "cold")):
            category = TriageCategory.THANK_YOU
        else:
            category = TriageCategory.FIX_IT
        decision = TriageDecision(review=review, category=category, reason="")
        return [stars, text,
                {"name": profile.name, "city": profile.city},
                template_reply(decision, profile)]

    profile = BusinessProfile(name="The Corner Bakery", kind="bakery",
                              city="Springfield")
    return [
        build(5, "Wonderful pastries, friendly service, will come again", profile),
        build(4, "Solid experience overall", profile),
        build(2, "The order was late and cold.", profile),
        build(1, "Wrong order twice in one week.", profile),
    ]


class RdJsTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node:
            from replydesk.draft import FALLBACK_LABEL
            payload = {
                "probes": PROBES,
                "reason_cases": REASON_CASES,
                "template_cases": _golden_template_cases(),
                "fallback_label": FALLBACK_LABEL,
            }
            cls.tmp = tempfile.mkdtemp(prefix="rdjs_t21d_")
            cls.payload_path = Path(cls.tmp) / "payload.json"
            cls.payload_path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        if cls.node and hasattr(cls, "tmp"):
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_rd_js_triage_and_template(self):
        if not self.node:
            self.skipTest("node not available")
        driver = Path(self.tmp) / "driver.js"
        driver.write_text(DRIVER_TEMPLATE, encoding="utf-8")
        proc = subprocess.run(
            [self.node, str(driver), str(RD_JS), str(self.payload_path)],
            capture_output=True, text=True, timeout=60, cwd=str(REPO))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
