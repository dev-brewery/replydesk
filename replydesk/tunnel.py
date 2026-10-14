"""Session-tunnel helpers (T23, ARCHITECTURE §12).

Two small, offline-testable pieces the ``tools/run_tunnel.*`` scripts shell
out to, so the logic lives in tested Python instead of untestable shell:

- ``parse_tunnel_url`` — extract the ``https://<random>.trycloudflare.com``
  URL from cloudflared's quick-tunnel output (a noisy log stream).
- ``write_service_json`` — the ``docs/app/service.json`` pointer the hosted
  SPA fetches (cache-busted): ``{"status": "live", "url": ...}`` when the
  tunnel is up, ``{"status": "unavailable", "url": null}`` otherwise.

Stdlib only, no network, no ``.env`` reads — safe to import from tests and
from either script flavor (bash / PowerShell).
"""

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE_JSON_PATH = _REPO_ROOT / "docs" / "app" / "service.json"

_TUNNEL_URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")

VALID_STATUSES = ("live", "unavailable")


def parse_tunnel_url(text: str) -> str | None:
    """Return the first trycloudflare URL in cloudflared output, or None.

    Matches the real quick-tunnel format (random hyphenated subdomain);
    noise lines without a URL are ignored.
    """
    match = _TUNNEL_URL_RE.search(text)
    return match.group(0) if match else None


def write_service_json(status: str, url: str | None = None,
                       path: Path = SERVICE_JSON_PATH) -> None:
    """Write the SPA-facing service pointer as pretty-printed JSON.

    ``live`` requires a URL; ``unavailable`` forces ``url`` to ``None``.
    The tunnel URL is public and ephemeral by design — not a secret.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
    if status == "unavailable":
        url = None
    if status == "live" and not url:
        raise ValueError("status 'live' requires a tunnel url")
    payload = {"status": status, "url": url}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="write docs/app/service.json")
    parser.add_argument("--status", required=True, choices=VALID_STATUSES)
    parser.add_argument("--url", default=None)
    args = parser.parse_args(argv)
    try:
        write_service_json(args.status, args.url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
