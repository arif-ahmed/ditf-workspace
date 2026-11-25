# Runs the client-portal (admin back office) browser tests (Playwright, tests\client) against the local dev stack and writes
# reports\client\html\index.html: every case with its screenshots and a video of the whole case.
#   .\scripts\test-client.ps1              run everything        .\scripts\test-client.ps1 -Only 06   one spec file (name filter)
#   .\scripts\test-client.ps1 -Up          start the stack first (dev.ps1 up -MockPayments) if it is not running
#   .\scripts\test-client.ps1 -Headed      watch the browser     -Open   open the HTML report when done
# First run installs Playwright + Chromium into tests\client (nothing in a submodule is touched). Exit code 0 only if all pass.
param([switch]$Up, [switch]$Headed, [switch]$Open, [string]$Only)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$client = Join-Path $root 'tests\client'

function Test-Port($p) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('localhost', $p); $c.Close(); $true } catch { $false } }
function Test-Stack { (Test-Port 5000) -and (Test-Port 9097) }  # client portal, admin API

if ($Up -and -not (Test-Stack)) {
    & (Join-Path $PSScriptRoot 'dev.ps1') up -MockPayments
    Write-Host 'Waiting for the client portal and admin API (first start compiles; up to 5 min)...'
    $end = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $end -and -not (Test-Stack)) { Start-Sleep 3 }
}
if (-not (Test-Stack)) { throw 'Stack is not running. Start it with .\scripts\dev.ps1 up -MockPayments (or pass -Up).' }

Push-Location $client
try {
    if (-not (Test-Path 'node_modules')) { npm install; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
    npx playwright install chromium; if ($LASTEXITCODE) { exit $LASTEXITCODE }  # no-op when the matching browser is already there
    $a = @('playwright', 'test')
    if ($Only) { $a += $Only }
    if ($Headed) { $a += '--headed' }
    & npx @a
    $code = $LASTEXITCODE
    if ($Open) { npx playwright show-report ../../reports/client/html }
    exit $code
} finally { Pop-Location }
