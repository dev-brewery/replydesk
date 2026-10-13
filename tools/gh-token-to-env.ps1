# Logs gh in (device flow, waits as long as needed), then writes the token to
# .env (in the given repo, default: current directory) as GITHUB_TOKEN.
# Replaces any existing GITHUB_TOKEN line. The token is never printed.
# Run in a normal PowerShell window (not inside an agent tool with a timeout):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\gh-token-to-env.ps1 [repoDir]
param([string]$RepoDir = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$envFile = Join-Path $RepoDir '.env'

gh auth login -h github.com --web --git-protocol https
if ($LASTEXITCODE -ne 0) { Write-Host 'gh auth login failed - .env not touched.' -ForegroundColor Red; exit 1 }

$token = (gh auth token -h github.com).Trim()
if (-not $token) { Write-Host 'gh returned no token - .env not touched.' -ForegroundColor Red; exit 1 }

$lines = @()
if (Test-Path $envFile) { $lines = @(Get-Content $envFile | Where-Object { $_ -notmatch '^\s*GITHUB_TOKEN=' }) }
$lines += "GITHUB_TOKEN=$token"
[IO.File]::WriteAllLines($envFile, $lines)  # UTF-8, no BOM

$login = gh api user --jq .login
Write-Host "Done. GITHUB_TOKEN written to $envFile (verified as: $login)." -ForegroundColor Green
