"""T21b tests for docs/rd.js auth helpers — node-driven, offline.

Runs node on a driver script that loads rd.js and exercises sign-up / log-in
/ session / log-out over a Map-backed storage shim, plus PBKDF2 hash
determinism and constant-time compare. Skips cleanly if node is absent.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RD_JS = REPO / "docs" / "rd.js"

DRIVER = r"""
'use strict';
const assert = require('assert');
require(process.argv[2]);
const rd = globalThis.rd;

function makeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    _map: m,
  };
}

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

test('hash determinism: same salt gives same hex, new salt differs', async () => {
  const a = await rd.hashPassword('correct horse battery staple',
    '00112233445566778899aabbccddeeff');
  const b = await rd.hashPassword('correct horse battery staple',
    '00112233445566778899aabbccddeeff');
  const c = await rd.hashPassword('correct horse battery staple',
    'ffeeddccbbaa99887766554433221100');
  assert.strictEqual(a, b);
  assert.notStrictEqual(a, c);
  assert.strictEqual(a.length, 64); // 32-byte key hex
});

test('equalHex is true only for equal hex strings', () => {
  assert.ok(rd.equalHex('ab12', 'ab12'));
  assert.ok(!rd.equalHex('ab12', 'ab13'));
  assert.ok(!rd.equalHex('ab12', 'ab12cc'));
  assert.ok(!rd.equalHex('ab12', 12));
  assert.ok(!rd.equalHex(null, null));
});

test('random salt is 16 bytes and fresh each call', () => {
  const s1 = rd.randomSaltHex();
  const s2 = rd.randomSaltHex();
  assert.strictEqual(s1.length, 32);
  assert.notStrictEqual(s1, s2);
});

test('valid signup stores account and sets session', async () => {
  const s = makeStorage();
  const r = await rd.createAccount(s, {
    name: 'Dana Owner', email: 'Dana@Example.com', password: 'longenough1' });
  assert.ok(r.ok, r.error);
  const accounts = JSON.parse(s.getItem(rd.ACCOUNTS_KEY));
  const acct = accounts['dana@example.com'];
  assert.ok(acct && acct.name === 'Dana Owner');
  assert.match(acct.salt, /^[0-9a-f]{32}$/);
  assert.match(acct.hash, /^[0-9a-f]{64}$/);
  assert.strictEqual(s.getItem(rd.SESSION_KEY), 'dana@example.com');
});

test('empty name rejected', async () => {
  const r = await rd.createAccount(makeStorage(),
    { name: '  ', email: 'a@b.co', password: 'longenough1' });
  assert.ok(!r.ok);
});

test('bad email rejected', async () => {
  const s = makeStorage();
  const r = await rd.createAccount(s, {
    name: 'Dana', email: 'not-an-email', password: 'longenough1' });
  assert.ok(!r.ok);
  assert.strictEqual(s.getItem(rd.SESSION_KEY), null);
});

test('short password rejected', async () => {
  const s = makeStorage();
  const r = await rd.createAccount(s, {
    name: 'Dana', email: 'a@b.co', password: 'short' });
  assert.ok(!r.ok);
  assert.strictEqual(s.getItem(rd.SESSION_KEY), null);
});

test('duplicate email rejected', async () => {
  const s = makeStorage();
  const first = await rd.createAccount(s, {
    name: 'Dana', email: 'a@b.co', password: 'longenough1' });
  assert.ok(first.ok, first.error);
  const dupe = await rd.createAccount(s, {
    name: 'Someone Else', email: 'A@B.CO', password: 'otherpass99' });
  assert.ok(!dupe.ok);
  const accounts = JSON.parse(s.getItem(rd.ACCOUNTS_KEY));
  assert.strictEqual(accounts['a@b.co'].name, 'Dana'); // original untouched
});

test('login verifies correct password, rejects wrong one generically', async () => {
  const s = makeStorage();
  await rd.createAccount(s, { name: 'Dana', email: 'a@b.co',
    password: 'longenough1' });
  s.removeItem(rd.SESSION_KEY); // isolate login from signup's session set
  const bad = await rd.login(s, { email: 'a@b.co', password: 'wrongpass99' });
  assert.ok(!bad.ok);
  const none = await rd.login(s, { email: 'ghost@b.co', password: 'whatever99' });
  assert.ok(!none.ok);
  assert.strictEqual(bad.error, none.error); // one generic message
  const good = await rd.login(s, { email: ' A@B.co ', password: 'longenough1' });
  assert.ok(good.ok, good.error);
  assert.strictEqual(good.name, 'Dana');
  assert.strictEqual(s.getItem(rd.SESSION_KEY), 'a@b.co');
});

test('logout clears the session only', async () => {
  const s = makeStorage();
  await rd.createAccount(s, { name: 'Dana', email: 'a@b.co',
    password: 'longenough1' });
  rd.logout(s);
  assert.strictEqual(s.getItem(rd.SESSION_KEY), null);
  const accounts = JSON.parse(s.getItem(rd.ACCOUNTS_KEY));
  assert.ok(accounts['a@b.co']); // account record survives
});

// --- T21c: founding-plan gate + found-reviews preview -----------------------

async function signedUp(s) {
  const r = await rd.createAccount(s, { name: 'Dana', email: 'a@b.co',
    password: 'longenough1' });
  assert.ok(r.ok, r.error);
}

test('plan locked until activation: signed in but no plan state', async () => {
  const s = makeStorage();
  await signedUp(s);
  const st = rd.planState(s);
  assert.ok(st.signedIn);
  assert.strictEqual(st.plan, null);
});

test('activation stores founding trial state and unlocks', async () => {
  const s = makeStorage();
  await signedUp(s);
  const r = rd.activateTrial(s, '2025-01-01');
  assert.ok(r.ok, r.error);
  assert.deepStrictEqual(r.plan, {
    plan: 'founding', status: 'trial', activated_on: '2025-01-01' });
  assert.strictEqual(rd.planState(s).plan.status, 'trial');
});

test('activation requires a signed-in account', () => {
  const r = rd.activateTrial(makeStorage(), '2025-01-01');
  assert.ok(!r.ok);
});

test('plan state persists across logout/login (reload path)', async () => {
  const s = makeStorage();
  await signedUp(s);
  rd.activateTrial(s, '2025-01-02');
  rd.logout(s);
  assert.strictEqual(rd.planState(s).signedIn, false);
  const back = await rd.login(s, { email: 'a@b.co', password: 'longenough1' });
  assert.ok(back.ok, back.error);
  const st = rd.planState(s);
  assert.ok(st.signedIn);
  assert.strictEqual(st.plan.status, 'trial');
  assert.strictEqual(st.plan.activated_on, '2025-01-02');
});

test('preview uses rd.parsePaste: glyph-run dump gives count + first lines', () => {
  const dump = [
    '\u2605\u2605\u2605\u2605\u2605',
    'Best coffee around, hands down.',
    '',
    '\u2605\u2605',
    'Cold order at first, staff fixed it fast.',
  ].join('\n');
  const res = rd.previewSummaries(dump);
  assert.strictEqual(res.count, 2);
  assert.ok(res.found);
  assert.strictEqual(res.items[0].stars, 5);
  assert.match(res.items[0].first, /^Best coffee around/);
  assert.strictEqual(res.items[1].stars, 2);
});

test('zero-found preview flags the manual-lines hint path', () => {
  const res = rd.previewSummaries('lorem ipsum nonsense only\nno anchors here');
  assert.strictEqual(res.count, 0);
  assert.strictEqual(res.found, false);
});

(async () => {
  const results = [];
  for (const [name, fn] of tests) {
    try { await fn(); results.push([name, 'pass']); }
    catch (e) { results.push([name, 'fail: ' + e.message]); }
  }
  const failed = results.filter(([, s]) => s !== 'pass');
  for (const [name, status] of results) console.log(status + ' ' + name);
  console.log(failed.length ? 'FAILED' : 'ALL PASS');
  process.exit(failed.length ? 1 : 0);
})();
"""


@unittest.skipIf(shutil.which("node") is None, "node is not available")
class RdJsAuthTest(unittest.TestCase):
    def test_auth_suite(self):
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "auth_driver.js"
            driver.write_text(DRIVER, encoding="utf-8")
            proc = subprocess.run(
                ["node", str(driver), str(RD_JS)],
                capture_output=True, text=True, timeout=120, cwd=tmp)
        output = proc.stdout + proc.stderr
        self.assertEqual(
            proc.returncode, 0,
            f"node auth suite failed:\n{output}")
        self.assertIn("ALL PASS", output)
        # Every expected behavior is actually exercised, not silently skipped.
        for marker in (
            "hash determinism", "equalHex", "valid signup", "empty name",
            "bad email rejected", "short password rejected",
            "duplicate email rejected", "login verifies", "logout clears",
            "plan locked until activation", "activation stores",
            "activation requires", "persists across logout/login",
            "preview uses rd.parsePaste", "zero-found preview",
        ):
            self.assertIn(marker, output)


class PlanGateShellTest(unittest.TestCase):
    """T21c static assertions: plan gate + workspace in the SPA shell."""

    @classmethod
    def setUpClass(cls):
        cls.html = (REPO / "docs" / "index.html").read_text(
            encoding="utf-8")
        cls.app = (REPO / "docs" / "app.js").read_text(
            encoding="utf-8")
        cls.rd = RD_JS.read_text(encoding="utf-8")
        # Whitespace-normalized view for phrase assertions across wrapped lines.
        cls.flat = " ".join(cls.html.split())

    def test_plan_copy_verbatim(self):
        self.assertIn(
            "We'll invoice you by email before the first charge", self.flat)
        self.assertIn("No card needed now", self.html)
        self.assertIn("First month free for founding", self.html)

    def test_activate_trial_button(self):
        self.assertIn('id="activate-trial"', self.html)
        self.assertIn(">Activate trial</button>", self.html)

    def test_no_card_fields_anywhere(self):
        self.assertNotRegex(self.html, r"card number|card-number|cvv|expiry",
                            "no payment fields — invoiced later, honestly")

    def test_tone_placeholder_matches_app_py(self):
        import sys
        sys.path.insert(0, str(REPO))
        from app import VOICE_PLACEHOLDER
        for line in VOICE_PLACEHOLDER.splitlines():
            if line.strip():
                self.assertIn(line.strip(), self.flat,
                              f"tone placeholder line missing: {line!r}")

    def test_reviews_placeholder_and_paste_guidance(self):
        self.assertIn("2 | my order was cold", self.html)
        self.assertIn("Paste your whole Google or Yelp reviews page", self.html)

    def test_zero_found_hint(self):
        self.assertIn("We could not find any reviews", self.flat)
        self.assertIn("manual lines", self.flat)

    def test_rd_js_exposes_plan_and_preview_helpers(self):
        for fn in ("planState", "activateTrial", "previewSummaries",
                   "parsePaste"):
            self.assertIn(fn, self.rd)
        self.assertIn("founding", self.rd)
        self.assertIn("trial", self.rd)

    def test_app_js_wires_gate_preview_and_honest_draft_note(self):
        self.assertIn("rd.planState", self.app)
        self.assertIn("rd.activateTrial", self.app)
        self.assertIn("rd.previewSummaries", self.app)

    def test_app_js_wires_draft_flow(self):
        """T21e: placeholder replaced by the hosted draft flow."""
        self.assertNotIn("Drafting service connects in the next build step.",
                         self.app)
        self.assertIn("window.rdDraft", self.app)
        self.assertIn("requestDrafts", self.app)
        self.assertIn("'service.json?t=' + Date.now()", self.app)
        self.assertIn("service offline", self.app)

    def test_draft_button_starts_locked(self):
        self.assertRegex(
            self.html, r'id="draft-button"[^>]*disabled',
            "drafting locked until trial activation")


if __name__ == "__main__":
    unittest.main()
