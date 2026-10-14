# replydesk: Implementation Plan

## Progress tracker

Orchestrator-maintained. Updated at every task acceptance; committed with the next
builder commit (brief → build → verify → accept → journal + tracker → next brief).
Only the builder commits.

| Item | What | Status | Commit |
|---|---|---|---|
| T01 | Scaffold + LICENSE + first commit of whole tree | ✅ | 678e93a |
| T02 | `model.py` dataclasses + enums | ✅ | 809e2b5 |
| T03 | Fixtures package (`FIXTURE_DATE`, demo loader) | ✅ | 77efab5 |
| T04 | `toneguide.py` parser | ✅ | b0d9225 |
| T05 | `triage.py` deterministic rules | ✅ | 9699ffa |
| T06 | `verifier.py` invention check | ✅ | c04871f |
| T07 | `llm.py` clients + config loader | ✅ | ecf776e |
| T08 | `draft.py` pipeline (verify → retry → fallback) | ✅ | 50b50cb |
| T09 | `render.py` HTML output | ✅ | e6fa893 |
| T10 | `app.py` local web UI | ✅ | d8194dd |
| T11 | Demo fixture set (identity RULED: Ridgeline Plumbing, Cedar Falls) | ✅ | 206a9a1 |
| T12 | `tools/build_demo.py` + committed `docs/` demo | ✅ | 3700035 |
| T13 | GitHub repo + push + Pages — owner ruled D7-B: he runs the token script himself; unblocks on his timing | ✅ live | (remote-only) |
| T14 | Online path (`--online`, `HttpLLM`) | ✅ live-verified | fb56b36, 7cdabb1, 904d4b8, 8e08331 |
| T14a | Triage assist (core, D5-B) — consult + dedicated unit tests | ✅ | 206a9a1, 5268488 |
| T15 | Refresh canned drafts from real run | ✅ | 90cbc12 |
| T16 | Screenshots into `docs/` | ⏳ | |
| T17 | Custom domain replydeskhq.tech — D8-A ruled, records set by owner | ✅ live | cdd4c30, ffb5cc3 |
| T18 | Final offline + privacy audit | ⏳ Fri | |
| T19 | Page-paste parser (Google/Yelp page copy or manual lines) | ✅ | 6d34f14, 9f5ea3c |
| T20 | Self-explaining UI (page-paste flow + found-reviews preview) | ✅ | cfce68a |
| T21a-e | Hosted SPA: parser port, signup/session, plan gate+workspace, ports, draft flow (+4 live fixes) | ✅ live | 1fa9131…8d5261c |
| T22 | API bridge + parallel drafting (T22b/c) | ✅ live | cd07aaf, 0e954e5 |
| T23 | Tunnel tooling + live run (service.json live) | ✅ live | 0993722, b209407 |
| T24 | Hosted e2e verification | ✅ (screenshots pending) | orchestrator-driven |
| T16 | Screenshots into `docs/` | ⏳ today | |
| ARCH | `ARCHITECTURE.md` + `TASKS.md` produced (architect-1) | ✅ | rides T01 |

**STATE:** Thu Oct 14 ~05:15. **THE HOSTED SIGN-UP PRODUCT IS LIVE at https://replydeskhq.tech/app/ and PROVEN END-TO-END in a real browser** (signup → founding-trial activation → page-paste → preview → live verified GLM-5.3-Flash drafts via accountless tunnel). 230 tests green; remote = local (8d5261c); bridge + tunnel running. Today: T24/T16 screenshots, T18 audit, post rewrite, D10; evening: first user (owner recruits). Publish: Sat 1 PM PDT target / 6 PM hard stop.

---

This file sequences the build into calendar gates so every MUST item is complete before
publish day, leaving Saturday for read-and-publish only. It does not replace
`PROJECTGUIDELINES.md` (source of truth), `ARCHITECTURE.md`, or `TASKS.md`.

**Anchors (weekdays verified; launch was Tue, so the kit's Mon gate compresses into Tue):**
1. **Thu Oct 15, evening** — real-world test / first-user session (needs the online path working by then).
2. **Fri Oct 16, EOD** — all MUSTs pass, post complete.
3. **Sat Oct 17, 1:00 PM PDT target / 6:00 PM PDT hard stop** (D2-B) — publish. Buffer: Sat evening + all Sun.

## Phase overview

| # | Phase | When | Exit criteria (gate) |
|---|---|---|---|
| 0 | Theme → idea → architecture | Tue Oct 13 (AM) | Idea picked; §3–§5 written; `ARCHITECTURE.md` + `TASKS.md`; post skeleton exists |
| 1 | Skeleton & offline spine | Tue Oct 13 (PM) | First commit made; offline demo stub runs from fixtures (A1 on track) |
| 2 | Core build | Wed Oct 14 | Core loop works offline; **Pages demo live** (A8, pending GITHUB_TOKEN) |
| 3 | Online path + AI core | Thu Oct 15 | Online path + verifier/fallback (A5, A6); app MUSTs pass |
| 4 | Real-world test / first user | Thu Oct 15 evening | Session done and logged (or honestly recorded as not done) — B1 |
| 5 | Evidence & post | Fri Oct 16 | Screenshots via `tools/screenshot.sh`; post complete; stretch stops 8 PM owner-local |
| 6 | Publish | Sat Oct 17 | Published; post-publish checks in `CHECKLIST.md` pass |

## If behind schedule

Cut in the guidelines §8 order: stretch → partner integration → agent session → demo
polish. **Never cut the post.**
