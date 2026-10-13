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

Blocked-on-owner register: **T11** (demo identity, §10 Q1) · **T13** (GITHUB_TOKEN,
§10 Q2) · **T15** (endpoint, §10 Q3) · **T17** (DNS, §10 Q4). Everything else runs
unblocked today.

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
| T15 | Refresh canned drafts from a real run | T11, T14 | **owner Q3** | A7, A8 |
| T16 | Screenshots of demo + app UI into `docs/` | T10, T12 | — | D4, D5 |
| T17 | Custom domain `replydeskhq.tech` | T13 | **owner Q4** | A8 |
| T18 | Final offline + privacy audit (`tools/final_audit.py`) | T12 | — | A7, A9, A10 |

Ordering rationale (guidelines §9): offline demo spine T01–T12 lands before anything
remote; the A5 verifier + fallback (T06/T08) lands before Thursday's first-user
session; online work T14+ comes after the offline spine is proven; nothing delays the
post past Saturday.

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

## T11 — Demo fixture set — **BLOCKED on owner identity pick (§10 Q1)**

- **Goal:** Write `replydesk/fixtures/demo/`: `demo_profile.json` (the **single**
  place the demo business name/kind/city live — the owner's pick), `tone_guide.md`
  (voice + 3–5 facts, at least one sanctioned commitment so the demo shows a
  verified commitment), `reviews.json` (8 reviews dated ≤ 2026-10-12: 3 thank-you,
  3 fix-it, 2 needs-a-human — one legal-flavored, one refund), `canned_drafts.json`
  (one hand-authored draft per non-human review, each passing the verifier).
  Fictional everything; no real names/places (A10). *Do not start before the
  orchestrator brief states the owner's pick.*
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

## T15 — Refresh canned drafts from a real run — **BLOCKED on endpoint (§10 Q3)**

- **Goal:** `tools/refresh_canned_drafts.py`: online `demo_run()` over the demo
  fixtures → verifier-checked drafts written back to `canned_drafts.json` →
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
