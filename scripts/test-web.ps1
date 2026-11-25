# Runs the web-portal browser tests (Playwright, tests\web) against the local dev stack and writes reports\web\html\index.html
# with a screenshot for every step.
#   .\scripts\test-web.ps1              run everything        .\scripts\test-web.ps1 -Only 03   one spec file (name filter)
#   .\scripts\test-web.ps1 -Up          start the stack first (dev.ps1 up -MockPayments) if it is not running
#   .\scripts\test-web.ps1 -Headed      watch the browser     -Open   open the HTML report when done
# First run installs Playwright + Chromium into tests\web (nothing in a submodule is touched). Exit code 0 only if all pass.
param([switch]$Up, [switch]$Headed, [switch]$Open, [string]$Only)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$web = Join-Path $root 'tests\web'

function Test-Port($p) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('localhost', $p); $c.Close(); $true } catch { $false } }
function Test-Stack { (Test-Port 4200) -and (Test-Port 9096) -and (Test-Port 18081) }  # web portal, public API, mock checkout

if ($Up -and -not (Test-Stack)) {
    & (Join-Path $PSScriptRoot 'dev.ps1') up -MockPayments
    Write-Host 'Waiting for the web portal and public API (first start compiles; up to 5 min)...'
    $end = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $end -and -not (Test-Stack)) { Start-Sleep 3 }
}
if (-not (Test-Stack)) { throw 'Stack is not running. Start it with .\scripts\dev.ps1 up -MockPayments (or pass -Up).' }

Push-Location $web
try {
    if (-not (Test-Path 'node_modules')) { npm install; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
    npx playwright install chromium; if ($LASTEXITCODE) { exit $LASTEXITCODE }  # no-op when the matching browser is already there
    $a = @('playwright', 'test')
    if ($Only) { $a += $Only }
    if ($Headed) { $a += '--headed' }
    & npx @a
    $code = $LASTEXITCODE
    if ($Open) { npx playwright show-report ../../reports/web/html }
    exit $code
} finally { Pop-Location }
