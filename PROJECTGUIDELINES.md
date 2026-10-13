# replydesk: Project Guidelines

A review-reply desk for small businesses: the owner pastes their Google or Yelp reviews, and an open-weight model drafts a reply to each one in the owner's own voice, flags the reviews a human must handle, and keeps a reusable tone guide so every reply sounds like the same person. Built for the DEV Hacktoberfest Week 2 "Side Hustle" challenge.

This file is the single source of truth for the project. Read it fully before planning or writing code. If anything in the codebase disagrees with this file, this file wins until Michael changes it.

---

## 1. The challenge

**DEV Hacktoberfest Open-Source AI Challenge, Week 2: "Side Hustle"**
https://dev.to/devteam/join-the-hacktoberfest-open-source-ai-challenge-side-hustle-2550-in-prizes-across-18-winners-55ba

- **Prompt (verbatim, verified on the live page 2026-10-13):** "Build something with open-weight models or open-source AI that someone would actually pay for."
- **Deadline:** Sunday, Oct 18, 2026, 11:59 PM PDT (Sunday verified against a calendar).
- **Winners announced:** week of Oct 19.
- **Rules:** brand-new project built entirely inside the challenge window; repo's first commit inside the window; one submission per person. Official contest rules and eligibility on the challenge hub — owner confirms eligibility.
- **Submission:** a published DEV post on `dev.to/devbrewery` using the challenge's "Side Hustle Submission Template". Required sections (per `ACCEPTANCE_CRITERIA.md` D2): What I Built / Demo / Code / How I Built It / Why Does Open Innovation Matter? Optional (D3): My Agent Session, My First User, Prize Categories. The template body is a collapsible on the challenge page; re-verify exact headings in the DEV editor at publish time.
- **Required tags (verified on the live page):** `devchallenge`, `hf26challenge`.
- **Judging, in order of weight (verified on the live page):** Writing Quality (most heavily), Relevance to the Prompt and Theme, Creativity, Technical Execution, Use of Partner Technology (optional).
- **Bonus (verbatim):** "Bonus points if you land your first user." → acceptance item B1.
- **Partner category targeted:** Best Use of a .tech Domain — demo served at **replydeskhq.tech** (one of 17 partner categories; a project can enter every category it genuinely uses, wins once per challenge).
- **Prizes:** overall $250 + DEV++ + badge; 6 featured × $200; 11 partner × $100.

### What went wrong before, and the rules that prevent it

- **Build for a Friend:** built and drafted, **never published**. → The published post is the deliverable; the draft starts day one; internal publish deadline is a full day before the real one.
- **Week 1 (clearnight):** published, but: weekday anchors were off by one; the owner's location leaked into git history (full rewrite); screenshots were corrupted by a text-mode copy and broke in the live post; repo push and publish blocked on credentials until the last day; the field test was cancelled. → Verified calendar, pre-commit privacy guard, `.gitattributes` binary images + `tools/screenshot.sh` with validation, credentials preflighted, real-world test scheduled on day 1.
- **This week's preflight (2026-10-13):** `GITHUB_TOKEN` is **missing/invalid** — repo creation, push, Pages and the publish-day `gh` calls are blocked until the owner refreshes it. Everything local proceeds regardless.

---

## 2. Who builds what

| Role | Who | Responsibilities |
|---|---|---|
| Owner | Michael | Decisions, real-world test / first-user session, final approval |
| Architect | GLM-5.3 (thinking high) via pi on z.ai | `ARCHITECTURE.md` and `TASKS.md` (section 9) |
| Builder | pi + GLM-5.3-flash (thinking low) on z.ai | All code, tests, and commits, one small task at a time |
| Orchestrator | pi + GLM-5.3 (thinking max) on z.ai | Briefs, launches, verifies, journals. Never writes application code, never runs git |

`AGENTS.md` is the router; charters live in `.pi/skills/{architect,builder,orchestrator}/SKILL.md`.

The in-app model calls a configurable OpenAI-compatible endpoint with an optional API key; endpoint and key live only in gitignored `.env` — see `.env.example`. Default in-app model: **GLM-5.3-Flash** (open weights, MIT license).

---

## 3. What the app does

Core loop (numbered; open-source AI at the core):

1. **Tone guide.** The owner describes how they talk (or pastes a few replies they've written before). replydesk saves that as a tone guide and reuses it for every draft.
2. **Paste reviews.** The owner pastes one or more reviews, each with its star rating and text.
3. **Triage.** Each review is sorted: **thank-you**, **fix-it** (a complaint the business can address), or **needs-a-human** (legal threats, safety or health claims, refund disputes, anything personal). Needs-a-human reviews get no drafted reply, only a short note explaining why.
4. **Draft.** GLM-5.3-Flash drafts a reply for every other review in the owner's voice. Replies never invent facts: no made-up promises, discounts, names or policies that aren't in the tone guide. A strict verifier enforces this; failures are retried once, then replaced by a clearly labeled template reply.
5. **Review and copy.** The owner edits each draft and copies it out to post.

Who pays and why: local shops, cafes, salons and contractors live on their reviews but rarely answer them well. Target price ≈ $9/month per business. Because the weights are open, a business or reseller can run replydesk on its own hardware and customer reviews never have to leave it — a closed API can't offer that.

Out of scope (owner-set): auto-posting to any platform, scraping reviews, accounts/billing/hosted backend, any partner integration other than the .tech domain.

---

## 4. Data sources and constraints

| Source | Use | Constraints |
|---|---|---|
| Synthetic review fixtures (fictional business) | offline demo, tests, GitHub Pages demo | committed; pinned fixture date; no real reviews, names or locations anywhere (A10) |
| Reviews pasted by the owner at runtime | triage + drafting input | in-memory only; never written to the repo |
| Tone guide (owner-written) | steering all drafts | same |
| OpenAI-compatible LLM endpoint | triage assist + drafting | gitignored `.env` only (A6); GLM-5.3-Flash default; offline fixture fallback when absent |
| GitHub Pages | static demo hosting | renders committed fixture output (A8); served at replydeskhq.tech |

**Hard constraints (defaults, pre-answered — see §10):**
- Python 3.12 (`py` on this machine; plain `python` is 3.7). Standard library first; every dependency pinned and justified.
- **Public demo identity:** one fictional business with synthetic reviews, in a fictional place. Identity is an owner determination (§10, open question 1). No real location, business or customer name anywhere in the repo.
- Every network call has a timeout and a cached or fixture fallback. **The whole test suite runs offline** and passes with or without a local `.env` (A9).
- Keyless open data preferred. The LLM endpoint is the one configurable exception.
- Pinned fixture date for reproducible offline output (architect fixes it in fixtures).

---

## 5. Proposed file map

Proposed here; the architect finalizes it in `ARCHITECTURE.md`.

```
replydesk/          # python package: model (dataclasses), triage, toneguide,
                    # draft, verifier, llm client (offline fallback), fixtures/
app.py              # local entry point (CLI or stdlib local web UI - architect's call)
tests/              # offline suite, network mocked
docs/               # GitHub Pages root: index.html renders committed fixture output + screenshots
kit files           # AGENTS.md, .pi/skills/, PROJECTGUIDELINES.md, ACCEPTANCE_CRITERIA.md,
                    # PROJECT.md, IMPLEMENTATIONPLAN.md, JOURNAL.md, TASKS.md, ARCHITECTURE.md,
                    # POST_DRAFT.md, POST_TEMPLATE.md, CHECKLIST.md, .gitignore, .gitattributes,
                    # .env.example, hooks/, tools/
out/                # gitignored: orchestrator briefs + sub-agent stdout
```

---

## 6. Deliverable acceptance criteria

Canonical list: **`ACCEPTANCE_CRITERIA.md`** (owner-maintained). Mirrored here; if they diverge, `ACCEPTANCE_CRITERIA.md` wins.

### Submission (MUST)
- **D1.** Post published on DEV before the deadline (Sun Oct 18, 2026, 11:59 PM PDT), using the challenge's submission template and required tags.
- **D2.** Post includes every required template section: What I Built / Demo / Code / How I Built It / Why Does Open Innovation Matter?
- **D3.** Post includes optional sections: My Agent Session, My First User, Prize Categories (.tech Domain).
- **D4.** Every screenshot in the post renders on the live page.
- **D5.** The demo link opens a working demo.
- **D6.** Repo public at `dev-brewery/replydesk`; first commit inside Oct 12–18, 2026; whole project built in the window.

### App (MUST)
- **A1.** Owner can enter a tone guide and paste reviews, each with star rating + text.
- **A2.** Every review triaged: thank-you / fix-it / needs-a-human.
- **A3.** Needs-a-human reviews get no draft, only a short reason.
- **A4.** Every other review gets a draft in the voice of the tone guide.
- **A5.** No invented facts in drafts (no promises, discounts, names, policies absent from tone guide/review). A check enforces this; failing drafts retry once, then fall back to a clearly labeled template reply.
- **A6.** In-app model is GLM-5.3-Flash via a configurable OpenAI-compatible endpoint; endpoint/key only in gitignored local config.
- **A7.** Without a key, a fresh clone runs the demo offline from committed fixtures (fictional business, synthetic reviews).
- **A8.** Static GitHub Pages demo renders committed fixture output, served at replydeskhq.tech; post links it there.
- **A9.** Test suite passes offline, network mocked.
- **A10.** No real reviews, real customer/business names, secrets, real locations or personal data anywhere in git history.
- **A11.** Every commit is made by the agent.

### Bonus (SHOULD)
- **B1.** A real local business owner uses replydesk on their own reviews; the post's My First User section describes it; identity stays private.
- **B2.** Post links an exported agent session from a clean session.

---

## 7. Engineering rules for the builder

- One task, one commit, ~10 builder-minutes, ending with passing tests: `py -m unittest discover -s tests`.
- Tests in the same task as the code. Network always mocked.
- No real locations, local-config values, LAN addresses, hostnames, or personal data in code, tests, fixtures, docs, or commit messages.
- Binary files are copied with `cp`; screenshots only via `tools/screenshot.sh`.
- Commit message: one-line summary, short body, `Signed-off-by: GLM-5.3-flash (via pi)`.
- If a task can't be completed, stop and say so.

---

## 8. Timeline (times PDT; every weekday verified) — compressed one day: launch was Tue, not Mon

| When | Milestone |
|---|---|
| Mon Oct 12 | Theme read; idea picked (PROJECT.md, ACCEPTANCE_CRITERIA.md) |
| Tue Oct 14→13 | Repo from kit; guidelines §3–§5; architecture + tasks; post skeleton; T01 first commit; offline spine starts |
| Wed Oct 14 | Core build; **GitHub Pages demo live** from offline output |
| Thu Oct 15, evening | **Owner real-world test = first-user session** (needs online path working; logged as it happens) |
| Fri Oct 16 | App MUSTs verified; screenshots, post complete, agent-session slice; stretch stops 8 PM owner-local |
| **Sat Oct 17, target 10 AM, hard stop 6 PM** | **Post published. Hard stop.** (Owner clicks Publish; post-publish checks same day) |
| Sun Oct 18, 11:59 PM | Official deadline — buffer only, never the plan |

Cut order if behind: stretch → partner integration → agent session → demo polish. **Never cut the post.**

---

## 9. What the architect must produce

1. **`ARCHITECTURE.md`**: final file map; data flow; public signatures and dataclasses per module; LLM prompt outline and verifier rules (this project's LLM writes user-facing text: define what counts as an invented fact for A5, the retry policy, and the clearly-labeled template fallback); triage rules (how needs-a-human is decided); caching/offline/fixture strategy (pinned fixture date; suite offline; Pages demo from committed fixture output); Pages demo build; risks with mitigations.
2. **`TASKS.md`**: ordered tasks `T01`… with goal, files, acceptance test, AC IDs. Offline demo (A1/A7) and Pages demo (A8) as early as possible. Tasks sized ~10 builder-minutes so no session hits the 600 s timeout.

No application code in the architecture step.

---

## 10. Owner determinations

### Pre-answered defaults (settled unless Michael changes them)
1. **Data:** demo runs on a fictional business with synthetic reviews written for the project. No scraping, no real reviews (A10). Real services are optional extras behind config.
2. **Privacy:** nothing localized in the public repo. Real endpoints, coordinates, and keys live only in gitignored `.env` / local config. The privacy guard is never bypassed.
3. **LLM:** any OpenAI-compatible endpoint, optional key; default model GLM-5.3-Flash. Explicit `max_tokens` budget, 300 s timeout, retries, `thinking=low` via `extra_body` where supported.
4. **Grounding:** a strict verifier checks every drafted reply against the tone guide + review text; retry once, then a clearly labeled template fallback. The LLM never emits unverified user-facing facts.
5. **Offline:** pinned fixture date; offline mode never reads local config.
6. **Real-world test:** Thu evening — doubles as the first-user session (B1). Optional; never gates the post. Identity stays private.
7. **Publish:** Sat Oct 17, a full day before the deadline. Owner clicks Publish (or approves the click). Orchestrator never assumes owner availability Sunday.
8. **Agent session:** the DevRelay-exportable session is a fresh session in which real locations and local config are never discussed.
9. **Repo:** `dev-brewery/replydesk` — name availability check pending a valid GITHUB_TOKEN (preflight gap, see §1).

### Open questions for Michael
1. **Demo business identity** (name, type of shop, fictional city) — appears in every fixture, screenshot and the post. Options with trade-offs in `JOURNAL.md`; blocks only fixture-writing tasks, not architecture.
2. **GITHUB_TOKEN** refresh (`tools/gh-token-to-env.ps1` in a normal PowerShell, `-NoProfile`) — blocks repo creation/push/Pages; needed ideally today.
3. **LLM endpoint for the online path** — which OpenAI-compatible endpoint + key goes in `.env` (needed by Thu evening for the first-user session).
4. **replydeskhq.tech DNS** → GitHub Pages (A8; owner action at the .tech registrar; needed by Fri).
5. **First-user session logistics** — who and when Thu evening; identity stays out of the repo.
6. **Saturday publish slot** — docs assume target 10 AM PDT / hard stop 6 PM PDT; confirm the slot you'll be at the keyboard.
