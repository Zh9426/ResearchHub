# Supplementary localhost-only QA harness; Docker Compose remains deployment target.
[CmdletBinding()]
param([ValidateSet('Install','Start','Stop','Status')][string]$Action = 'Start', [switch]$PostgresOnly)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repoRoot 'storage/runtime'
$downloads = Join-Path $runtime 'downloads'
$pgBin = Join-Path $runtime 'pgsql/bin'
$pgData = Join-Path $runtime 'pgdata'
$minioExe = Join-Path $runtime 'bin/minio.exe'
$secretPath = Join-Path $runtime 'native-env.json'
$statePath = Join-Path $runtime 'native-state.json'
New-Item -ItemType Directory -Force -Path $runtime,$downloads,(Join-Path $runtime 'bin') | Out-Null

function New-NativeSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_').TrimEnd('=')
}
function Save-Json($path, $value) {
    [IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding $false))
}
function Get-VendorDownload($url, $path) {
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host ('Downloading vendor archive: ' + [IO.Path]::GetFileName($path))
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $path -TimeoutSec 600
    }
}
function Invoke-Pg($executable, [string[]]$arguments) {
    & (Join-Path $pgBin $executable) @arguments
    if ($LASTEXITCODE -ne 0) { throw "$executable failed ($LASTEXITCODE); inspect runtime logs." }
}

if ($Action -eq 'Install') {
    $pgZip = Join-Path $downloads 'postgresql-17.11-windows-x64-binaries.zip'
    # Exact EDB Windows x86-64 link from its PostgreSQL17.11 binary download page.
    Get-VendorDownload 'https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616' $pgZip
    if (-not (Test-Path -LiteralPath (Join-Path $pgBin 'postgres.exe'))) { Expand-Archive -LiteralPath $pgZip -DestinationPath $runtime -Force }
    Invoke-Pg 'postgres.exe' @('--version')
    $releases = Invoke-RestMethod -Uri 'https://go.dev/dl/?mode=json' -TimeoutSec 60
    $release = $releases | Where-Object stable | Select-Object -First 1
    $archive = $release.files | Where-Object { $_.os -eq 'windows' -and $_.arch -eq 'amd64' -and $_.kind -eq 'archive' } | Select-Object -First 1
    if (-not $archive -or $archive.filename -notmatch '^go[0-9.]+\.windows-amd64\.zip$') { throw 'Unexpected official Go download metadata.' }
    $goZip = Join-Path $downloads $archive.filename
    Get-VendorDownload ('https://go.dev/dl/' + $archive.filename) $goZip
    if ((Get-FileHash -LiteralPath $goZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archive.sha256) { throw 'Go archive SHA256 mismatch; refusing execution.' }
    $goExe = Join-Path $runtime 'go/bin/go.exe'
    if (-not (Test-Path -LiteralPath $goExe)) { Expand-Archive -LiteralPath $goZip -DestinationPath $runtime -Force }
    $env:GOBIN = Join-Path $runtime 'bin'
    $env:GOPATH = Join-Path $runtime 'gopath'
    $env:GOCACHE = Join-Path $runtime 'gocache'
    $env:GOMODCACHE = Join-Path $runtime 'gomodcache'
    $env:GOENV = 'off'
    $env:GOTOOLCHAIN = 'local'
    $env:CGO_ENABLED = '0'
    $env:GOFLAGS = '-p=4'
    & $goExe version
    if ($LASTEXITCODE -ne 0) { throw 'Portable Go failed.' }
    if (-not (Test-Path -LiteralPath $minioExe)) {
        Write-Host 'Compiling fixed MinIO RELEASE.2025-10-15T17-29-55Z; first build may take several minutes.'
        & $goExe install -trimpath 'github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z'
        if ($LASTEXITCODE -ne 0) { throw 'MinIO source compilation failed; see module error above.' }
    }
    & $minioExe --version
    if ($LASTEXITCODE -ne 0) { throw 'Compiled MinIO executable failed.' }
    Save-Json (Join-Path $runtime 'vendor-manifest.json') @{postgresql_version='17.11'; postgresql_archive_sha256=(Get-FileHash -LiteralPath $pgZip -Algorithm SHA256).Hash.ToLowerInvariant(); go_version=$release.version; go_archive_sha256=$archive.sha256; minio_source='RELEASE.2025-10-15T17-29-55Z'}
    Write-Host 'Native QA dependencies prepared; use -Action Start. No Windows service/registry installation.'
    exit 0
}

if ($Action -eq 'Stop') {
    if (Test-Path -LiteralPath (Join-Path $pgData 'postmaster.pid')) { Invoke-Pg 'pg_ctl.exe' @('-D',$pgData,'-m','fast','-w','stop') }
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
        $process = Get-Process -Id $state.minio_pid -ErrorAction SilentlyContinue
        if ($process -and $process.Path -eq $minioExe) { Stop-Process -Id $process.Id; $process.WaitForExit() }
    }
    Write-Host 'Native PostgreSQL and MinIO stopped; local QA data retained.'
    exit 0
}
if ($Action -eq 'Status') {
    if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath }
    Invoke-Pg 'pg_isready.exe' @('-h','127.0.0.1','-p','55432')
    (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:59000/minio/health/live' -TimeoutSec 5).StatusCode
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $pgBin 'initdb.exe')) -or (-not $PostgresOnly -and -not (Test-Path -LiteralPath $minioExe))) { throw 'Run scripts/native-qa.ps1 -Action Install first.' }
if (-not (Test-Path -LiteralPath $secretPath)) {
    $pgPassword = New-NativeSecret
    Save-Json $secretPath @{POSTGRES_USER='researchhub'; POSTGRES_PASSWORD=$pgPassword; POSTGRES_PORT=55432; DATABASE_URL="postgresql+psycopg://researchhub:${pgPassword}@127.0.0.1:55432/researchhub"; QA_DATABASE_URL="postgresql+psycopg://researchhub:${pgPassword}@127.0.0.1:55432/researchhub_qa"; S3_ENDPOINT_URL='http://127.0.0.1:59000'; S3_ACCESS_KEY=(New-NativeSecret); S3_SECRET_KEY=(New-NativeSecret); S3_BUCKET='researchhub-qa'; COOKIE_SECURE='false'; CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:3000'; MAX_UPLOAD_BYTES='104857600'}
}
$config = Get-Content -Raw -LiteralPath $secretPath | ConvertFrom-Json
$oldPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $config.POSTGRES_PASSWORD
    if (-not (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION'))) {
        $pwfile = Join-Path $runtime 'initdb-pwfile'
        [IO.File]::WriteAllText($pwfile,$config.POSTGRES_PASSWORD,(New-Object Text.UTF8Encoding $false))
        try { Invoke-Pg 'initdb.exe' @('-D',$pgData,'-U','researchhub','--encoding=UTF8','--locale=C','--auth-host=scram-sha-256','--auth-local=scram-sha-256',('--pwfile=' + $pwfile)) }
        finally { Remove-Item -LiteralPath $pwfile }
        Add-Content -LiteralPath (Join-Path $pgData 'postgresql.conf') -Value "`nlisten_addresses = '127.0.0.1'`nport = 55432`npassword_encryption = 'scram-sha-256'"
    }
    & (Join-Path $pgBin 'pg_ctl.exe') -D $pgData status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $pgProcess = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList @('-D',('"' + $pgData + '"'),'-l',('"' + (Join-Path $runtime 'postgres.log') + '"'),'-w','start') -WindowStyle Hidden -PassThru
        # Start-Process -Wait also waits for descendant postgres processes on Windows.
        # WaitForExit waits for pg_ctl only while the database stays running.
        $pgProcess.WaitForExit()
        if ($pgProcess.ExitCode -ne 0) { throw 'Native PostgreSQL failed to start; inspect storage/runtime/postgres.log.' }
    }
    foreach ($name in @('researchhub','researchhub_qa')) {
        $existing = & (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p 55432 -U researchhub -d postgres -Atc "SELECT datname FROM pg_database WHERE datname='$name'"
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL authenticated connection failed.' }
        if (-not $existing) { Invoke-Pg 'createdb.exe' @('-h','127.0.0.1','-p','55432','-U','researchhub',$name) }
    }
} finally { $env:PGPASSWORD = $oldPassword }

if ($PostgresOnly) { Write-Host 'Native PostgreSQL17.11 ready at 127.0.0.1:55432; MinIO compilation may continue separately. Credentials in ignored storage/runtime/native-env.json.'; exit 0 }

$minioProcess = $null
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
    $candidate = Get-Process -Id $state.minio_pid -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Path -eq $minioExe) { $minioProcess = $candidate }
}
if (-not $minioProcess) {
    $oldUser=$env:MINIO_ROOT_USER; $oldSecret=$env:MINIO_ROOT_PASSWORD
    try {
        $env:MINIO_ROOT_USER=$config.S3_ACCESS_KEY; $env:MINIO_ROOT_PASSWORD=$config.S3_SECRET_KEY
        $objects = Join-Path $runtime 'minio-data'
        New-Item -ItemType Directory -Force -Path $objects | Out-Null
        $minioProcess = Start-Process -FilePath $minioExe -ArgumentList @('server',('"' + $objects + '"'),'--address','127.0.0.1:59000','--console-address','127.0.0.1:59001') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'minio.stdout.log') -RedirectStandardError (Join-Path $runtime 'minio.stderr.log')
    } finally { $env:MINIO_ROOT_USER=$oldUser; $env:MINIO_ROOT_PASSWORD=$oldSecret }
}
for ($attempt=0; $attempt -lt 60; $attempt++) {
    try { $health=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:59000/minio/health/live' -TimeoutSec 2; if ($health.StatusCode -eq 200) { break } } catch { Start-Sleep -Milliseconds 500 }
    if ($minioProcess.HasExited) { throw 'MinIO exited; inspect native runtime logs.' }
}
if (-not $health -or $health.StatusCode -ne 200) { throw 'MinIO health check did not become ready.' }
$pgPid = [int](Get-Content -LiteralPath (Join-Path $pgData 'postmaster.pid') -TotalCount 1)
Save-Json $statePath @{postgres_pid=$pgPid; postgres_port=55432; minio_pid=$minioProcess.Id; minio_port=59000; minio_console_port=59001; credential_file=$secretPath}
Write-Host 'Real native QA PostgreSQL/MinIO ready, bound only to localhost. Credentials remain in ignored storage/runtime/native-env.json.'
