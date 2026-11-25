# Runs the whole DG TMS stack from this workspace, using each submodule's own commands (nothing in a submodule is edited).
#   .\scripts\dev.ps1 up        database, public API :9096, admin API :9097, web portal :4200, client portal :5000
#   .\scripts\dev.ps1 status    what is listening
#   .\scripts\dev.ps1 up -NoApi   same, but without the two APIs (run them from IntelliJ)
#   .\scripts\dev.ps1 up -MockPayments   also start the fake DGePay + S3 (:18080/:18090) and fake media (:18091) and point the
#                               public API at them, so a full booking -> pay -> ticket PDF works offline (then: scripts\mock-pay.ps1)
#   .\scripts\dev.ps1 infra   only the shared pieces: database + seed + mock DGePay/S3 + mock media (no APIs, no web apps)
#   .\scripts\dev.ps1 down      stop the apps (the database container is left running; add -Db to stop it too)
# Local overrides (never committed): scripts/dev.local.env, one KEY=VALUE per line, e.g. SCANNER_KEYS=gate-1:<key>
param(
    [ValidateSet('up', 'infra', 'down', 'status')][string]$Action = 'up',
    [switch]$Db,
    [switch]$NoApi,  # run the APIs from IntelliJ instead (see docs/local-dev.md)
    [switch]$MockPayments
)
$ErrorActionPreference = 'Stop'
if ($Action -eq 'infra') { $MockPayments = [switch]$true }  # infra = database + mocks only; run the APIs/web apps yourself
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$ports = @{ 'public API' = 9096; 'admin API' = 9097; 'web portal' = 4200; 'client portal' = 5000; 'mock DGePay' = 18080; 'mock checkout' = 18081; 'mock media' = 18091 }

function Test-Port($p) { [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) }

if ($Action -eq 'status') {
    foreach ($k in $ports.Keys) { '{0,-14} :{1}  {2}' -f $k, $ports[$k], $(if (Test-Port $ports[$k]) { 'UP' } else { 'down' }) }
    return
}

if ($Action -eq 'down') {
    foreach ($p in $ports.Values) {
        Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
    if ($Db) { docker stop ditf-pg }
    return
}

# ---- preflight ----
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker is not running. Start Docker Desktop first.' }
if ($Action -ne 'infra' -and (cmd /c 'java -version 2>&1' | Out-String) -notmatch 'version "2[1-9]') { throw 'JDK 21+ is required for the API (check JAVA_HOME / PATH).' }
if ($Action -ne 'infra' -and [version](node -v).TrimStart('v') -lt [version]'22.12') { throw 'Node 22.12+ is required for the web apps.' }
foreach ($d in 'dg-tms-api', 'dg-tms-web-portal', 'dg-tms-client-portal') {
    if (-not (Test-Path (Join-Path $root "$d\package.json")) -and -not (Test-Path (Join-Path $root "$d\pom.xml"))) {
        throw "$d is empty. Run: git submodule update --init"
    }
}

# ---- database ----
$exists = docker ps -a --filter 'name=^ditf-pg$' --format '{{.Names}}'
if ($exists) { docker start ditf-pg | Out-Null } else { docker compose -f (Join-Path $root 'docker-compose.dev.yml') up -d }
& (Join-Path $root 'scripts\seed\seed.ps1') | Out-Null   # waits for PostgreSQL; repeatable

# ---- settings (dev defaults, then scripts/dev.local.env on top) ----
# The storage endpoint is deliberately unreachable: application.properties ships real S3 credentials, and a local
# run must not write ticket PDFs to that shared bucket. Override STORAGE_* in dev.local.env for a local MinIO.
$cfg = [ordered]@{
    QUARKUS_DATASOURCE_JDBC_URL          = 'jdbc:postgresql://127.0.0.1:5432/ditf'
    QUARKUS_DATASOURCE_USERNAME          = 'ditf'
    QUARKUS_DATASOURCE_PASSWORD          = 'ditf'
    ADMIN_TOKEN_SECRET                   = 'dev-only-secret-at-least-32-characters-long'
    APP_PUBLIC_BASE_URL                  = 'http://localhost:9096'
    APP_PAYMENT_RESULT_REDIRECT_URL      = 'http://localhost:4200/txn-status'
    STORAGE_ENDPOINT                     = 'http://127.0.0.1:9'
}
$uploads = Join-Path $env:TEMP 'ditf-mock-uploads'
if ($MockPayments) {
    # The e2e suite's mock gateway (same protocol as DGePay). Its credentials are fixed test values, not secrets.
    $mockDir = Join-Path $root 'dg-tms-api\src\test\e2e'
    python -c "import cryptography" 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'MockPayments needs Python 3 with: pip install cryptography' }
    $cfg['DGEPAY_BASE_URL']      = 'http://127.0.0.1:18081/payment_gateway'  # via mock_checkout.py, which adds the checkout page
    $cfg['DGEPAY_CLIENT_ID']     = 'test-client'
    $cfg['DGEPAY_CLIENT_SECRET'] = 'mocksecret0123456789abcdef'
    $cfg['DGEPAY_API_KEY']       = 'mock-api-key'
    $cfg['STORAGE_ENDPOINT']     = 'http://127.0.0.1:18090'
    $cfg['STORAGE_ACCESS_KEY']   = 'testaccess'
    $cfg['STORAGE_SECRET_KEY']   = 'testsecret123'
    $cfg['STORAGE_PUBLIC_URL']   = 'http://127.0.0.1:18091'
}
$local = Join-Path $PSScriptRoot 'dev.local.env'
if (Test-Path $local) {
    Get-Content $local | Where-Object { $_ -match '^\s*[^#\s][^=]*=' } | ForEach-Object {
        $k, $v = $_ -split '=', 2; $cfg[$k.Trim()] = $v.Trim()
    }
}

# ---- apps: one window each, started through the same commands the submodule READMEs give ----
function Start-App($title, $dir, $cmd, $env) {
    $set = ($env.GetEnumerator() | ForEach-Object { "`$env:$($_.Key)='$($_.Value)';" }) -join ' '
    $line = "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location '$root\$dir'; $set $cmd"
    Start-Process pwsh -ArgumentList '-NoExit', '-Command', $line
}

if ($Action -eq 'up') { foreach ($d in 'dg-tms-web-portal', 'dg-tms-client-portal') {
    if (-not (Test-Path (Join-Path $root "$d\node_modules"))) { Push-Location (Join-Path $root $d); npm install; Pop-Location }
} }

if ($MockPayments) {
    Start-App 'ditf mock DGePay :18080' 'dg-tms-api\src\test\e2e' 'python -I mock_dgepay.py' @{ UPLOAD_DIR = $uploads }
    Start-App 'ditf mock checkout :18081' 'scripts' 'python -I mock_checkout.py' @{}
    Start-App 'ditf mock media :18091' 'scripts' "python -I mock_media.py '$uploads'" @{}
}
if ($Action -eq 'infra') {
    Write-Host 'Infra ready: DB :5432 (ditf/ditf, seeded), mock DGePay+S3 :18080/:18090, mock checkout page :18081, mock media :18091.'
    Write-Host 'Env for the public API (IntelliJ run config / shell):'
    $cfg.GetEnumerator() | ForEach-Object { Write-Host "  $($_.Key)=$($_.Value)" }
    Write-Host 'Admin API additionally: QUARKUS_HTTP_PORT=9097, VM option -Dapp.module=admin. Stop with: .\scripts\dev.ps1 down'
    return
}
if (-not $NoApi) {
    # Both APIs run in dg-tms-api, so the admin one gets its own port, debug port and log file.
    Start-App 'ditf public API :9096' 'dg-tms-api' '.\mvnw.cmd quarkus:dev' $cfg
    $admin = [ordered]@{}; foreach ($e in $cfg.GetEnumerator()) { $admin[$e.Key] = $e.Value }  # OrderedDictionary has no .Clone() on newer .NET
    $admin['QUARKUS_HTTP_PORT'] = '9097'
    $admin['QUARKUS_LOG_FILE_PATH'] = 'logs/admin.log'
    Start-App 'ditf admin API :9097' 'dg-tms-api' '.\mvnw.cmd quarkus:dev "-Dapp.module=admin" "-Ddebug=5006"' $admin
}
Start-App 'ditf web portal :4200' 'dg-tms-web-portal' 'npm start' @{}
Start-App 'ditf client portal :5000' 'dg-tms-client-portal' 'npm start' @{}

Write-Host "Started. Check progress with: .\scripts\dev.ps1 status"
Write-Host "Booking page http://localhost:4200 | Admin portal http://localhost:5000 (phone 1900003001, PIN 1234)"
Write-Host "Mobile app: cd dg-tms-mobile-app; flutter run --dart-define-from-file=env/dev.json"
