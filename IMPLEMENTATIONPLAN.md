# replydesk: Implementation Plan

## Progress tracker

Orchestrator-maintained. Updated at every task acceptance; committed with the next
builder commit (brief → build → verify → accept → journal + tracker → next brief).
Only the builder commits.

| Item | What | Status | Commit |
|---|---|---|---|
| T01 | Scaffold + LICENSE + first commit of whole tree | 🔄 briefed | |
| T02 | `model.py` dataclasses + enums | ⏳ | |
| T03 | Fixtures package (`FIXTURE_DATE`, demo loader) | ⏳ | |
| T04 | `toneguide.py` parser | ⏳ | |
| T05 | `triage.py` deterministic rules | ⏳ | |
| T06 | `verifier.py` invention check | ⏳ | |
| T07 | `llm.py` clients + config loader | ⏳ | |
| T08 | `draft.py` pipeline (verify → retry → fallback) | ⏳ | |
| T09 | `render.py` HTML output | ⏳ | |
| T10 | `app.py` local web UI | ⏳ | |
| T11 | Demo fixture set — **blocked: owner Q1 (identity)** | 🔒 | |
| T12 | `tools/build_demo.py` + committed `docs/` demo | ⏳ | |
| T13 | GitHub repo + push + Pages — **blocked: owner Q2 (token)** | 🔒 | |
| T14 | Online path (`--online`, `HttpLLM`) | ⏳ | |
| T15 | Refresh canned drafts — **blocked: owner Q3 (endpoint)** | 🔒 | |
| T16 | Screenshots into `docs/` | ⏳ | |
| T17 | Custom domain replydeskhq.tech — **blocked: owner Q4 (DNS)** | 🔒 | |
| T18 | Final offline + privacy audit | ⏳ | |
| ARCH | `ARCHITECTURE.md` + `TASKS.md` produced (architect-1) | ✅ | rides T01 |

**STATE:** Tue Oct 13 PM. Architecture accepted (18 tasks, offline spine T01–T12 first). T01 in flight. GITHUB_TOKEN missing (T13+ blocked). Owner determinations pending: demo identity (T11/T12 + Wed Pages gate), token, endpoint, DNS, first-user logistics, Sat publish slot.

---

This file sequences the build into calendar gates so every MUST item is complete before
publish day, leaving Saturday for read-and-publish only. It does not replace
`PROJECTGUIDELINES.md` (source of truth), `ARCHITECTURE.md`, or `TASKS.md`.

**Anchors (weekdays verified; launch was Tue, so the kit's Mon gate compresses into Tue):**
1. **Thu Oct 15, evening** — real-world test / first-user session (needs the online path working by then).
2. **Fri Oct 16, EOD** — all MUSTs pass, post complete.
3. **Sat Oct 17, 10:00 AM PDT target / 6:00 PM PDT hard stop** — publish. Hard stop.

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
