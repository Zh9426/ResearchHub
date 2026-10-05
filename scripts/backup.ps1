[CmdletBinding()]
param([switch]$Lan)
. "$PSScriptRoot/common.ps1"
Push-Location $RepoRoot
$resume = @()
$files = @('-f', 'docker-compose.yml')
if ($Lan) { $files += @('-f', 'docker-compose.lan.yml') }
try {
    Assert-Docker
    $running = @(Invoke-Compose @files ps --services --status running)
    if ($running -notcontains 'db' -or $running -notcontains 'minio') { throw 'Database and MinIO must be running before backup.' }
    $resume = @($running | Where-Object { $_ -in @('web','api') })
    $backupDir = Join-Path $RepoRoot ('storage/backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $backupDir | Out-Null
    # Stop all writers first: SQL and objects describe the same quiescent state.
    if ($resume.Count -gt 0) { Invoke-Compose @files stop @resume }
    Invoke-Compose @files exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/researchhub.dump'
    Invoke-Compose @files cp db:/tmp/researchhub.dump (Join-Path $backupDir 'postgres.dump')
    Invoke-Compose @files run --rm --no-deps --user 0 --volume "${backupDir}:/backup" --entrypoint python api /app/scripts/backup_data.py export /backup/objects.zip
    $checksums = @{}
    foreach ($name in @('postgres.dump','objects.zip')) { $checksums[$name] = (Get-FileHash -LiteralPath (Join-Path $backupDir $name) -Algorithm SHA256).Hash.ToLowerInvariant() }
    $manifest = @{ format_version = 1; created_at = (Get-Date).ToUniversalTime().ToString('o'); checksums = $checksums }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $backupDir 'manifest.json') -Encoding UTF8
    Write-Host "Backup complete: $backupDir. Copy .env separately into encrypted offline storage."
} finally {
    try { if ($resume.Count -gt 0) { Invoke-Compose @files start @resume } }
    finally { Pop-Location }
}
