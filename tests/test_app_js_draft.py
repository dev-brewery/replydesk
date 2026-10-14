"""T21e tests for the hosted draft flow in docs/app/app.js — node-driven.

Loads app.js behind a minimal DOM stub (same pattern as the other SPA tests)
and exercises the pure `window.rdDraft` builders: live RunResult rendering,
offline fallback (service not live, POST rejection), the verbatim offline
note, needs-human cards carrying no draft, and HTML escaping of review text.
Offline throughout; fetch is always a mock. Skips cleanly if node is absent.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RD_JS = REPO / "docs" / "app" / "rd.js"
APP_JS = REPO / "docs" / "app" / "app.js"
FALLBACK_LABEL = "[Template reply - edit before posting]"
OFFLINE_NOTE = ("replydesk service offline — these are editable templates; "
                "live model drafts connect when the service is up.")

DRIVER = r"""
'use strict';
const assert = require('assert');

// --- minimal DOM / browser stubs (offline; nothing real is touched) ---------
function stubEl() {
  return {
    classList: { add() {}, remove() {} },
    addEventListener() {},
    innerHTML: '', textContent: '', value: '', disabled: false,
    reset() {},
    elements: { name: { value: '' }, email: { value: '' },
                password: { value: '' } },
  };
}
globalThis.window = globalThis;
globalThis.document = { getElementById: () => stubEl() };
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };

require(process.argv[2]); // rd.js
require(process.argv[3]); // app.js — wires stubs, exposes window.rdDraft
const rd = globalThis.rd;
const app = globalThis.rdDraft;

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

const REVIEWS_TEXT = '5 | Wonderful pastries, will come again\n'
  + '2 | order arrived late and cold\n'
  + '1 | I want my money back, this is unacceptable\n';

const LIVE_RUN = {
  generated_on: '2025-01-01',
  profile: { name: 'The Corner Bakery', kind: 'bakery', city: 'Springfield' },
  decisions: [
    { review_id: 'r1', stars: 5, category: 'thank_you',
      reason: 'no rule matched; 5 stars >= 4 -> thank-you' },
    { review_id: 'r2', stars: 2, category: 'fix_it',
      reason: "complaint: matched pattern 'late'" },
    { review_id: 'r3', stars: 1, category: 'needs_human',
      reason: "refund-dispute: matched pattern 'money back'" },
  ],
  drafts: [
    { review_id: 'r1', source: 'model', verified: true, text: 'MODEL DRAFT r1' },
    { review_id: 'r2', source: 'model_retry', verified: false,
      text: 'RETRY DRAFT r2' },
  ],
};

function okJson(obj) {
  return { ok: true, json: () => Promise.resolve(obj) };
}

test('live path: service live + POST → RunResult mapped into cards', async () => {
  let called = 0;
  const fetchMock = (url, opts) => {
    called += 1;
    assert.strictEqual(url, 'https://tunnel.example/api/draft');
    assert.strictEqual(opts.method, 'POST');
    const body = JSON.parse(opts.body);
    assert.strictEqual(body.profile.name, 'The Corner Bakery');
    assert.strictEqual(body.reviews.length, 3);
    return Promise.resolve(okJson(LIVE_RUN));
  };
  const res = await app.requestDrafts({
    service: { status: 'live', url: 'https://tunnel.example' },
    fetch: fetchMock, tone: '# Voice', profile: LIVE_RUN.profile,
    reviewsText: REVIEWS_TEXT,
  });
  assert.strictEqual(called, 1);
  assert.strictEqual(res.mode, 'live');
  assert.strictEqual(res.cards.length, 3);
  const [c1, c2, c3] = res.cards;
  assert.strictEqual(c1.source, 'model');
  assert.strictEqual(c1.verified, true);
  assert.strictEqual(c1.draftText, 'MODEL DRAFT r1');
  assert.strictEqual(c2.source, 'model_retry');
  assert.strictEqual(c2.verified, false);
  assert.strictEqual(c2.draftText, 'RETRY DRAFT r2');
  // needs-human: reason carried, no draft at all
  assert.strictEqual(c3.needsHuman, true);
  assert.ok(c3.reason.includes('refund-dispute'));
  assert.strictEqual(c3.draftText, null);
  assert.strictEqual(c3.source, null);
});

test('needs-human cards render no textarea', () => {
  const el = { innerHTML: '' };
  app.renderCardsInto(el, app.buildCards(
    rd.parsePaste(REVIEWS_TEXT).reviews, LIVE_RUN, LIVE_RUN.profile));
  const boxes = el.innerHTML.split('<textarea').length - 1;
  assert.strictEqual(boxes, 2, 'only the two draftable reviews get textareas');
  assert.ok(el.innerHTML.includes('Needs a human'));
  assert.ok(el.innerHTML.includes('refund-dispute'));
});

test('source labels MODEL / MODEL RETRY / TEMPLATE appear in render', () => {
  const reviews = rd.parsePaste(REVIEWS_TEXT).reviews;
  const run = JSON.parse(JSON.stringify(LIVE_RUN));
  run.drafts[1].source = 'template';
  const el = { innerHTML: '' };
  app.renderCardsInto(el, app.buildCards(reviews, run, {}));
  assert.ok(el.innerHTML.includes('model'));
  assert.ok(el.innerHTML.includes('template'));
  assert.ok(el.innerHTML.includes('verified'));
  assert.ok(el.innerHTML.includes('unverified'));
});

test('service unavailable → offline path with labeled templates + note', async () => {
  let called = 0;
  const fetchMock = () => { called += 1; return Promise.reject(new Error('no')); };
  for (const service of [null, { status: 'unavailable', url: null },
                         { status: 'live', url: null }]) {
    const res = await app.requestDrafts({
      service, fetch: fetchMock, tone: '', profile: {},
      reviewsText: REVIEWS_TEXT,
    });
    assert.strictEqual(res.mode, 'offline');
    assert.strictEqual(called, 0, 'no network call when service is not live');
    assert.strictEqual(res.note, app.OFFLINE_NOTE);
    for (const c of res.cards) {
      if (c.needsHuman) {
        assert.strictEqual(c.draftText, null);
      } else {
        assert.strictEqual(c.source, rd.FALLBACK_LABEL);
        assert.ok(c.draftText.startsWith(rd.FALLBACK_LABEL + ' '));
        assert.strictEqual(c.verified, false);
      }
    }
  }
});

test('POST rejection → offline path (never a dead end)', async () => {
  const res = await app.requestDrafts({
    service: { status: 'live', url: 'https://tunnel.example' },
    fetch: () => Promise.reject(new Error('network down')),
    tone: '', profile: {}, reviewsText: REVIEWS_TEXT,
  });
  assert.strictEqual(res.mode, 'offline');
  assert.strictEqual(res.note, app.OFFLINE_NOTE);
  assert.ok(res.cards.every(
    c => c.needsHuman || c.source === rd.FALLBACK_LABEL));
});

test('HTTP 503 response → offline path too', async () => {
  const res = await app.requestDrafts({
    service: { status: 'live', url: 'https://tunnel.example' },
    fetch: () => Promise.resolve({ ok: false, status: 503 }),
    tone: '', profile: {}, reviewsText: REVIEWS_TEXT,
  });
  assert.strictEqual(res.mode, 'offline');
});

test('offline note text is the verbatim contract string', () => {
  assert.strictEqual(app.OFFLINE_NOTE, process.argv[4]);
});

test('profile fields are optional (defaults match app.py)', () => {
  const p = app.defaultProfile({});
  assert.deepStrictEqual(p, { name: 'my business', kind: 'local shop',
                              city: 'town' });
  assert.deepStrictEqual(app.defaultProfile(null), p);
  assert.strictEqual(app.defaultProfile({ name: 'Bakery' }).name, 'Bakery');
  assert.strictEqual(app.defaultProfile({ name: 'Bakery' }).kind, 'local shop');
});

test('review text with <script> is escaped in rendered HTML', () => {
  const reviews = [{ review_id: 'x1', stars: 2,
                     text: '<script>alert(1)</script> late order' }];
  const el = { innerHTML: '' };
  app.renderCardsInto(el, app.buildCards(reviews, null, {}));
  assert.ok(!el.innerHTML.includes('<script>'));
  assert.ok(el.innerHTML.includes('&lt;script&gt;'));
});

test('no review text survives unescaped into a textarea', () => {
  const reviews = [{ review_id: 'x1', stars: 5,
                     text: 'Great "food" & <drink> spot' }];
  const el = { innerHTML: '' };
  app.renderCardsInto(el, app.buildCards(reviews, null, {}));
  assert.ok(el.innerHTML.includes(
    'Great &quot;food&quot; &amp; &lt;drink&gt; spot'));
});

test('CDN split: stale unavailable then live → resolves live in 2 attempts', async () => {
  const configs = [{ status: 'unavailable', url: null },
                    { status: 'live', url: 'https://tunnel.example' }];
  let calls = 0;
  const svc = await app.fetchServiceConfig(
    () => Promise.resolve(okJson(configs[calls++])));
  assert.strictEqual(calls, 2);
  assert.strictEqual(svc.status, 'live');
  assert.strictEqual(svc.url, 'https://tunnel.example');
});

test('CDN split: all four attempts stale → resolves the unavailable config', async () => {
  const stale = { status: 'unavailable', url: null };
  let calls = 0;
  const svc = await app.fetchServiceConfig(() => {
    calls += 1;
    return Promise.resolve(okJson(stale));
  });
  assert.strictEqual(calls, 4);
  assert.deepStrictEqual(svc, stale);
});

test('CDN split: network error then live → resolves live', async () => {
  const live = { status: 'live', url: 'https://tunnel.example' };
  let calls = 0;
  const svc = await app.fetchServiceConfig(() => {
    if (calls++ === 0) return Promise.reject(new Error('network down'));
    return Promise.resolve(okJson(live));
  });
  assert.strictEqual(calls, 2);
  assert.deepStrictEqual(svc, live);
});

// Live root cause T21e4: browsers throw 'Illegal invocation' when a detached
// global fetch is invoked unbound. Simulate a real global-shaped fetch that
// only works when called with `this === window`, wrap it the way app.js wraps
// it (fetchBound), and prove requestDrafts works through that path.
test('bound fetch: detached global-shaped fetch works through the window wrapper', async () => {
  const strictGlobalFetch = function (url, opts) {
    assert.strictEqual(this, globalThis.window,
      'global fetch must be invoked with window as this');
    return Promise.resolve(okJson({
      generated_on: '2025-01-01', profile: {}, decisions: [], drafts: [],
    }));
  };
  const fetchBound = function () { return strictGlobalFetch.apply(window, arguments); };
  const res = await app.requestDrafts({
    service: { status: 'live', url: 'https://tunnel.example' },
    fetch: fetchBound, tone: '# Voice', profile: {},
    reviewsText: REVIEWS_TEXT,
  });
  assert.strictEqual(res.mode, 'live');
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


class AppJsDraftTests(unittest.TestCase):
    def test_draft_flow_suite(self):
        if shutil.which("node") is None:
            self.skipTest("node not available")
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "draft_driver.js"
            driver.write_text(DRIVER, encoding="utf-8")
            proc = subprocess.run(
                ["node", str(driver), str(RD_JS), str(APP_JS), OFFLINE_NOTE],
                capture_output=True, text=True, timeout=120, cwd=tmp)
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"node draft-flow suite failed:\n{output}")
        self.assertIn("ALL PASS", output)
        for marker in (
            "live path", "needs-human cards render no textarea",
            "source labels", "service unavailable", "POST rejection",
            "HTTP 503", "verbatim contract", "profile fields are optional",
            "<script> is escaped", "no review text survives unescaped",
            "resolves live in 2 attempts", "resolves the unavailable config",
            "network error then live",
            "bound fetch",
        ):
            self.assertIn(marker, output)

    def test_service_json_shape(self):
        import json
        svc = json.loads((REPO / "docs" / "app" / "service.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(set(svc), {"status", "url"})
        self.assertIn(svc["status"], {"live", "unavailable"})
        self.assertIsNone(svc["url"]) if svc["status"] == "unavailable" \
            else self.assertTrue(svc["url"].startswith("https://"))

    def test_index_html_has_draft_cards_container(self):
        html = (REPO / "docs" / "app" / "index.html").read_text(
            encoding="utf-8")
        self.assertIn('id="draft-cards"', html)

    def test_app_js_cache_busts_service_json(self):
        app = APP_JS.read_text(encoding="utf-8")
        self.assertIn("'service.json?t=' + Date.now()", app)
        self.assertIn("service offline", app)

    def test_app_js_binds_global_fetch(self):
        """T21e4: the live handler must not pass the detached global fetch."""
        app = APP_JS.read_text(encoding="utf-8")
        self.assertIn("fetch.apply(window, arguments)", app)
        self.assertIn("fetchServiceConfig(fetchBound)", app)
        self.assertIn("fetch: fetchBound", app)


if __name__ == "__main__":
    unittest.main()
