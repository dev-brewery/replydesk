# replydesk — Agent Wiring

A review-reply desk for small businesses: paste reviews, triage them, draft replies in the owner's own voice for the DEV Hacktoberfest Week 2 "Side Hustle" challenge.
**Source of truth: `PROJECTGUIDELINES.md` (owner-maintained).** `ARCHITECTURE.md` is the
design, `TASKS.md` the build plan, `IMPLEMENTATIONPLAN.md` the calendar gates. If any file
disagrees with the guidelines, the guidelines win until Michael changes them.

## Roles

| Role | Who | Model | Charter |
|---|---|---|---|
| **Owner** | Michael (human) | — | All determinations (scope, standards, priorities, §10 questions), real-world testing, final approval. Decision rights are his alone; see standing rules. |
| **Orchestrator** | pi session | GLM-5.3, thinking: max | `.pi/skills/orchestrator/` — task briefs from `TASKS.md`, launches builder sessions, verifies acceptance criteria, records outcomes in `JOURNAL.md`, guards scope and the post deadline. Never writes application code, never commits. |
| **Architect** | pi session | GLM-5.3, thinking: high | `.pi/skills/architect/` — produces and maintains `ARCHITECTURE.md` + `TASKS.md` per guidelines §9. Never writes application code. |
| **Builder** | pi session | GLM-5.3-flash, thinking: low | `.pi/skills/builder/` — writes all code, tests, and commits, one `TASKS.md` task at a time. The only role that touches git in this repo. |

## Activation

All agent-role models run direct against the **z.ai** provider (`zai` in pi's catalog).
Load the charter before acting in a role:

- Architect: `pi --model zai/glm-5.3:high` then `/skill:architect`
- Builder: `pi --model zai/glm-5.3-flash:low` then `/skill:builder`
- Orchestrator: `pi --model zai/glm-5.3:max` then `/skill:orchestrator`

Project-local skills load only after the project is trusted. The first pi session in this
repo prompts for trust; approve it and run `/trust` to persist the decision.

## Delegation protocol (orchestrator-driven)

The owner is hands-off for day-to-day execution. The orchestrator launches sub-agents
non-interactively and verifies their output:

```
pi -p -a --no-skills --model <model> --name "<role>-<order>" @.pi/skills/<role>/SKILL.md @out/brief-<order>.md
```

- `-p` — print mode: one shot, result to stdout, captured by the orchestrator.
- `-a` — approves project-local resources for the run (`.pi/skills/` is trust-gated
  in non-interactive mode).
- `--no-skills` + `@<charter>` — attaches the role charter deterministically
  (skill auto-discovery is nondeterministic for delegation; validated in Week 1).
- **Briefs are files** (`out/brief-<order>.md`, gitignored), never inline shell
  strings — inline briefs broke on shell quoting in Week 1.
- Sub-agents never ask questions; blockers are reported in stdout and journaled.
- Timeouts: 600 s. A timed-out builder that already committed gets a short
  "finish + report" brief, not a redo.
- Cadence: brief → build → verify → accept → journal + tracker → next brief.
  One task, one commit.
- Owner-required, non-delegable actions stay flagged in `JOURNAL.md`: the real-world
  test and final post approval.

## Standing rules (all roles)

1. Surface owner-level determinations as options with trade-offs and wait for
   Michael's call; own any deviation immediately, without technicalities.
2. Role boundaries are hard. Architect and orchestrator never write application code.
   Only the builder commits; every commit is authored by the builder model.
3. One task, one commit, tests in the same task, network always mocked.
4. Privacy: no real location, LAN address, hostname, or secret ever enters the repo —
   not in code, fixtures, docs, journal, screenshots, or commit messages. The
   pre-commit guard (`hooks/`) enforces it; never bypass it with `--no-verify`.
5. Course-correct protocol for any role: stop → re-read `PROJECTGUIDELINES.md` →
   realign → await direction.
6. The published DEV post is the deliverable. Nothing delays it past the internal
   deadline. If scope must shrink, cut in the §8 order.
