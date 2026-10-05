[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BackupDirectory, [switch]$ConfirmRestore, [switch]$Lan)
. "$PSScriptRoot/common.ps1"
if (-not $ConfirmRestore) { throw 'Restore requires explicit -ConfirmRestore. Use a NEW empty deployment; never delete existing volumes automatically.' }
Push-Location $RepoRoot
try {
    Assert-Docker
    $backupDir = (Resolve-Path -LiteralPath $BackupDirectory).Path
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $backupDir 'manifest.json') | ConvertFrom-Json
    if ($manifest.format_version -ne 1) { throw 'Unsupported backup version.' }
    foreach ($name in @('postgres.dump','objects.zip')) {
        $actual = (Get-FileHash -LiteralPath (Join-Path $backupDir $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $manifest.checksums.$name) { throw "Checksum mismatch: $name. Nothing restored." }
    }
    $files = @('-f', 'docker-compose.yml')
    if ($Lan) { $files += @('-f', 'docker-compose.lan.yml') }
    Invoke-Compose @files stop web api
    Invoke-Compose @files up --detach --wait db minio
    $count = @(Invoke-Compose @files exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema = ''public''"')
    if (($count -join '').Trim() -ne '0') { throw 'Destination database is not empty. Use a new Compose project/volumes; restore will not destroy existing data.' }
    Invoke-Compose @files build api
    Invoke-Compose @files run --rm --no-deps --user 0 --volume "${backupDir}:/backup:ro" --entrypoint python api /app/scripts/backup_data.py restore /backup/objects.zip
    Invoke-Compose @files cp (Join-Path $backupDir 'postgres.dump') db:/tmp/researchhub-restore.dump
    Invoke-Compose @files exec -T db sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/researchhub-restore.dump'
    Invoke-Compose @files up --build --detach --wait --wait-timeout 300
    Write-Host 'Restore completed. Verify login, projects and an artifact download before using this deployment.'
} finally { Pop-Location }
