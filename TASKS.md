# replydesk — Build Tasks

Ordered build plan for the builder role. Each task = one commit by the builder,
tests written with the code, ending green: `py -m unittest discover -s tests`
(Python 3.12 via `py`). Network is always mocked in tests; no task *requires* network
or a `.env` to pass. Module contracts live in `ARCHITECTURE.md` — read the cited
section before coding. Guidelines §7 is binding (privacy guard, binary files,
sign-off `Signed-off-by: GLM-5.3-flash (via pi)`).

Status is tracked by the orchestrator in `IMPLEMENTATIONPLAN.md`. Post/publish work
(D1–D4, B2) is scheduled there, not here; its file commits ride along with the next
builder task or a dedicated tiny brief.

Blocked-on-owner register: **T13** (GITHUB_TOKEN, §10 Q2) · **T15** (z.ai key
presence in `.env`; endpoint ruled D3-A) · **T17** (DNS, §10 Q4). T11's identity is
RULED (D1, 2026-10-13; guidelines §10 Q1). Everything else runs unblocked today.

T21a–T24 (added per the guidelines §3 amendment of 2026-10-14, brief architect-5):
**unblocked** — the amendment is itself the owner ruling (hosted sign-up product,
founding-trial gate, existing repo/machine/endpoint only). T24 executes inside the
orchestrator's live session window per `tools/TUNNEL.md` (ARCHITECTURE §12).

| ID | Task | Depends | Blocked | AC |
|---|---|---|---|---|
| T01 | Scaffold + LICENSE + first commit of the whole tree | — | — | A11, D6 |
| T02 | `model.py` dataclasses + enums | T01 | — | A1, A2 |
| T03 | Fixtures package: `FIXTURE_DATE`, demo loader | T02 | — | A7, A10 |
| T04 | `toneguide.py` parser | T02 | — | A1, A4 |
| T05 | `triage.py` deterministic rules | T02 | — | A2, A3 |
| T06 | `verifier.py` invention check | T02 | — | A5 |
| T07 | `llm.py` client + `FixtureLLM` + config loader | T02 | — | A6, A7, A9 |
| T08 | `draft.py` pipeline: verify → retry → labeled fallback | T04, T05, T06, T07 | — | A4, A5 |
| T09 | `render.py` HTML output | T08 | — | A3, A8 |
| T10 | `app.py` local web UI | T08, T09 | — | A1, A7 |
| T11 | Demo fixture set (profile/tone/reviews/canned) | T03, T08 | **owner Q1** | A7, A10 |
| T12 | `tools/build_demo.py` → committed `docs/` demo | T09, T11 | (Q1) | A7, A8 |
| T13 | GitHub repo public + push + Pages on `/docs` | T12 | **owner Q2** | D6, A8 |
| T14 | Online path: wire `HttpLLM` behind `--online` | T07, T10 | — | A6 |
| T14a | Triage assist (core): prompt + wiring behind `LLMClient` | T07 | — | A2, A6 |
| T15 | Refresh canned drafts from a real run | T11, T14 | **owner Q3** | A7, A8 |
| T16 | Screenshots of demo + app UI into `docs/` | T10, T12 | — | D4, D5 |
| T17 | Custom domain `replydeskhq.tech` | T13 | **owner Q4** | A8 |
| T18 | Final offline + privacy audit (`tools/final_audit.py`) | T12 | — | A7, A9, A10 |
| T19 | `paste_parse.py` smart page-paste parser | T10 | — | A1, A10 |
| T20 | Self-explaining UI: 3-step flow, preview, privacy copy | T19 | — | A1, A7, A9 |
| T21a | `docs/app/rd.js`: `parsePaste` JS port + node test harness | T19 | — | A1, A10 |
| T21b | SPA shell + sign-up/log-in/session (WebCrypto PBKDF2) | T21a | — | §3-AM |
| T21c | Plan gate (founding trial) + workspace + found-reviews preview | T21a, T21b | — | A1, §3-AM |
| T21d | `rd.js`: deterministic triage + template ports | T21a | — | A2, A3, A5 |
| T22 | `app.py --serve-api` JSON bridge (`replydesk/api.py`) | T14 | — | A5, A6 |
| T21e | Draft flow: `service.json` → `/api/draft` → cards; offline path | T21c, T21d, T22 | — | A4, A5, D5 |
| T23 | Tunnel tooling + `service.json` + runbook (`run_tunnel.*`, `TUNNEL.md`) | T22 | — | §3-AM, D5 |
| T24 | Hosted end-to-end verification + screenshots (synthetic account) | T21e, T23 | session | B1, D4, D5 |

Ordering rationale (guidelines §9): offline demo spine T01–T12 lands before anything
remote; the A5 verifier + fallback (T06/T08) lands before Thursday's first-user
session; online work T14+ comes after the offline spine is proven; nothing delays the
post past Saturday. T14a (owner ruling D5-B) lands right after the online path it
refines; it touches only `draft.py`/tests and depends on T07 alone, so it is
parallel-safe with render/app work. T19/T20 (owner product ruling 2026-10-14
evening: manual per-review paste is not a payable flow — both in existing scope,
no criteria changes) land before Thursday evening's first-user session; T19 is a
pure parser the app layer consumes in T20.

T21a–T24 (guidelines §3 amendment 2026-10-14, brief architect-5 — the hosted
sign-up product; contracts in ARCHITECTURE §11/§12): T21a, T21b, T21d touch only
`docs/app/` pure logic and **parallelize with T22** (`replydesk/api.py` + a small
`app.py` edit — no shared files); T21c then T21e wire the SPA serially (both edit
`docs/app/index.html`); T23 needs T22's bridge to point at; T24 runs last, inside
the live session window, as the synthetic dress rehearsal for Thursday evening's
first-user session — its screenshots double as T16's app-UI evidence. The recorded
demo page at `/` is untouched throughout (ARCHITECTURE §8 JS boundary). §3-AM = the
§3 amendment (sign-up mandatory, hosted first-user run, founding-trial gate).

---

## T01 — Scaffold + LICENSE + first commit

- **Goal:** Package skeleton, MIT `LICENSE` ("Copyright (c) 2026 replydesk
  contributors"), and the repo's **first commit containing the entire current tree**
  (kit files, guidelines, `ARCHITECTURE.md`, `TASKS.md`, `PROJECT.md`,
  `ACCEPTANCE_CRITERIA.md`, `POST_DRAFT.md`, `.env.example`, `hooks/`, `tools/`,
  `.pi/`, `.privacy-patterns.example`). Existing `.gitignore`/`.gitattributes` stay
  as-is. Nothing in `.privacy-patterns`, `.env`, or `out/` gets staged.
- **Files:** `LICENSE`, `replydesk/__init__.py`, `tests/__init__.py`, `tests/test_scaffold.py`.
- **Acceptance:** `py -m unittest discover -s tests` → 1 test (imports `replydesk`) OK;
  `git log --oneline` shows exactly 1 commit, authored/signed by the builder;
  `git status --short` clean apart from ignored paths; commit date inside Oct 12–18.

## T02 — `model.py`

- **Goal:** Dataclasses/enums exactly per ARCHITECTURE §2 (`TriageCategory`,
  `DraftSource`, `Review`, `ToneGuide`, `BusinessProfile`, `TriageDecision`,
  `DraftResult`, `RunResult`), frozen, type-hinted; no other logic.
- **Files:** `replydesk/model.py`, `tests/test_model.py`.
- **Acceptance:** Suite green; tests construct every type and assert frozen-ness and
  field names (guards downstream signature drift).

## T03 — Fixtures package

- **Goal:** `replydesk/fixtures/__init__.py` with `FIXTURE_DATE = date(2026, 10, 12)`
  (pinned; every demo review date is ≤ it) and `load_demo_fixtures()` that
  schema-validates and loads a demo directory (profile/tone/reviews/canned dicts).
  No demo fixture files are written yet (that's T11); tests point the loader at a
  temp directory of neutral synthetic files (e.g. "Sample Cafe"/"Sampletown" —
  clearly test data, not the demo identity).
- **Files:** `replydesk/fixtures/__init__.py`, `tests/test_fixtures.py`.
- **Acceptance:** Suite green offline; loader rejects a malformed directory with a
  clear error; `FIXTURE_DATE` is 2026-10-12.

## T04 — `toneguide.py`

- **Goal:** `parse_tone_guide` + `ToneGuideError` per ARCHITECTURE §2: `# Voice` and
  `# Facts I'll stand behind` sections, lenient (no headings → all voice, no facts;
  empty → error); facts become bullets/sentences.
- **Files:** `replydesk/toneguide.py`, `tests/test_toneguide.py`.
- **Acceptance:** Suite green; tests cover both headings, heading-less text, facts
  bullets, and the empty-input error.

## T05 — `triage.py`

- **Goal:** Deterministic ordered rules per ARCHITECTURE §4: needs-a-human groups
  (legal / safety-health / refund / personal) checked first, then complaint patterns,
  then star rating; pattern groups in one auditable table at module top; `reason`
  names the matched rule.
- **Files:** `replydesk/triage.py`, `tests/test_triage.py`.
- **Acceptance:** Suite green; tests hit every rule group (incl. a 5-star review with
  a complaint → fix-it, a 1-star refund demand → needs-a-human, a legal threat at any
  rating) and assert reasons are non-empty strings.

## T06 — `verifier.py`

- **Goal:** `verify_draft` per ARCHITECTURE §6: fact tokens (numbers / capitalized
  names / commitment phrases) must trace to source texts (tone guide + review +
  profile + rating); deterministic; human-readable violations.
- **Files:** `replydesk/verifier.py`, `tests/test_verifier.py`.
- **Acceptance:** Suite green; tests include: pass (all tokens trace), invented
  number ("30%"), invented commitment ("refund" nowhere sanctioned), invented name
  ("Marlene"), sanctioned commitment (tone guide says "we honor refunds" → pass),
  review-sourced name passes.

## T07 — `llm.py`

- **Goal:** `LLMClient` protocol, `FixtureLLM` (keyed by `key`), `HttpLLM`
  (urllib, JSON body, `Authorization` header when key set, `max_tokens`,
  temperature 0.3, `extra_body` thinking=low, 300 s timeout, ≤3 transport attempts,
  raises `LLMError` after), `load_env_config` (parses `.env`-style file). Offline
  code paths never call the loader.
- **Files:** `replydesk/llm.py`, `tests/test_llm.py`.
- **Acceptance:** Suite green with **`urllib.request.urlopen` patched** (success,
  retry-then-success, final failure → `LLMError`); `FixtureLLM` returns by key and
  errors clearly on a missing key; loader parses comments/blank lines. No test opens
  a socket.

## T08 — `draft.py` — the A5 pipeline

- **Goal:** `run()` + `template_reply()` per ARCHITECTURE §2/§6: triage →
  needs-a-human produces **no draft**; others prompt the client → verify → on fail
  one retry with violations in the prompt → on second fail a clearly labeled template
  (`[Template…` marker, `source=TEMPLATE`, notes say why); client exceptions
  (`LLMError`) → labeled template with "model unreachable" note; `generated_on`
  from the `today` argument.
- **Files:** `replydesk/draft.py`, `tests/test_draft.py`.
- **Acceptance:** Suite green using a stub client and `FixtureLLM`; tests cover:
  clean model draft passes first try; bad draft → retried with feedback → passes
  (`source=MODEL_RETRY`); bad twice → labeled template; raising client → labeled
  template; needs-a-human excluded from drafts; template text itself passes the
  verifier.

## T09 — `render.py`

- **Goal:** `render_run()` per ARCHITECTURE §2: standalone HTML (inline CSS, no JS,
  no external assets), review cards with rating/text/triage badge+reason, drafts in
  `<textarea>` with source + verifier status, `demo` banner flag, everything
  HTML-escaped.
- **Files:** `replydesk/render.py`, `tests/test_render.py`.
- **Acceptance:** Suite green; tests assert: escaped review text (`<script>` →
  entity), needs-a-human card contains the reason and **no** textarea, template
  label appears verbatim, no `http://`/`https://` asset links in the page.

## T10 — `app.py` local web UI

- **Goal:** Stdlib `http.server` app per ARCHITECTURE §2: `GET /` form (tone guide,
  reviews as `5 | text` lines), `POST /run` → pipeline → rendered results, `--demo`
  read-only fixture run, `--online` opt-in (loads `.env`, `HttpLLM`), default
  offline mode (triage runs; drafts come straight from the labeled template path
  with an "offline mode" note) that **never reads `.env`**; binds `127.0.0.1`.
  `parse_reviews` is a pure function.
- **Files:** `app.py`, `tests/test_app.py`.
- **Acceptance:** Suite green offline; tests cover `parse_reviews` (valid lines,
  blanks, bad rating error) and exercise the server once on an ephemeral loopback
  port (threaded `http.server` in-test; no external network); the offline run
  handler returns HTML containing triage badges.

## T11 — Demo fixture set (identity RULED 2026-10-13 — guidelines §10 Q1)

- **Goal:** Write `replydesk/fixtures/demo/`: `demo_profile.json` (the **single**
  place the demo business name/kind/city live — the owner's pick), `tone_guide.md`
  (voice + 3–5 facts, at least one sanctioned commitment so the demo shows a
  verified commitment), `reviews.json` (8 reviews dated ≤ 2026-10-12: 3 thank-you,
  3 fix-it, 2 needs-a-human — one legal-flavored, one refund), `canned_drafts.json`
  (one hand-authored draft per non-human review, each passing the verifier; plus
  `assist:{review_id}` entries per ARCHITECTURE §7 — include at least one flip to
  fix-it and one confirming thank-you). Fictional everything; no real names/places
  (A10). *Identity ruled (D1): the orchestrator's T11 brief carries it; single
  source is `demo_profile.json`.*
- **Files:** `replydesk/fixtures/demo/*`, `tests/test_demo_fixtures.py`.
- **Acceptance:** Suite green; a test loads the set, runs `demo_run()` offline, and
  asserts: 8 decisions, every non-human review has a verified draft, both
  needs-a-human reviews carry reasons and no drafts; `demo_run().generated_on ==
  FIXTURE_DATE`.

## T12 — `tools/build_demo.py` + committed `docs/` demo

- **Goal:** Offline script per ARCHITECTURE §8: fixtures → `demo_run()` → writes
  self-contained `docs/index.html` (+ demo banner, pinned-date stamp) and
  `docs/demo_run.json`; output is byte-deterministic across re-runs. Commit the
  generated files.
- **Files:** `tools/build_demo.py`, `docs/index.html`, `docs/demo_run.json`, `tests/test_build_demo.py`.
- **Acceptance:** Suite green; test runs the builder function into a temp dir and
  asserts self-containment (no external URLs, no JS fetch) and determinism
  (two runs, equal bytes); `py tools/build_demo.py` regenerates identical `docs/`
  files (builder verifies with `git diff` clean after re-run).

## T13 — GitHub repo + push + Pages — **BLOCKED on GITHUB_TOKEN (§10 Q2)**

- **Goal:** With a valid token in the environment (never committed): create
  `dev-brewery/replydesk` **public**, push `main`, enable Pages from `/docs` on
  `main`. Verify the repo name was free first. If the token is missing/invalid:
  stop and report; do not improvise.
- **Files:** none (remote operations only).
- **Acceptance (conditional):** `gh repo view dev-brewery/replydesk` → public,
  default branch `main`; `https://dev-brewery.github.io/replydesk/` returns the demo
  page (checked with the owner's browser or `curl`); repo history shows only
  builder commits (A11) with the first inside Oct 12–18 (D6).

## T14 — Online path

- **Goal:** Wire `--online` end-to-end per ARCHITECTURE §2/§5: `.env` →
  `load_env_config` → `HttpLLM` (GLM-5.3-Flash default) into `draft.run`; every
  failure mode degrades to the labeled template. No key, no endpoint string, no
  hostname ever committed (tests use a fake `.env` in a temp dir).
- **Files:** `app.py` (small edit), `replydesk/llm.py` (if gaps found), `tests/test_online_mode.py`.
- **Acceptance:** Suite green offline (transport mocked; a temp fake `.env` toggles
  the mode in tests); manual smoke against the real endpoint is the orchestrator's
  verification step, not a test.

## T14a — Triage assist (core) — thank-you → fix-it refinement

- **Goal:** Per ARCHITECTURE §5 (owner ruling D5-B): `TRIAGE_ASSIST_SYSTEM` prompt
  constant plus assist wiring inside `draft.run()` immediately after `triage_all`
  (no signature change). Consulted once per deterministic THANK_YOU decision (the
  star-rating fall-through) through the same client: `key="assist:"+review_id`,
  `max_tokens=512` (budgets amended 2026-10-14; ARCHITECTURE §5), output contract
  `category|one-line reason`. A well-formed
  `fix-it` flips the decision to FIX_IT with a reason naming the assist and the
  model's one-line reason (a flipped review then drafts with fix-it guidance);
  malformed/empty output, a `needs-a-human` token, an `LLMError`, or a fixture
  miss leaves the deterministic decision unchanged. FIX_IT/NEEDS_HUMAN reviews
  never trigger an assist call; the assist never blocks or crashes the run.
- **Depends on T07 only** (deliberately not T09/T10 — parallel-safe with
  render/app work; its table position after T14 reflects the online path it
  refines).
- **Files:** `replydesk/draft.py`, `tests/test_triage_assist.py` (test-only tweaks
  to existing T08 stubs allowed if they now see an extra assist call — say so in
  the commit), regenerated `docs/` via `py tools/build_demo.py` (offline,
  deterministic) so the committed demo reflects the assist.
- **Acceptance:** Suite green offline (stub client, no socket): thank-you +
  `fix-it|…` stub → flipped FIX_IT with assist-named reason; malformed / empty /
  `needs-a-human` output → decision unchanged; raising client → unchanged; FIX_IT
  and NEEDS_HUMAN reviews produce no assist call (stub counts calls);
  `FixtureLLM` serves a canned `assist:` entry when present and misses gracefully
  when absent; `docs/` regenerated with a clean diff on re-run. ACs A2 (triage
  outcomes stay correct), A6 (rides the configurable endpoint).

## T15 — Refresh canned drafts from a real run — **blocked on z.ai key in `.env` (endpoint ruled D3-A)**

- **Goal:** `tools/refresh_canned_drafts.py`: online `demo_run()` over the demo
  fixtures → verifier-checked drafts written back to `canned_drafts.json`
  (including its `assist:` entries, §7) →
  `tools/build_demo.py` re-run → commit updated `docs/`. Keeps the pinned date and
  determinism. Skip/stop cleanly if the endpoint is unavailable.
- **Files:** `tools/refresh_canned_drafts.py`, `replydesk/fixtures/demo/canned_drafts.json`, `docs/`.
- **Acceptance:** Suite still green offline; refreshed `demo_run()` still passes
  T11's assertions (every non-human draft verified, labels correct); `git diff`
  after a re-run without refresh is clean.

## T16 — Screenshots

- **Goal:** Demo + app screenshots for the post: only via `tools/screenshot.sh`
  (binary-safe; kit rule), then eyeball each PNG (demo content only, no real data),
  `file docs/*.png` reports `PNG image data`, copy with `cp`.
- **Files:** `docs/demo.png`, `docs/app.png` (names may match POST_DRAFT.md).
- **Acceptance:** Both PNGs committed as binaries (bytes intact in `git show`),
  open cleanly, show fictional data only.

## T17 — Custom domain — **BLOCKED on owner DNS action (§10 Q4)**

- **Goal:** After the owner points `replydeskhq.tech` at Pages: commit
  `docs/CNAME` containing `replydeskhq.tech`, re-push, verify HTTPS serves the demo;
  update `POST_DRAFT.md` fallback note if DNS is solid.
- **Files:** `docs/CNAME`, possibly `POST_DRAFT.md`.
- **Acceptance (conditional):** `https://replydeskhq.tech/` returns the demo page;
  Pages settings show the domain attached; if DNS hasn't propagated, report status
  honestly and keep the github.io link primary.

## T18 — Final audit

- **Goal:** `tools/final_audit.py` (offline): (1) copy the tracked tree to a temp
  dir **without** any `.env`/`.privacy-patterns`/`out/`, run the suite there
  (fresh-clone sim, A7/A9); (2) scan all tracked files against the privacy patterns
  (`.privacy-patterns` if present locally, else `.privacy-patterns.example` patterns)
  and exit non-zero on any hit (A10); (3) print a one-page MUST checklist summary.
- **Files:** `tools/final_audit.py`, `tests/test_final_audit.py` (unit-level: pattern
  scanner behavior).
- **Acceptance:** Suite green; `py tools/final_audit.py` exits 0 with all sections
  PASS on the final tree; scanner test proves a planted pattern is caught.

## T19 — `paste_parse.py` — smart page-paste parser

- **Goal:** `parse_paste(text) -> list[Review]` per ARCHITECTURE §2 (owner product
  ruling 2026-10-14: manual per-review paste is not a payable flow — the user
  pastes a whole reviews page once). Accepts EITHER the existing manual
  `5 | text` lines (strict behavior unchanged; the single implementation of
  `parse_reviews` / `ReviewsFormatError` moves to `paste_parse.py` and `app.py`
  re-exports both, so existing callers and tests stay green — disclose any test
  tweak in the commit) OR a raw plain-text browser copy of a Google Business
  reviews dialog / Yelp reviews page: star-anchored segmentation (glyph runs
  ★/☆/⭐, halves floor to the lower whole star; conservative numeric `4/5` forms),
  reviewer-name / relative-date / calendar-date lines recognized as scaffolding
  and dropped — never entering `Review.text`; noise (owner responses, friend
  counts, UI strings) dropped via module-top pattern tables like `triage.py`'s.
  Page mode never raises; fewer than 1 usable review → `[]`. Dates are parser
  input only, never stored on `Review` (pinned `FIXTURE_DATE` rules untouched);
  parsing is local and in-memory — not scraping (no network, no platform APIs).
- **Files:** `replydesk/paste_parse.py`, `app.py` (re-export edit only),
  `tests/test_paste_parse.py`.
- **Acceptance:** Suite green offline; tests cover: synthetic Google-shape and
  Yelp-shape dumps → correct stars + text per review; mixed garbage tolerance
  (noise/scaffolding dropped, never crashes); manual lines still parse incl.
  existing error cases; page mode returns `[]` on unusable input; date/name lines
  provably excluded from `Review.text`. (The preview that surfaces the found
  count is T20's UI; T19 proves the parser can power it.) Fixtures are SYNTHETIC
  only (A10): fictional reviewers/content, real-copy shape; the orchestrator's
  real-shape sample stays in gitignored `out/` for local validation only — if it
  is absent at build time, proceed on the synthetic spec and say so in stdout;
  never block on it, never commit it.

## T20 — Self-explaining UI pass

- **Goal:** `app.py` flow + copy per ARCHITECTURE §2: plain-words three-step header
  (1. paste the page & describe your voice — 2. we sort and draft — 3. copy out
  what you like); explicit "no account, nothing stored, nothing posted without
  you" line; paste-guidance hint; `POST /preview` found-reviews step (count +
  stars/excerpts + confirm action; hidden fields re-carry tone guide and raw
  paste — stateless, no JS) run **before** `/run` drafts; a paste yielding no
  usable review re-renders the form with a manual-lines fallback hint (no dead
  ends). Result cards stay `render.py`'s — no new framework: still stdlib, still
  offline-first, no JS.
- **Files:** `app.py`, `tests/test_app.py` (extend; a separate
  `tests/test_ui_flow.py` is fine instead).
- **Acceptance:** Suite green offline; tests assert the new copy/preview elements:
  the step header, the privacy line, the paste guidance, the preview surfacing the
  found count before drafting (T19's deferred acceptance), and the zero-found
  fallback hint; existing behavior (offline note, `[Template` labels, loopback
  bind, `.env` untouched offline) unchanged.

## T21a — `docs/app/rd.js`: `parsePaste` port + JS test harness

- **Goal:** Per ARCHITECTURE §11: create `docs/app/rd.js` — a pure-logic module (no
  DOM) that runs under node (`module.exports`) and browser (`window.rd`) — exposing
  `parsePaste(text)` as a behavior port of `paste_parse.parse_paste`: manual
  `N | text` lines (same error messages, thrown as an Error) and never-raising
  page mode — glyph anchors incl. Google private-use **U+E838** as a full star with
  U+E8DC/U+E80D/U+E5D4/U+E88E neutral fillers, ½ floors down, conservative numeric
  anchors, scaffolding (dates, 2–4 title-case names) dropped, noise table
  (owner-response, UI strings, counts, badges) dropped, trailing-noise rule, `[]`
  on nothing usable, ids `p1, p2, …`; pattern tables at module top mirroring
  `paste_parse.py`. Test harness: `tests/js/` (node `--test` files using the same
  neutral synthetic Google/Yelp-shape literals as `tests/test_paste_parse.py`) and
  `tests/test_spa_js.py` running `node --test tests/js` via subprocess, **skipping
  cleanly when `node` is absent**. No network, no DOM, no `docs/index.html` change.
- **Files:** `docs/app/rd.js`, `tests/js/parse.test.js`, `tests/test_spa_js.py`.
- **Acceptance:** Suite green offline; with node present, JS tests pass and prove
  parity with the Python parser on the shared shapes (same stars/text); without
  node they skip, not fail.

## T21b — SPA shell + sign-up/log-in/session

- **Goal:** Per ARCHITECTURE §11: `docs/app/index.html` — single page (inline CSS,
  no frameworks, no external CDNs/assets), header + views: sign up / log in /
  workspace placeholder when logged in. `rd.js` auth helpers: `hashPassword`
  (WebCrypto PBKDF2-SHA-256, 100 000 iterations, 16-byte random salt hex, 32-byte
  key hex — `crypto.subtle` exists in all Pages-served browsers and node ≥ 19),
  `equalHex` constant-time compare, account store over an injected storage shim
  (`localStorage`: `rd_accounts` email → {name, salt, hash}; session flag
  `rd_session`; log out clears the session only). Sign-up validates non-empty
  name, email shape, password ≥ 8 chars, rejects duplicate email; login failure
  shows one generic message. **Honest copy rendered at sign-up, verbatim:** "Your
  account lives in this browser — we'll move it to the service when we launch."
- **Files:** `docs/app/index.html`, `docs/app/rd.js` (extend),
  `tests/js/auth.test.js`, `tests/test_spa_shell.py`.
- **Acceptance:** Suite green; node tests cover hash determinism (same salt → same
  hex; new salt → different) and store round-trip + duplicate-email rejection via a
  Map-backed shim; Python test asserts the verbatim honest copy, the three form
  fields, no external URLs, relative `rd.js` load.

## T21c — Plan gate + workspace + found-reviews preview

- **Goal:** Per ARCHITECTURE §11: plan-gate card until activated — "Founding plan —
  $9/month. First month free for founding members." with button **Activate trial**
  (sets `trialActivatedOn` on the account) and sub-line verbatim "We'll invoice you
  by email before the first charge. No card needed now."; no card form anywhere.
  Workspace (Draft button disabled until signed in + trial): tone-guide textarea
  with `app.py`'s exact headings hint and placeholder text; three optional
  business-profile inputs (name / kind / city, 60-char cap, `app.py`'s neutral
  defaults when blank); reviews paste box with the page-paste guidance; live
  **found-reviews preview** (count + stars + first-line excerpts) via
  `rd.parsePaste`; zero found → the manual-lines fallback hint (T20's copy).
- **Files:** `docs/app/index.html` (extend), `tests/test_spa_workspace.py`.
- **Acceptance:** Suite green; Python test asserts the verbatim plan strings, the
  activate-trial gating, preview wiring (`parsePaste` referenced), the zero-found
  hint, and placeholders matching `app.py`'s; no behavior requires a server
  (browser-level behavior is T24's live check).

## T21d — `rd.js`: deterministic triage + template ports

- **Goal:** Per ARCHITECTURE §11: port the **deterministic** triage table
  (`triage.py`, ARCHITECTURE §4 — same ordered groups, same patterns incl.
  trade/service staff roles, same reasons, ambiguity → cautious) as
  `rd.triageReview(review) → {category, reason}` (categories `thank_you|fix_it|`
  `needs_human`; no LLM assist client-side), and `draft.template_reply` as
  `rd.templateReply(decision, profile)` + `rd.FALLBACK_LABEL` (same neutral
  strings; caller prepends the label). Pattern tables at module top mirroring
  `triage.py` / `draft.py`.
- **Files:** `docs/app/rd.js` (extend), `tests/js/triage.test.js`.
- **Acceptance:** Suite green; node tests mirror `tests/test_triage.py` probes
  (every rule group; 5-star complaint → fix-it; 1-star refund → needs-human;
  staff-name probe → needs-human; lowercase role mention → not) plus one golden
  template-parity case (same decision + profile → exactly the Python
  `template_reply` output for that sample).

## T21e — Draft flow: `service.json` → `/api/draft` → result cards; offline path

- **Goal:** Per ARCHITECTURE §11/§12: **Draft replies** (enabled when signed in +
  trial active): fetch same-origin `service.json?t=<now>`; if `available`, POST
  `{tone, profile, reviews}` to `<url>/api/draft` (JSON) with an AbortController
  timeout of 420 000 ms; render the response as cards in `render.py`'s visual
  language — stars, triage badges + reasons, **editable** draft textareas, source
  labels (MODEL / MODEL RETRY / TEMPLATE) + verifier status, `needs_human` cards
  show reason and no draft box (A3), all strings HTML-escaped; cards join the
  response to the client-side reviews by `review_id` (the API never echoes review
  text). On `unavailable`, fetch failure, or timeout: offline path —
  `rd.triageReview` + labeled `rd.templateReply` per non-human review with the
  verbatim note "Service offline — replies below are editable templates." Card
  building lives in `rd.js` as pure string helpers (`renderCards`) — node-testable;
  `index.html` only wires events/DOM. No absolute URLs in either file.
- **Files:** `docs/app/index.html` (extend), `docs/app/rd.js` (extend),
  `tests/js/render.test.js`, `tests/test_spa_flow.py`.
- **Acceptance:** Suite green; node tests: `renderCards` escapes `<script>` input,
  badges/labels present, needs-human card has no textarea, template label
  verbatim; Python test: `index.html`/`rd.js` contain the verbatim offline note,
  reference `service.json` with a cache-buster, and contain no absolute URLs.

## T22 — `app.py --serve-api`: JSON generation bridge

- **Goal:** Per ARCHITECTURE §12: new `replydesk/api.py` — `ALLOWED_ORIGINS`, the
  `CAPS` table (MAX_BODY_BYTES 262 144, MAX_TONE_CHARS 4 000, MAX_REVIEWS 20,
  MAX_REVIEW_CHARS 2 000, MAX_PROFILE_CHARS 60), `runresult_json(run, note="")`
  (demo_run.json schema + optional `note`; `tools/build_demo.py`'s
  `demo_run_json` becomes a thin wrapper so committed `docs/` output stays
  byte-identical), `make_api_server(host, port, client)`:
  `POST /api/draft` validates `{tone, profile?, reviews:[{review_id, stars, text}]}`
  (`review_id` matches `^[a-z0-9-]{1,16}$`, preserved) against caps (400/413 JSON
  errors naming the cap; user text never echoed) → `parse_tone_guide` →
  `draft.run` (triage + assist + verify, unchanged) → `runresult_json`; unexpected
  errors → 500 JSON naming only the failure class; `OPTIONS` preflight echoes
  allowlisted origins only (no wildcard). `app.py` gains `--serve-api` (same
  `--host/--port/--env`; implies the online client via `online_client()`; client
  unavailable → server still starts, every request 503 JSON). Logs carry status +
  counts only, never review text.
- **Files:** `replydesk/api.py`, `app.py` (small edit), `tools/build_demo.py`
  (wrapper edit), `tests/test_api.py`; regenerated `docs/` must be byte-identical
  (`git diff` clean).
- **Acceptance:** Suite green offline (in-process server on an ephemeral loopback
  port, stub client, no socket beyond loopback, no `.env` read in tests): preflight
  CORS echo; non-allowlisted origin gets no ACAO header; valid request →
  schema-correct JSON with note; each cap violation → 400/413 naming the cap;
  oversized body → 413; `client=None` → 503; `runresult_json(demo_run())`
  byte-equals `build_demo.demo_run_json(demo_run())`; `py tools/build_demo.py`
  re-run leaves `docs/` unchanged.

## T23 — Public reach: quick tunnel + `service.json` + runbook

- **Goal:** Per ARCHITECTURE §12: `tools/run_tunnel.ps1` (primary) + `run_tunnel.sh`
  mirror + `tools/TUNNEL.md`. The script: (1) ensures the cloudflared binary at
  `out/bin/cloudflared[.exe]` (gitignored; **download the official release binary
  if absent — anonymous, no account, no sign-in**; on download failure write
  `docs/app/service.json` = `{"status":"unavailable"}` and exit non-zero with a
  clear message); (2) starts the bridge (`py app.py --serve-api --port 8787`)
  unless that port already answers; (3) runs `cloudflared tunnel --url
  http://127.0.0.1:8787 --no-autoupdate`, capturing the printed
  `https://…trycloudflare.com` URL; (4) writes `docs/app/service.json`
  (`{"status":"available","url":…}` or unavailable); `-Stop` mode writes
  unavailable. `TUNNEL.md` documents the runbook incl. the **≥ 15-min lead time**
  (Pages rebuild + ~10-min edge cache) and the after-session flip to unavailable.
  Commit the initial `docs/app/service.json` as `{"status":"unavailable"}`.
- **Files:** `tools/run_tunnel.ps1`, `tools/run_tunnel.sh`, `tools/TUNNEL.md`,
  `docs/app/service.json`.
- **Acceptance:** Suite green (offline, file-level tests: script present with the
  quick-tunnel command shape and the failure→unavailable path; `service.json`
  committed as unavailable; `TUNNEL.md` names the lead time). **No test or task
  step in T23 opens a network connection or downloads anything** — the
  orchestrator runs the script in the session window. Only the public ephemeral
  URL ever enters `service.json` (privacy guard applies as always).

## T24 — Hosted end-to-end verification + screenshots (dress rehearsal)

- **Goal:** Per brief architect-5: on the **deployed** Pages URL
  (`https://replydeskhq.tech/app/`; github.io fallback acceptable), through a real
  browser session: sign up a synthetic account (fictional name/email), activate the
  trial, paste a **synthetic** page-dump (reuse the committed Google-shape fixture
  text), confirm the found-reviews preview, run Draft replies against the live
  bridge (tunnel up per `tools/TUNNEL.md`), and verify: live MODEL drafts render
  with source/verifier labels; a needs-a-human review shows its reason and no
  draft; textareas editable; the honest account/plan copy present. Capture
  screenshots **only via `tools/screenshot.sh`** (`docs/app-signup.png`,
  `docs/app-drafts.png`) — these double as T16's app-UI evidence (T16's demo-page
  screenshot remains separate). If browser automation is unavailable to the
  builder session, report it; the orchestrator drives the browser and the builder
  commits the artifacts (one commit either way). Record the tunnel end-state
  (kept `available` for Thursday evening, or flipped to `unavailable`) in the
  report.
- **Files:** `docs/app-signup.png`, `docs/app-drafts.png` (screenshot tool + `cp`).
- **Acceptance:** PNGs committed as binaries (bytes intact in `git show`),
  eyeballed, fictional data only (A10); report confirms each live check ran
  against the hosted URL; suite still green; no real reviews or real accounts
  involved anywhere.
