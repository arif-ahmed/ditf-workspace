# Loads scripts/seed/seed.sql into the dev PostgreSQL container (docker-compose.dev.yml). Safe to run repeatedly.
# If the tables don't exist yet it applies the API's db/schema.sql first (idempotent), so the API need not run first.
param([string]$Container = 'ditf-pg')
$ErrorActionPreference = 'Stop'

$running = docker ps --filter "name=^$Container$" --format '{{.Names}}'
if (-not $running) { throw "Container '$Container' is not running. Start it: docker compose -f docker-compose.dev.yml up -d" }

for ($i = 0; $i -lt 30; $i++) {
    docker exec $Container pg_isready -U ditf -d ditf *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep 2
}
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL in '$Container' is not accepting connections." }

$hasSchema = docker exec $Container psql -U ditf -d ditf -tAc "select to_regclass('public.booking_configs') is not null"
if ($hasSchema.Trim() -ne 't') {
    $schema = Join-Path $PSScriptRoot '..\..\dg-tms-api\src\main\resources\db\schema.sql'
    if (-not (Test-Path $schema)) { throw 'dg-tms-api submodule is empty. Run: git submodule update --init' }
    Write-Host 'Applying schema...'
    Get-Content $schema -Raw | docker exec -i $Container psql -U ditf -d ditf -v ON_ERROR_STOP=1 -q -1
    if ($LASTEXITCODE -ne 0) { throw 'Applying the schema failed.' }
}

Get-Content (Join-Path $PSScriptRoot 'seed.sql') -Raw | docker exec -i $Container psql -U ditf -d ditf -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) { throw 'Seeding failed (the transaction was rolled back).' }
