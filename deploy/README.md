# replydesk API bridge — deploy

Deploys the replydesk JSON bridge (`POST /api/draft`, `GET /api/health`) to the
Oracle A1 host behind Caddy.

1. Put a real `.env` (copy of `.env.example` with the real key) next to this directory.
2. From the oracle-cloud repo: `.\infra\deploy.ps1 -Name replydesk-api -Source ..\replydesk\deploy`
3. DNS prerequisite: `api.replydeskhq.tech` A record → host public IP (HTTPS is automatic).
4. Verify: `docker compose ps` shows `healthy`; `curl https://api.replydeskhq.tech/api/health` → `{"ok": true}`.

The accounts DB persists in the named volume `replydesk-api-data` (mounted at
`/app/data`); backups: `docker run --rm -v replydesk-api-data:/data -v "$PWD":/backup alpine tar czf /backup/accounts-backup.tar.gz -C /data .`.
