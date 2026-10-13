#!/bin/sh
# Screenshot a local HTML file with headless Chrome, trim trailing dark rows,
# and verify the result is a real PNG.
# usage: tools/screenshot.sh <page.html> <out.png> [css-width=900] [max-css-height=8000]
# Never copy the resulting image through a text tool; commit it as-is.
set -e
html="$1"; out="$2"; w="${3:-900}"; h="${4:-8000}"
[ -f "$html" ] && [ -n "$out" ] || { echo "usage: $0 <page.html> <out.png> [width] [max-height]" >&2; exit 2; }

chrome=""
for c in "/c/Program Files/Google/Chrome/Application/chrome.exe" \
         "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
         "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"; do
  [ -x "$c" ] && { chrome="$c"; break; }
done
[ -n "$chrome" ] || { echo "no Chrome/Edge found" >&2; exit 1; }

tmp=$(mktemp -d)
abs=$(cd "$(dirname "$html")" && pwd -W 2>/dev/null || pwd)/$(basename "$html")
"$chrome" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$tmp/prof" \
  --force-device-scale-factor=2 --window-size="$w,$h" --screenshot="$tmp/raw.png" \
  "file:///$abs" >/dev/null 2>&1
py -I "$(dirname "$0")/trim_png.py" "$tmp/raw.png" "$out" 40
rm -rf "$tmp"

head -c 8 "$out" | od -An -tx1 | tr -d ' \n' | grep -q '^89504e470d0a1a0a$' \
  || { echo "FAIL: $out is not a valid PNG" >&2; exit 1; }
file "$out" 2>/dev/null || true
echo "Open and look at $out before committing: demo data only."
