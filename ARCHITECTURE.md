# replydesk — Architecture

Design source: `PROJECTGUIDELINES.md` (owner-maintained, wins on conflict). This file is
the builder's contract: the file map, module signatures, and behavioral rules below are
binding for every task in `TASKS.md`. No application code lives here.

Python 3.12 (`py`), standard library only (zero third-party dependencies planned).
Whole test suite runs offline: `py -m unittest discover -s tests`.

---

## 1. Final file map

```
replydesk/                  # python package
  __init__.py
  model.py                  # dataclasses + enums (no logic beyond helpers)
  toneguide.py              # parse/validate owner tone guide text
  paste_parse.py            # T19: parse a manual-lines or raw page paste -> Reviews
  triage.py                 # deterministic triage rules (A2/A3)
  verifier.py               # A5 fact-grounding check (pure, deterministic)
  draft.py                  # drafting pipeline: prompt -> verify -> retry -> fallback
  llm.py                    # LLMClient protocol, HttpLLM, FixtureLLM, .env loader
  render.py                 # RunResult -> standalone HTML (no server needed)
  fixtures/
    __init__.py             # FIXTURE_DATE, demo loader, demo_run()
    demo/                   # committed demo fixture set (T11; identity ruled D1)
      demo_profile.json     #   single source of the demo business identity
      tone_guide.md         #   demo tone guide (voice + facts)
      reviews.json          #   8 synthetic reviews, dates <= FIXTURE_DATE
      canned_drafts.json    #   offline "model" replies, keyed by review_id
app.py                      # local web UI (stdlib http.server), default offline;
                            # --serve-api starts the §12 JSON bridge instead
replydesk/api.py            # T22: /api/draft bridge: CORS allowlist, request caps,
                            # runresult_json serializer (shared with build_demo)
tests/                      # offline suite; network always mocked; inline neutral literals
tools/
  build_demo.py             # regenerate docs/ demo output from fixtures (deterministic)
  refresh_canned_drafts.py  # online: replace canned drafts with a real model run (T15)
  final_audit.py            # fresh-clone offline sim + privacy-pattern scan (T18)
  gh-token-to-env.ps1       # kit tool (owner-run)
  screenshot.sh / trim_png.py  # kit tools
  run_tunnel.ps1 / .sh      # T23: cloudflared quick-tunnel start + service.json writer
  TUNNEL.md                 #   session runbook (bridge -> tunnel -> commit -> push)
docs/                       # GitHub Pages root
  index.html                #   recorded no-JS demo page (§8; untouched by T21+)
  demo_run.json             #   committed fixture output
  CNAME, *.png              #   custom domain + post screenshots
  app/                      #   T21: hosted product SPA (§11) — vanilla JS allowed
    index.html              #     markup + inline CSS + UI wiring
    rd.js                   #     pure logic ports: parse/triage/template + auth helpers
    service.json            #     T23: {"status","url"} tunnel pointer (committed)
kit files                   # AGENTS.md, PROJECTGUIDELINES.md, ACCEPTANCE_CRITERIA.md,
                            # PROJECT.md, IMPLEMENTATIONPLAN.md, JOURNAL.md, TASKS.md,
                            # ARCHITECTURE.md, POST_DRAFT.md, POST_TEMPLATE.md,
                            # CHECKLIST.md, LICENSE, .env.example, .gitignore,
                            # .gitattributes, hooks/, .pi/, .privacy-patterns.example
out/                        # gitignored: orchestrator briefs + sub-agent stdout +
                            # out/bin/cloudflared binary (T23; never committed)
```

Not in the map (out of scope, guidelines §3 as amended 2026-10-14): auto-posting,
scraping, a hosted backend beyond the session-window bridge of §12, any payment
collection (no card form, no provider — founding trial gate only), partner
integrations beyond the .tech domain. Accounts exist as the browser-local sign-up +
trial gate of §11 exactly as the amendment rules; there is no server-side account
store.

---

## 2. Data model and public signatures

### `replydesk/model.py`

```python
class TriageCategory(Enum):      # THANK_YOU | FIX_IT | NEEDS_HUMAN
class DraftSource(Enum):         # MODEL | MODEL_RETRY | TEMPLATE

@dataclass(frozen=True)
class Review:
    review_id: str               # stable synthetic id, e.g. "r1"
    stars: int                   # 1..5
    text: str

@dataclass(frozen=True)
class ToneGuide:
    voice: str                   # free text: how the owner talks
    facts: tuple[str, ...]       # bullet facts the owner stands behind (may be empty)

@dataclass(frozen=True)
class BusinessProfile:
    name: str                    # demo business (single source: demo_profile.json, D1)
    kind: str                    # e.g. shop type
    city: str                    # fictional place

@dataclass(frozen=True)
class TriageDecision:
    review: Review
    category: TriageCategory
    reason: str                  # human-readable, names the matched rule

@dataclass(frozen=True)
class DraftResult:
    review_id: str
    text: str
    source: DraftSource
    verified: bool
    verifier_notes: tuple[str, ...]   # violations or (), also used for offline/error notes

@dataclass(frozen=True)
class RunResult:
    profile: BusinessProfile
    tone_guide: ToneGuide
    decisions: tuple[TriageDecision, ...]
    drafts: tuple[DraftResult, ...]   # only for non-NEEDS_HUMAN reviews (A3)
    generated_on: date                # FIXTURE_DATE for demo/offline runs
```

### `replydesk/toneguide.py`

```python
class ToneGuideError(ValueError): ...
def parse_tone_guide(text: str) -> ToneGuide
```

Owner-entered plain text with two optional headings; lenient format:

```
# Voice
How I talk... (any prose; may include sample replies)
# Facts I'll stand behind
- we open at 7am
- free refill on the large drip
```

No headings at all → everything is voice, facts empty (verifier gets stricter, which is
safe). Empty/whitespace-only input raises `ToneGuideError`. Bullets under the facts
heading become `facts`; prose there is split on sentence ends. Keep the parser ~40 lines.

### `replydesk/paste_parse.py` (T19)

```python
def parse_paste(text: str) -> list[Review]
# also owns parse_reviews / ReviewsFormatError (moved from app.py, re-exported there)
```

Owner paste parsing, from the owner's 2026-10-14 product ruling (manual per-review
paste is not a payable flow — the user pastes a whole reviews page once). One
function accepts either shape:

- **Manual lines** — every non-blank line matches `5 | text`: the strict manual
  parser applies, behavior and errors unchanged (its single implementation moves
  here from `app.py`, which re-exports both names — existing callers/tests stay
  green).
- **Page copy** — anything else: a heuristic, **never-raising** parse of a
  plain-text browser copy of a Google Business reviews dialog or a Yelp reviews
  page. This is parsing, not scraping (out-of-scope guard): no network, no
  platform APIs — the human copies the text; the parser runs locally, in-memory.
  - Segments are anchored on a **star rating**: a glyph run (★/☆/⭐; halves floor
    to the lower whole star, clamped to 1–5) or a conservative numeric form
    (`4/5`, `4 out of 5`, `Rated 4/5`). Text runs from after the anchor to the
    next anchor; lines before the anchor in a segment (reviewer name, relative or
    calendar date — "2 days ago", "a week ago", "Oct 12") are scaffolding:
    recognized to help splitting, then **dropped** — they never enter
    `Review.text`, so no untraceable date/name tokens ride into drafts. Dates are
    parser input only, never stored on `Review`; the pinned `FIXTURE_DATE` rules
    are untouched.
  - Known noise (owner-response markers, friend/review counts, UI strings such as
    share/help prompts) is dropped via pattern tables. `STAR_`, `DATE_`, and
    `NOISE_` patterns live in one auditable block at module top, like
    `triage.py`'s rule table.
  - A segment without a star anchor, or without usable text after scaffolding, is
    discarded — unknown segments are ignored; the parse never crashes. Fewer than
    one usable review → `[]` (the caller falls back, below).
  - `review_id` is `p1, p2, …` in document order.

### `replydesk/triage.py`

```python
def triage(review: Review) -> TriageDecision
def triage_all(reviews: Iterable[Review]) -> list[TriageDecision]
```

### `replydesk/verifier.py`

```python
@dataclass(frozen=True)
class Verification:
    passed: bool
    violations: tuple[str, ...]   # e.g. ("untraceable commitment: 'refund'",)

def verify_draft(draft_text: str, *, tone_guide: ToneGuide, review: Review,
                 profile: BusinessProfile) -> Verification
```

### `replydesk/llm.py`

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, key: str, max_tokens: int) -> str

class HttpLLM:                   # OpenAI-compatible /chat/completions via urllib.request
    def __init__(self, base_url: str, model: str, api_key: str = "",
                 timeout: float = 300.0, attempts: int = 3): ...

class FixtureLLM:                # offline: dict[review_id -> canned completion]
    def __init__(self, mapping: Mapping[str, str]): ...

def load_env_config(env_path: str) -> dict   # LLM_BASE_URL / LLM_MODEL / LLM_API_KEY
```

`key` carries the review_id for draft calls and `assist:{review_id}` for triage-assist
calls (§5): `FixtureLLM` looks completions up by it; `HttpLLM` uses it only for error
messages. `load_env_config` is called **only** in online mode (§6).

### `replydesk/draft.py`

```python
FALLBACK_LABEL = "[Template reply - edit before posting]"   # exact wording up to builder, must start with "[Template"
TRIAGE_ASSIST_SYSTEM: str       # §5 triage-assist classifier prompt (core, D5-B)

def template_reply(decision: TriageDecision, profile: BusinessProfile) -> str

def run(tone_guide: ToneGuide, profile: BusinessProfile,
        reviews: Iterable[Review], client: LLMClient, *, today: date) -> RunResult
```

### `replydesk/render.py`

```python
def render_run(run: RunResult, *, title: str = "replydesk", demo: bool = False) -> str
```

One standalone HTML page (inline CSS, no JS, no external assets): per review a card with
star rating, review text, triage badge + reason; drafts in copyable `<textarea>` with
verifier status and source label; `NEEDS_HUMAN` cards show the reason and **no** draft
box (A3). All user/model text HTML-escaped. `demo=True` adds a "recorded offline run"
banner. Used by `app.py` and `tools/build_demo.py`.

### `replydesk/fixtures/__init__.py`

```python
FIXTURE_DATE = date(2026, 10, 12)          # pinned; all fixture review dates <= this

def load_demo_fixtures() -> tuple[BusinessProfile, ToneGuide, list[Review], dict[str, str]]
def demo_run() -> RunResult                # full offline pipeline over demo fixtures
```

### `app.py`

```python
def parse_reviews(text: str) -> list[Review]   # moved to paste_parse.py; re-exported here
def main(argv=None) -> None                    # argparse: --demo, --online, --port, --host
```

Stdlib `http.server` on `127.0.0.1` (loopback default; committed code never contains a
real hostname). **Three-step self-explaining flow (T20):** `GET /` renders the form
under a plain-words step header — *1. paste the page & describe your voice · 2. we
sort and draft · 3. copy out what you like* — with the explicit line "no account,
nothing stored, nothing posted without you" and paste guidance (paste the whole
Google/Yelp reviews page exactly as copied, or one `5 | text` line per review);
`POST /preview` parses via `parse_paste` and shows the found-reviews count plus
stars/text excerpts with a confirm action (no JS: hidden form fields re-carry tone
guide and raw paste — stateless); `POST /run` re-parses (idempotent), runs the
pipeline, and re-renders the form plus results. A paste yielding no usable review
re-renders the form with a manual-lines fallback hint — no dead ends. `--demo`
serves the fixture run read-only. Modes: **offline** (default; triage runs, drafts
come straight from the labeled template path with an "offline mode" note; never
touches `.env`), **demo** (fixtures via `FixtureLLM`), **online** (`--online`; reads
`.env` via `load_env_config` → `HttpLLM`, 300 s timeout, labeled template fallback on
any client error), and **serve-api** (`--serve-api`; runs the `replydesk/api.py`
bridge of §12 instead of the form UI — implies the online client; uses the same
`--host/--port/--env` arguments).

### `replydesk/api.py` (T22)

```python
ALLOWED_ORIGINS = ("https://replydeskhq.tech", "https://dev-brewery.github.io")
CAPS = {"MAX_BODY_BYTES": 262_144, "MAX_TONE_CHARS": 4_000, "MAX_REVIEWS": 20,
        "MAX_REVIEW_CHARS": 2_000, "MAX_PROFILE_CHARS": 60}   # one auditable table

def runresult_json(run, *, note: str = "") -> str
    # the demo_run.json schema (tools/build_demo.demo_run_json becomes a thin
    # wrapper; committed docs/ output stays byte-identical) + "note" banner field
    # (present only when non-empty)

def make_api_server(host: str, port: int, client) -> ThreadingHTTPServer
```

Full endpoint contract in §12.

---

## 3. Data flow

```
            owner paste                      committed fixtures (docs/demo)
                 │                                      │
        ┌────────▼────────┐                    ┌────────▼─────────┐
        │ app.py form     │                    │ fixtures/demo/*  │
        └────────┬────────┘                    └────────┬─────────┘
                 │ paste_parse.parse_paste / load_demo_fixtures     │
                 ▼                                                │
        found-reviews preview (T20: count + excerpts; confirm)     │
                 ▼                                                ▼
        ToneGuide, list[Review]  ──► triage.triage_all ──► TriageDecision per review
                 │                        │
                 │                        ▼
                 │            triage assist (§5, core; rides the same client):
                 │            each THANK_YOU decision consulted once — a
                 │            well-formed "fix-it|reason" flips it to FIX_IT;
                 │            any other outcome leaves it unchanged
                 │                        │
                 │          NEEDS_HUMAN ──┼──► no draft, reason only (A3)
                 │                        ▼
                 │            draft.run: prompt (tone guide + profile + review
                 │            + category) ─► LLMClient.complete (Http or Fixture)
                 │                        ▼
                 │            verifier.verify_draft ── fail ─► retry once with
                 │                        │                    verifier feedback
                 │                        ▼                        │ fail again
                 │                     pass                       ▼
                 │                        │              clearly labeled template
                 ▼                        ▼
                 └──────────────► RunResult ─► render.render_run ─► HTML
                                                                │
                        local UI (app.py) ◄──────────────────────┤
                                                                 ▼
                                            tools/build_demo.py ─► docs/index.html
                                                                 + docs/demo_run.json
                                                                 → GitHub Pages (A8)
```

Online and offline share the pipeline; only the `LLMClient` differs. Any `HttpLLM`
transport error after retries becomes a labeled template draft with the failure noted —
the app never blocks on the network.

---

## 4. Triage rules (A2/A3)

Triage is **deterministic and auditable** — a false "safe" on a legal threat is the
worst failure mode, so rules, not a model, decide `NEEDS_HUMAN`. (A **core** LLM
triage-assist — owner ruling D5-B, 2026-10-13 — is consulted only *after* this table
returns a THANK_YOU decision, i.e. only at the group-6 star-rating fall-through, and
may only flip it to fix-it; it can never un-flag, pre-empt, or delay needs-a-human.
Spec in §5.)

Ordered rule groups, first match wins; `reason` names the matched group and pattern:

1. **needs-a-human — legal:** lawyer, attorney, sue, suing, court, legal action,
   small claims, cease and desist.
2. **needs-a-human — safety/health:** food poisoning, sick after, got sick, illness,
   injury, injured, ambulance, ER, hospital, allergic reaction, health department,
   hazard, blood, glass in, hair in my food, mold.
3. **needs-a-human — refund dispute:** refund, money back, charged twice, double
   charged, chargeback, dispute the charge, credit card dispute.
4. **needs-a-human — personal:** discriminat*, racist, sexist, homophobic,
   harassment/assault words, bereavement/family-distress mentions
   (my mother passed, funeral), references to a staff member by name
   (quoted name + "the [role] named"/"spoke to [A-Z name]").
5. **fix-it:** stars <= 3, or complaint patterns regardless of stars
   (broken, cold, late, rude, wrong order, never arrived, dirty, overcharged,
   ignored, cancelled).
6. **thank-you:** stars >= 4 without complaint patterns.

Patterns are lowercase regexes matched case-insensitively; every pattern group and the
priority order live in one dict at the top of `triage.py` so tests and the post can
quote them. Ambiguity resolves toward the more cautious category.

---

## 5. LLM prompt outline (A4/A6)

Default model: **GLM-5.3-Flash** via any OpenAI-compatible endpoint (§10 item 3).
Call policy everywhere: explicit `max_tokens`, temperature 0.3, timeout 300 s, up to 3
transport attempts, `thinking=low` via `extra_body` where the endpoint supports it.
`FixtureLLM` ignores policy knobs — same interface, zero network.
Token budgets (amended 2026-10-14 from live-smoke data, glm-5.3-flash thinking=low
via the owner's endpoint): the reasoning pass consumes ~70–400 completion tokens
before any reply text, so a draft budget of 400 starved the reply
(`finish_reason=length`, empty `content`) while **800** stops clean (~200-token
completion → verified 40–120-word reply); the assist budget of 100 starved
identically while **512** stops clean — hence draft/retry `max_tokens=800`,
assist `max_tokens=512`. Aligned with this, an empty `content` in an
otherwise-OK response is treated as a retryable failure by `HttpLLM` (raises
`LLMError`; landed with T14's fix) and the verifier rejects empty drafts — no
pipeline path can emit an empty reply.

**Draft prompt (the core one).**
- *System:* "You ghostwrite review replies as the owner of {profile.name}, a
  {profile.kind} in {profile.city}. Match this voice exactly: {tone_guide.voice}.
  Facts you may use, and the only facts you may use: {tone_guide.facts}, plus anything
  the review itself says and the star rating. Never invent promises, discounts, names,
  policies, times or prices. 40–120 words. Plain text only — no markdown, no emoji
  unless the voice shows them, no sign-off unless the voice has one. Output only the
  reply."
- *User:* triage category with guidance — thank-you: "warm thanks, echo one specific
  detail from the review"; fix-it: "name the problem, own it, no excuses, offer only
  next steps the facts allow" — then "Rating: {stars}/5" and the review text verbatim.
  `key=review.review_id`, `max_tokens=800`.
- *Retry:* identical, plus the verifier violations: "Your previous draft contained
  unverified claims: {violations}. Rewrite without them." `max_tokens=800`.

**Triage-assist prompt (core — owner ruling D5-B, 2026-10-13).** The deterministic
table of §4 always runs first, in full. The assist is consulted exactly when the
table falls through to star rating into THANK_YOU (group 6: ≥4 stars, no pattern
matched — the only reachable THANK_YOU), once per such review, via the same
`LLMClient` as drafting: `complete(TRIAGE_ASSIST_SYSTEM, review.text,
key="assist:"+review_id, max_tokens=512)`. *System:* classifier into thank-you/fix-it
only — needs-a-human is not in its vocabulary; the deterministic table is the
escalation authority. *User:* the review text verbatim. Output contract: one line,
`category|one-line reason`, category ∈ {thank-you, fix-it}.

Binding behavior:
- Only a well-formed `fix-it` outcome has any effect: the decision flips to FIX_IT
  and its `reason` names the assist and carries the model's one-line reason. The
  flip is one-way (toward the more cautious category) and steers the draft prompt
  (a flipped review drafts with fix-it guidance).
- Everything else — malformed or empty output, a `needs-a-human` token, an
  `LLMError`, a fixture miss — leaves the deterministic decision unchanged. No
  assist-level retry (`HttpLLM`'s transport attempts already apply); the assist
  never blocks, never crashes the run, never drafts text, and never reaches the
  verifier.
- FIX_IT and NEEDS_HUMAN decisions are never consulted, so the assist can never
  move a review out of, or block entry into, needs-a-human (guardrails of D5-B).

Wiring (consultation point): inside `draft.run()`, immediately after `triage_all`
and before the drafting loop — no signature change. The one client argument yields
all three behaviors with no mode branches: **online** (`HttpLLM`) = real assist;
**demo** (`FixtureLLM`) = canned assist when the fixture set carries an `assist:`
entry, deterministic result otherwise; **offline** (no working network client) =
assist silently skipped, deterministic result stands. Offline and demo modes never
read `.env` and never open a socket for the assist (§7; §10 item 5). The §5 call
policy applies (temperature 0.3, 300 s timeout, `thinking=low` via `extra_body`
where supported).

**Tone-guide steering** happens before any of this: the guide is parsed once per run
and injected verbatim into every system prompt, so every reply sounds like the same
person (guidelines §3 core loop 1).

---

## 6. Verifier rules (A5) — the invention check

**Invented fact (definition, binding).** A draft contains an invented fact if it
contains any *fact token* that is not traceable to a **source text**.

- **Source texts:** tone guide (voice + facts), the review's own text, the business
  profile fields (name/kind/city), and the review's star rating.
- **Fact tokens (three kinds, all checked):**
  1. **Numbers** — digits, percents, prices, clock times, durations ("10%", "$4",
     "7am", "48 hours", "three").
  2. **Names** — capitalized tokens that are not sentence-initial courtesy words.
     Courtesy stoplist (I, I'm, We, We're, Thanks, Hi, Hello, Please, Sorry, OK, and
     sentence starts generally) is exempt; everything else capitalized must trace.
  3. **Commitments/policies** — fixed phrase list: we'll, we will, promise, guarantee,
     refund, discount, free, on the house, voucher, coupon, comp, replace, remake,
     % off, next time, come back, call us, email us, reach out, stop by.
- **Traceable** = the token (case-insensitive) occurs in a source text. A commitment is
  sanctioned only by the *same commitment word* appearing in the tone guide or review
  (tone guide fact "we honor refunds" sanctions refund language; nothing else does).
- Template replies are exempt (built from safe strings + profile + review echo).

The check is pure stdlib (regex + sets), deterministic, and returns human-readable
violations ("untraceable commitment: 'refund'", "untraceable number: '30%'").

**Retry policy (binding).** Verify every model draft → fail → one retry with the
violations in the prompt → fail again → replace with `template_reply()`, clearly
labeled: the draft text *starts with* a visible marker like
`[Template reply - edit before posting]`, `source=TEMPLATE`, and the card shows why
(verification failed / model unreachable). The label must survive rendering verbatim.
`DraftResult.source` records `MODEL` / `MODEL_RETRY` / `TEMPLATE` for the UI and tests.

Two as-built clarifications (T08): `template_reply()` returns the unlabeled body and
`run()` prepends `FALLBACK_LABEL` — the draft-text-starts-with-the-marker invariant
holds while the body alone stays verifier-clean. An `LLMError` from the *retry* call
(not only the first) also falls back to the labeled template — the pipeline never
blocks on the client.

---

## 7. Offline, caching, and fixture strategy (A7/A9)

- **Pinned fixture date: 2026-10-12.** Every demo fixture review is dated on or before
  it; `demo_run()` and all committed demo output are stamped with it, so regeneration
  is byte-deterministic (same fixtures in, same HTML out).
- **Demo fixture set** (`replydesk/fixtures/demo/`, written in T11; identity ruled
  D1, 2026-10-13): 8 synthetic reviews — 3 thank-you, 3 fix-it, 2 needs-a-human
  (one legal-flavored, one refund) — named "Ridgeline Plumbing", a plumbing
  contractor in the fictional town of Cedar Falls, with `demo_profile.json` as the
  single source of that identity. Reviews are
  written to exercise every triage group and the verifier (at least one fix-it whose
  canned draft contains a sanctioned commitment, so the demo shows verification
  passing; A5's retry/fallback is exercised in tests with crafted bad drafts).
- **`FixtureLLM`** serves `canned_drafts.json` (keyed by review_id). Initially
  hand-authored by the builder; T15 optionally regenerates them from a real GLM-5.3-Flash
  run once the endpoint exists. The verifier runs on canned drafts too.
- **Triage-assist fixture outcomes (optional, graceful).** `canned_drafts.json` may
  also carry `"assist:{review_id}"` entries whose values are `category|one-line
  reason` strings, served by `FixtureLLM` under the same key namespace — zero new
  plumbing. A missing entry raises inside the consult and the deterministic decision
  stands. Demo judgment (D5-B, stated): the committed demo **includes** assist
  outcomes for its thank-you reviews — the assist is core scope, and a recorded run
  that silently skipped it would under-represent the app; canned entries stand in
  for the model exactly as canned drafts already do, under the same "recorded
  offline run" banner. T15's real-run refresh replaces them with genuine assist
  outputs when it runs. Determinism holds either way (committed fixtures in, same
  bytes out).
- **Paste-parser fixtures (T19).** Committed fixtures for `paste_parse` are
  synthetic Google-shape and Yelp-shape dumps — fictional reviewers, fictional
  content, structurally shaped like real page copies (A10). A real-shape sample
  captured from a public page may live only in gitignored `out/` for local
  validation; it is never committed. Relative/calendar dates inside paste text
  are parser input only — dropped before `Review` exists — so the pinned-date
  rule above is untouched by T19/T20.
- **Offline mode never reads local config** (§10 item 5): no code path reachable from
  offline/demo mode opens `.env`; only `--online` calls `load_env_config`.
- **Network policy:** every `HttpLLM` call has the 300 s timeout and transport retries;
  after that the pipeline falls back to a labeled template — there is no code path that
  blocks on or crashes from the network. The test suite mocks all transport (patch
  `urllib.request.urlopen`); no test reads or requires `.env`.
- **Caching:** no disk cache. `FixtureLLM` *is* the fixture fallback; within one app
  session `HttpLLM` may memoize identical (system, user) pairs in memory only. `cache/`
  stays gitignored regardless.

## 8. GitHub Pages demo (A8)

`tools/build_demo.py` (stdlib, offline): load demo fixtures → `demo_run()` → write
`docs/index.html` (self-contained: inline CSS, embedded results, demo banner, no JS, no
external fetches — renders identically opened locally or on Pages) and
`docs/demo_run.json` (the committed fixture output, for anyone auditing the demo).
Pages serves `/docs` on `main`; the post links `https://replydeskhq.tech/` with the
`dev-brewery.github.io/replydesk/` fallback until DNS lands. Screenshots for the post
come from this page and the app UI via `tools/screenshot.sh` only (binary-safe; kit
`.gitattributes` already guards PNG bytes).

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `GITHUB_TOKEN` missing → no repo/push/Pages (§10 Q2) | Remote tasks T13/T17 conditional and last-ish; everything through T12 runs and is committed locally; post draft carries the github.io fallback URL. |
| Demo identity pick pending (§10 Q1) | Single-source `demo_profile.json`; only T11/T12 wait; tests use neutral inline literals; orchestrator escalates pick before Wed AM. |
| Builder session timeout (600 s) | Tasks sized ~10 min; one task, one commit; a timed-out builder gets a "finish + report" brief. |
| LLM endpoint absent by Thu (§10 Q3) | First-user session degrades gracefully to offline mode (still exercises tone guide, triage, template fallback); post describes it honestly. |
| Verifier false positives annoy the owner | Violations are shown in the UI, one retry with feedback, then a clearly labeled editable template — never a dead end. |
| Week-1 failure modes (image corruption, location leaks, weekday drift) | Kit rules already in force: binary via `cp`/`screenshot.sh`, `.gitattributes` binary attrs, pre-commit privacy guard (never bypassed), calendar pre-verified in §8. |
| Custom-domain DNS misses publish (§10 Q4) | Post links the github.io URL as fallback; domain swap is a one-line edit + re-push. |
| Core triage-assist adds one LLM call per thank-you review (latency, failure surface) | Single call, `max_tokens=512`, no assist-level retry; malformed output / error / fixture miss → deterministic result stands; offline and demo never consult the network (§5, §7). |
| Heuristic page-paste parser mis-reads a real page copy (T19) | Anchor on star ratings only; conservative numeric forms; scaffolding (names/dates) and noise dropped, never injected into `Review.text`; <1 usable review → manual-lines fallback hint (no dead end); synthetic Google/Yelp-shape tests plus local validation against a gitignored real-shape sample; worst case = manual lines, which still work. |
| cloudflared absent on this box; quick-tunnel download blocked (T23) | One-time anonymous fetch of the official release binary inside `run_tunnel.*`; failure → honest `{"status":"unavailable"}` + non-zero exit; the SPA's offline path (§11) keeps the hosted app usable; nothing blocks the post. |
| GitHub Pages edge-caches `service.json` (~10 min) and rebuilds lazily | Session runbook (`tools/TUNNEL.md`) starts the tunnel ≥ 15 min before the session; SPA cache-busts the fetch (`service.json?t=<now>`); URL rotation rides the same commit → push → rebuild cycle. |
| Tunnel URL is public and unauthenticated (T23) | Request caps (§12), loopback-only bind, ephemeral unguessable trycloudflare URL, short session window, key stays server-side in `.env`; CORS constrains browsers only and is framed honestly as such. |
| JS ports (`rd.js`) drift from their Python counterparts | Ports copy the pattern tables verbatim; node tests run the same synthetic shapes as the Python suite (parity is the acceptance bar); server re-validates caps; server-side decisions are authoritative whenever the service is up. |
| Browser-local accounts read as a security claim | Verbatim honest copy at sign-up (§11); no security claims anywhere; SPA holds no key material — generation is server-side or clearly-labeled template. |
| Worst-case bridge latency (20 reviews × retry ladder) exceeds SPA patience | SPA aborts at 420 s and degrades to the labeled template path with the offline note (never a dead end); runbook suggests ≤ 15 reviews per run; observed live latency ~22 s/review. |
| T24 needs a real browser from the builder session | Browser automation is available to sessions (used for page captures); if unavailable, the builder reports, the orchestrator drives the browser, and the builder commits the artifacts — one commit either way. |

## 10. Pending owner determinations wired into this design

1. Demo business identity → `replydesk/fixtures/demo/demo_profile.json` only (T11).
2. `GITHUB_TOKEN` → gates T13 (repo/push/Pages) and T15's re-push.
3. LLM endpoint + key for `.env` → gates T14/T14a/T15 online runs (code lands mocked either way).
4. `replydeskhq.tech` DNS → gates T17 (domain verification); fallback URL everywhere.
5. First-user logistics + Sat publish slot → schedule only; no code impact.
6. **§3 amendment (2026-10-14) is itself the owner ruling** for T21–T24: sign-up
   mandatory, first user on a hosted URL, existing repo/machine/endpoint only,
   founding-trial billing, no new accounts/services/sign-ins. **No further owner
   determination gates the build.** Architect discretions exercised inside that
   ruling (reversible, on record, superseded by the T22d owner ruling): SPA at
   `/app/` with the recorded demo kept at `/` — the product was later moved to
   the domain root and the recorded demo to `/demo/`; CORS allowlist extended with the
   `dev-brewery.github.io` Pages origin (testing + fallback; one-line removal);
   PBKDF2 100 000 iterations (tunable constant); SPA draft textareas editable
   (product behavior; the recorded demo page stays read-only).

---

## 11. Hosted product SPA — `docs/` domain root (§3 amendment; T21; rehomed T22d)

The owner ruling (guidelines §3, amended 2026-10-14): sign-up is mandatory; the first
user's run happens on a hosted URL; only the existing repo (GitHub + Pages at
replydeskhq.tech), this machine, and the existing z.ai endpoint may be used. The SPA
is the fastest honest build inside those constraints.

**Routing (T22d owner ruling):** the SPA is the product and lives at the **domain
root** — Pages serves `docs/index.html` at `https://replydeskhq.tech/` (and the
github.io fallback). The recorded offline demo moved to `docs/demo/`, served at
`/demo/`; the product header links to it. `tools/build_demo.py` writes only
`docs/demo/` output and never touches the product files.

**Files.**

```
docs/index.html       # single page: inline CSS, no frameworks, no build step, no
                      # external CDNs/assets; view switching; loads rd.js relatively
docs/rd.js            # pure logic (no DOM): parser/triage/template ports + auth and
                      # card-render helpers; runs under node (module.exports) and
                      # browser (window.rd) for the §11 test harness
docs/service.json     # T23: {"status":"available","url":"https://…trycloudflare…"}
                      # or {"status":"unavailable"} — committed; public by design
```

The SPA's only network activity: same-origin `service.json` (cache-busted,
`service.json?t=<now>`) and, when it says `available`, the `/api/draft` POST to the
URL it carries (§12). `index.html` and `rd.js` contain no absolute URLs and no
key/endpoint material — the tunnel origin is data, not code.

### `rd.js` contract — ports, not rewrites

Each port mirrors its Python counterpart's behavior and pattern tables (tables at
module top, like `triage.py`):

- `parsePaste(text)` → `[{review_id, stars, text}]` — port of
  `paste_parse.parse_paste`: manual `N |` lines (same error messages, thrown as an
  `Error` named ReviewsFormatError-equivalent) and never-raising page mode — glyph
  runs ★/☆/⭐ with Google private-use **U+E838 as a full star**, row fillers
  U+E8DC/U+E80D/U+E5D4/U+E88E neutral, ½ floors down, conservative numeric anchors
  (`4/5`, `4 out of 5`, `Rated 4/5`), scaffolding (relative + calendar dates,
  2–4 title-case names) dropped, noise table (owner-response, UI strings, counts,
  badges) dropped, trailing-noise rule, `[]` on nothing usable, ids `p1, p2, …`.
- `triageReview(review)` → `{category, reason}` — port of the **deterministic**
  `triage.py` table only (§4, incl. trade/service staff roles; the LLM assist does
  not exist client-side). Used by the offline path; when the service is up, the
  server's decisions are authoritative.
- `templateReply(decision, profile)` + `FALLBACK_LABEL` — port of
  `draft.template_reply` (same neutral strings + profile/review echo; the caller
  prepends the label, mirroring `run()`).
- auth helpers: `hashPassword(password, saltHex)` — WebCrypto PBKDF2-SHA-256,
  100 000 iterations, 16-byte salt, 32-byte key, hex out (`crypto.subtle` exists in
  all Pages-served browsers and node ≥ 19); `equalHex` constant-time compare;
  account store over an injected storage shim (`localStorage` in the browser).

**Tests (offline):** `tests/js/*.test.js` run under node's built-in runner
(`node --test tests/js/`) from `tests/test_spa_js.py` via subprocess — **skipped,
not failed, when `node` is absent**. Parity is the acceptance bar: the same neutral
synthetic Google/Yelp-shape inputs as the Python suite produce the same
stars/text/category/template output in JS.

### SPA flow (views inside one page)

1. **Sign up / log in** — name, email (shape-checked), password (≥ 8 chars);
   duplicate email rejected; login failure shows one generic message. Accounts in
   `localStorage` (`rd_accounts`: email → {name, salt, hash}); session flag
   `rd_session`; log out clears the session only. **Honest copy at sign-up
   (verbatim): "Your account lives in this browser — we'll move it to the service
   when we launch."** Browser-local auth is convenience, not a security boundary;
   the SPA never claims otherwise.
2. **Plan gate** — card: "Founding plan — $9/month. First month free for founding
   members." Button **Activate trial** → sets `trialActivatedOn` on the account →
   generation enabled. Sub-line (verbatim): "We'll invoice you by email before the
   first charge. No card needed now." No card form anywhere (§3 amendment:
   invoiced later; no provider exists inside the constraint set).
3. **Workspace** — tone-guide textarea with `app.py`'s exact headings hint and
   placeholder text; three optional one-line business fields (name / kind / city,
   ≤ 60 chars each, defaulted to `app.py`'s neutral default profile — the fields
   steer the draft prompt's profile slot); reviews paste box with the page-paste
   guidance; live **found-reviews preview** (count + stars + first-line excerpts)
   via `parsePaste`; zero found → the manual-lines fallback hint (T20's copy).
4. **Draft replies** (enabled only when signed in + trial active) — fetch
   `service.json?t=<now>`; on `available`, POST `{tone, profile, reviews}` to
   `<url>/api/draft` (JSON; AbortController timeout **420 000 ms**); render the
   response as cards in `render.py`'s visual language: stars (★/☆), triage badges
   + reasons, draft textareas **editable** (product behavior — the owner edits
   before copying; the recorded demo page stays read-only), source labels
   (MODEL / MODEL RETRY / TEMPLATE) + verifier status, `needs_human` cards show
   the reason and **no** draft box (A3); every user/model string HTML-escaped.
   Card building lives in `rd.js` as pure string helpers (`renderCards`) joined to
   the client-side reviews by `review_id` — the API response never echoes review
   text back. On `unavailable`, fetch failure, or timeout: the **offline path** —
   `triageReview` + labeled `templateReply` per non-human review, with the note
   (verbatim): "Service offline — replies below are editable templates." Never a
   dead end.

The SPA performs **no generation locally** and holds no key material: generation is
the §12 bridge or clearly-labeled templates.

---

## 12. Generation bridge + session tunnel (T22/T23)

**`app.py --serve-api`** (existing `--host/--port/--env` args; runbook uses
`--port 8787`, loopback bind) starts a `ThreadingHTTPServer` from
`replydesk/api.py` running the existing online pipeline. `--serve-api` implies the
online client via `online_client()`; if the client cannot be built, the server
still starts and every `/api/draft` responds 503 `{"error": "service unavailable"}`
— the bridge never crashes on configuration.

**`POST /api/draft`** — request JSON:
`{tone: str, profile?: {name, kind, city}, reviews: [{review_id, stars, text}]}`
(`review_id` matches `^[a-z0-9-]{1,16}$`, preserved verbatim so the SPA can join;
reviews arrive pre-parsed by the SPA's `parsePaste`, so the previewed set and the
drafted set cannot drift — the server re-validates shape and caps regardless).
Validate against the `CAPS` table (§2): violations → 400/413 JSON errors naming the
cap; user text is never echoed in errors. Valid request → the unchanged spine:
`parse_tone_guide` → `triage_all` (+ assist per §5) → `draft.run` →
`runresult_json`. Any unexpected exception → 500 JSON naming only the failure
class. **Logs carry status + counts only — review/tone text is never logged.**

**`OPTIONS /api/draft`** — preflight: `Access-Control-Allow-Origin` echoes the
request origin **only if** it is in `ALLOWED_ORIGINS` (`https://replydeskhq.tech`,
`https://dev-brewery.github.io` — the Pages fallback origin, same service); methods
`POST, OPTIONS`; headers `Content-Type`; max-age 600. No wildcard, no credentials.

**Timeouts and load.** Each `HttpLLM` call keeps the §5 policy (300 s, ≤ 3 transport
attempts). `MAX_REVIEWS = 20` bounds a request; observed live latency is
~22 s/review, so a 10–15-review run completes in minutes; the SPA's 420 s abort
covers the practical window (theoretical worst case is larger — the runbook
suggests ≤ 15 reviews per run; degradation is the labeled template path, never a
crash or a hang without an answer).

**Honest CORS note.** The allowlist constrains browsers, not scripts; the endpoint's
real guards are the caps, the loopback bind, the unguessable ephemeral tunnel URL,
and the short session window. The API key stays in `.env` on this box and never
appears in any response or log.

**Session tunnel (T23).** `tools/run_tunnel.ps1` (primary; `.sh` mirror):
1. ensure the cloudflared binary at `out/bin/cloudflared[.exe]` (gitignored; if
   absent, **download the official release binary — a one-time anonymous fetch, no
   account, no sign-in**; quick tunnels are accountless by design; on download
   failure write `{"status":"unavailable"}` and exit non-zero with a clear message);
2. start the bridge (`py app.py --serve-api --port 8787`) unless that port already
   answers;
3. run `cloudflared tunnel --url http://127.0.0.1:8787 --no-autoupdate` and capture
   the printed `https://<random>.trycloudflare.com` URL;
4. write `docs/service.json` — `{"status":"available","url":…}` on success,
   `{"status":"unavailable"}` on any failure; a `-Stop` mode writes unavailable.

`tools/TUNNEL.md` is the runbook: start tunnel → builder commits `service.json` →
orchestrator push → wait out the Pages rebuild + ~10-min edge cache (**start ≥ 15 min
before the session**) → verify `replydeskhq.tech/` shows the live service →
session → flip to `unavailable` → commit + push. The trycloudflare URL is public and
ephemeral by design (it dies with the process) and carries no owner-infrastructure
details; the pre-commit privacy guard applies to every commit as always.
