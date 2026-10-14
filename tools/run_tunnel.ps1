#!/usr/bin/env pwsh
# replydesk session tunnel (T23, ARCHITECTURE §12) — primary launcher, mirror
# of tools/run_tunnel.sh. ACCOUNTLESS cloudflared quick tunnel: no sign-in,
# no account, no credentials anywhere. Binary lives in out/ (gitignored).
#
# Usage: .\tools\run_tunnel.ps1           start bridge + quick tunnel
#        .\tools\run_tunnel.ps1 -Stop     write service.json unavailable

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Port = 8010
$Bin = "out\bin\cloudflared.exe"
$ApiLog = "out\api-tunnel.log"
$TunnelLog = "out\tunnel.log"

function Write-Service([string]$Status, [string]$Url) {
    if ($Url) {
        py -m replydesk.tunnel --status $Status --url $Url
    } else {
        py -m replydesk.tunnel --status $Status
    }
    if ($LASTEXITCODE -ne 0) { throw "service.json write failed" }
}

if ($args -contains "-Stop") {
    Write-Service "unavailable" $null
    Write-Host "service.json set to unavailable."
    exit 0
}

# 1. Ensure the official cloudflared release binary (anonymous one-time fetch).
if (-not (Test-Path $Bin)) {
    Write-Host "downloading cloudflared (anonymous, no account)..."
    New-Item -ItemType Directory -Force -Path "out\bin" | Out-Null
    $dl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    $tmp = "$Bin.tmp"
    try {
        Invoke-WebRequest -Uri $dl -OutFile $tmp -UseBasicParsing
        Move-Item $tmp $Bin -Force
    } catch {
        Write-Error "could not download cloudflared: $($_.Exception.Message)"
        Write-Service "unavailable" $null
        exit 1
    }
}

# 2. Start the API bridge unless it already answers on $Port (loopback only).
$bridgeUp = $false
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2
    $bridgeUp = $true
} catch {}
$bridge = $null
if (-not $bridgeUp) {
    $bridge = Start-Process -FilePath "py" -ArgumentList "app.py", "--serve-api", "--port", "$Port" `
        -RedirectStandardOutput $ApiLog -RedirectStandardError "out\api-tunnel.err.log" -PassThru -NoNewWindow
    Write-Host "bridge starting on 127.0.0.1:$Port (pid $($bridge.Id), log $ApiLog)"
    Start-Sleep -Seconds 3
}

# 3. Quick tunnel, then parse the printed trycloudflare URL from its log.
$tunnel = Start-Process -FilePath $Bin `
    -ArgumentList "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate" `
    -RedirectStandardOutput $TunnelLog -RedirectStandardError "out\tunnel.err.log" `
    -PassThru -NoNewWindow

$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if ($tunnel.HasExited) { break }
    $log = (Get-Content $TunnelLog, "out\tunnel.err.log" -Raw -ErrorAction SilentlyContinue) -join "`n"
    $parsed = $log | py -c "import sys; from replydesk.tunnel import parse_tunnel_url; u = parse_tunnel_url(sys.stdin.read()); print(u if u else '')"
    if ($parsed) { $url = ([string]$parsed).Trim(); break }
}

if (-not $url) {
    Write-Error "no trycloudflare URL appeared; tunnel not live."
    Write-Service "unavailable" $null
    try { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue } catch {}
    exit 1
}

# 4. Flip the SPA pointer live, then stay up until Ctrl-C.
Write-Service "live" $url
Write-Host "tunnel live: $url  (Ctrl-C to stop, then: .\tools\run_tunnel.ps1 -Stop)"
try { Wait-Process -Id $tunnel.Id } catch {}
Write-Service "unavailable" $null
if ($bridge) { try { Stop-Process -Id $bridge.Id -Force -ErrorAction SilentlyContinue } catch {} }
