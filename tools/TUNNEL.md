# replydesk session tunnel runbook (T23)

Accountless cloudflared **quick tunnel**: an anonymous binary from the official
cloudflared GitHub releases — no account, no sign-in, no credentials anywhere.
The binary lives in `out/bin/` (gitignored, never committed). The only artifact
that enters the repo is the public, ephemeral `https://<random>.trycloudflare.com`
URL in `docs/service.json`; it dies with the tunnel process and is not a secret.

## Before a live session (start ≥ 15 minutes early)

The Pages rebuild plus ~10 minutes of edge cache lag means the flipped
`service.json` is not visible on `replydeskhq.tech/` immediately.

1. `tools/run_tunnel.ps1` (or `tools/run_tunnel.sh` in git-bash). It:
   - downloads the cloudflared binary once if missing (anonymous),
   - starts the bridge (`py app.py --serve-api --port 8010`, log `out/api-tunnel.log`)
     unless the port already answers,
   - starts the quick tunnel (`cloudflared tunnel --url http://127.0.0.1:8010
     --no-autoupdate`, log `out/tunnel.log`),
   - writes `docs/service.json` = `{"status": "live", "url": "<tunnel URL>"}`
     and prints the URL.
   - Any failure (download blocked, no URL within ~60 s): writes
     `{"status": "unavailable", "url": null}` and exits non-zero.
2. Builder commits the flipped `service.json`; orchestrator pushes.
3. Wait out the Pages rebuild + edge cache (≥ 15 minutes total from push).
4. Verify: open `replydeskhq.tech/`, confirm live drafting works (a draft
   run returns MODEL-mode replies, not the offline template note).

## During the session

- Keep the console open; Ctrl-C stops cloudflared and flips `service.json`
  back to `unavailable` locally.
- Stay within the bridge caps (≤ 20 reviews/request; ≤ 15 is practical given
  ~22 s per review; the SPA aborts at 420 s).

## After the session

1. Ctrl-C the tunnel script (both bridge and cloudflared stop).
2. `tools/run_tunnel.ps1 -Stop` (or `tools/run_tunnel.sh stop`) to write
   `{"status": "unavailable", "url": null}` if it wasn't flipped already.
3. Commit + push the flipped `service.json` so the hosted app shows the
   honest offline state again.

## Judging window

The bridge + quick tunnel stay up through the winners announcement (week of
Oct 19). If the box reboots: re-run `tools/run_tunnel.ps1` (or
`tools/run_tunnel.sh`), then the builder re-commits the flipped
`docs/service.json` and the orchestrator pushes so the Pages copy updates.
