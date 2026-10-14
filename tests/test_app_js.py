"""T21b tests for docs/app/rd.js auth helpers — node-driven, offline.

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
RD_JS = REPO / "docs" / "app" / "rd.js"

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
        ):
            self.assertIn(marker, output)


if __name__ == "__main__":
    unittest.main()
