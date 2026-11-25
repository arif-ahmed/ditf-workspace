# Runs the API test suite (tests/api) one case after another against the local dev stack and writes reports\latest.html.
#   .\scripts\test.ps1              run everything          .\scripts\test.ps1 -Only 04   one case file (prefix)
#   .\scripts\test.ps1 -Up          start the stack first (dev.ps1 up -MockPayments) if it is not running
#   .\scripts\test.ps1 -FailFast    stop at the first failing case       -Open   open the report when done
#   .\scripts\test.ps1 -Fast        skip the one case that waits ~2 min for the payment reconciliation timer (full run ~2.5 min, -Fast ~20 s)
# Exit code is 0 only when every case passes. Needs Python 3 with: pip install cryptography jinja2
param([switch]$Up, [switch]$FailFast, [switch]$Open, [switch]$Fast, [string]$Only)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')

function Test-Health($p) { try { (Invoke-WebRequest "http://127.0.0.1:$p/ticket-booking/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch { $false } }

if ($Up -and -not ((Test-Health 9096) -and (Test-Health 9097))) {
    & (Join-Path $PSScriptRoot 'dev.ps1') up -MockPayments
    Write-Host 'Waiting for both APIs (first start compiles; up to 5 min)...'
    $end = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $end -and -not ((Test-Health 9096) -and (Test-Health 9097))) { Start-Sleep 3 }
}

$a = @()
if ($Only) { $a += '--only', $Only }
if ($FailFast) { $a += '--fail-fast' }
if ($Fast) { $a += '--fast' }
if ($Open) { $a += '--open' }
python (Join-Path $root 'tests\api\runner.py') @a
exit $LASTEXITCODE
