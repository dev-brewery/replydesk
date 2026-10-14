#!/usr/bin/env bash
# replydesk session tunnel (T23, ARCHITECTURE §12) — git-bash mirror of
# tools/run_tunnel.ps1. ACCOUNTLESS cloudflared quick tunnel: no sign-in,
# no account, no credentials anywhere. The binary lives in out/ (gitignored).
#
# Usage: tools/run_tunnel.sh          start bridge + quick tunnel
#        tools/run_tunnel.sh stop    write service.json unavailable (after
#                                    Ctrl-C stopped the processes)
set -u
cd "$(dirname "$0")/.."

PORT=8010
BIN="out/bin/cloudflared"
API_LOG="out/api-tunnel.log"
TUNNEL_LOG="out/tunnel.log"

write_service() {
    if [ -n "${2:-}" ]; then
        py -m replydesk.tunnel --status "$1" --url "$2"
    else
        py -m replydesk.tunnel --status "$1"
    fi
}

if [ "${1:-}" = "stop" ] || [ "${1:-}" = "-Stop" ]; then
    write_service unavailable
    echo "service.json set to unavailable."
    exit 0
fi

# 1. Ensure the official cloudflared release binary (anonymous one-time fetch).
case "$(uname -s)" in
    MINGW*|MSYS*) BIN="out/bin/cloudflared.exe"
                  DL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" ;;
    Darwin*)      DL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz" ;;
    *)            DL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" ;;
esac
if [ ! -x "$BIN" ]; then
    echo "downloading cloudflared (anonymous, no account)..."
    mkdir -p out/bin
    case "$DL" in
        *.tgz) curl -fsSL "$DL" -o out/bin/cfd.tgz \
               && tar -xzf out/bin/cfd.tgz -C out/bin cloudflared \
               && rm out/bin/cfd.tgz ;;
        *)     curl -fsSL "$DL" -o "$BIN" ;;
    esac
    if [ ! -x "$BIN" ]; then
        echo "error: could not download cloudflared; tunnel not started." >&2
        py -m replydesk.tunnel --status unavailable
        exit 1
    fi
fi

# 2. Start the API bridge unless it already answers on $PORT (loopback only).
if ! curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
    py app.py --serve-api --port "$PORT" >"$API_LOG" 2>&1 &
    BRIDGE=$!
    echo "bridge starting on 127.0.0.1:$PORT (pid $BRIDGE, log $API_LOG)"
    sleep 3
fi

# 3. Quick tunnel, then parse the printed trycloudflare URL from its log.
"$BIN" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate >"$TUNNEL_LOG" 2>&1 &
TUNNEL=$!
URL=""
for _ in $(seq 1 30); do
    sleep 2
    URL=$(py -c "import sys; from replydesk.tunnel import parse_tunnel_url; \
u = parse_tunnel_url(open('$TUNNEL_LOG', encoding='utf-8', errors='replace').read()); \
print(u if u else '')")
    [ -n "$URL" ] && break
    kill -0 "$TUNNEL" 2>/dev/null || break
done

if [ -z "$URL" ]; then
    echo "error: no trycloudflare URL appeared; tunnel not live." >&2
    py -m replydesk.tunnel --status unavailable
    kill "$TUNNEL" 2>/dev/null
    exit 1
fi

# 4. Flip the SPA pointer live, then stay up until Ctrl-C.
py -m replydesk.tunnel --status live --url "$URL"
echo "tunnel live: $URL  (Ctrl-C to stop, then: tools/run_tunnel.sh stop)"
trap 'kill "$TUNNEL" 2>/dev/null; py -m replydesk.tunnel --status unavailable' INT TERM
wait "$TUNNEL"
py -m replydesk.tunnel --status unavailable
