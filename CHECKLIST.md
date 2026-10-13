# Checklist

## Preflight (day before launch)
- [ ] `GITHUB_TOKEN` in the kit's `.env` (run `tools/gh-token-to-env.ps1` in a normal
      PowerShell window, **with `-NoProfile`**, if missing). Check:
      `GH_TOKEN=$(grep -m1 '^GITHUB_TOKEN=' .env | cut -d= -f2- | tr -d '\r') gh api user --jq .login` → `dev-brewery`.
- [ ] z.ai key valid; one `pi -p` smoke call per charter (`@file` attachment).
- [ ] `py --version` → 3.12.x.
- [ ] `.privacy-patterns` is current (real place names, coordinates at 2–4 decimals,
      LAN prefixes, hostnames, real timezone if it narrows the location).
- [ ] DEV logged in, in the Chrome the DevTools MCP drives.
- [ ] Calendar printed with weekdays for the whole week.

## Launch day
- [ ] Read the theme, rules, template, partner list, exact deadline. Paste them into guidelines §1.
- [ ] Ideation: 3 candidates, scored on judging weights + hard filters (real-world
      testable by Thu · Pages-deployable · no private data · partner fit). Owner picks.
- [ ] Repo name free: `gh repo view dev-brewery/<name>` → not found.
- [ ] Repo from the kit (see README), `git config core.hooksPath hooks`, placeholders filled.
- [ ] Privacy guard test: stage a file with a pattern from `.privacy-patterns` → commit blocked.
- [ ] Create GitHub repo **public** early (`gh repo create dev-brewery/<name> --public --source . --remote origin`), push `main`, enable Pages from `/docs` on `main`.
- [ ] `POST_DRAFT.md` created from `POST_TEMPLATE.md`.

## Screenshots
- [ ] Only via `tools/screenshot.sh <html> <out.png>` — never copy images through a text tool.
- [ ] Open every PNG and look at it before committing: demo location only, no real data.
- [ ] `file docs/*.png` reports `PNG image data`.

## Publish (DEV editor via Chrome DevTools MCP)
- [ ] `dev.to/new`: title, tags (type into the tag box with a trailing comma), body from `POST_DRAFT.md`.
- [ ] Owner clicks Publish (or approves the click).
- [ ] Mirror the live body back into `POST_DRAFT.md`; builder commits it.

## Post-publish verification (public API — no key needed)
- [ ] `curl -s https://dev.to/api/articles/devbrewery/<slug>` → `published_at` set,
      `tag_list` correct, body starts with the submission line, embed renders (`ltag-github` in `body_html`).
- [ ] On the live page, every `#article-body img` has `naturalWidth > 0`.
- [ ] Demo link opens; repo is public; default branch `main`.
