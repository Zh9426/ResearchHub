# Optional local native acceptance runtime; production deployment remains Compose.
[CmdletBinding()]
param([ValidateSet('Start','Stop','Status')][string]$Action='Start', [switch]$Qa)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$runtime=Join-Path $repoRoot 'storage/runtime'
$statePath=Join-Path $runtime 'native-app-state.json'
$pythonExe=Join-Path $repoRoot '.venv/Scripts/python.exe'
$nodeCommand=Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCommand) { throw 'Node.js22 or later is required; install it and reopen PowerShell.' }
$nodeExe=$nodeCommand.Source

if ($Action -eq 'Status') {
    if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath }
    (Invoke-WebRequest 'http://127.0.0.1:8000/api/auth/status' -TimeoutSec 5).StatusCode
    (Invoke-WebRequest 'http://127.0.0.1:3000' -TimeoutSec 5).StatusCode
    exit 0
}
if ($Action -eq 'Stop') {
    if (Test-Path -LiteralPath $statePath) {
        $state=Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
        foreach ($entry in @(@{Id=$state.api_pid;Path=$pythonExe},@{Id=$state.web_pid;Path=$state.node_executable})) {
            $process=Get-Process -Id $entry.Id -ErrorAction SilentlyContinue
            if ($process -and $process.Path -eq $entry.Path) {
                # Windows venv Python is a redirector; stop its owned child server too.
                & taskkill.exe /PID $process.Id /T /F | Out-Null
                if ($LASTEXITCODE -ne 0) { throw 'Could not stop the owned native process tree.' }
                $process.WaitForExit()
            }
        }
    }
    Write-Host 'Owned native API/Web processes stopped. PostgreSQL/MinIO and data retained.'
    exit 0
}
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install API/MCP requirements first.' }
$webRoot=Join-Path $repoRoot 'apps/web'
if (-not (Test-Path -LiteralPath (Join-Path $webRoot '.next/BUILD_ID'))) { throw 'Build the Web first: cd apps/web; npm ci; npm run build.' }
foreach ($port in @(8000,3000)) {
    $socket=New-Object Net.Sockets.TcpClient
    try { $socket.Connect('127.0.0.1',$port); throw "Port $port is already in use; stop its owner before starting this harness." }
    catch [Net.Sockets.SocketException] { }
    finally { $socket.Dispose() }
}
$secretPath=Join-Path $runtime 'native-env.json'
if (-not (Test-Path -LiteralPath $secretPath)) { throw 'Start PostgreSQL/MinIO first with scripts/native-qa.ps1 -Action Start.' }
$config=Get-Content -Raw -LiteralPath $secretPath | ConvertFrom-Json
$values=@{DATABASE_URL=$config.DATABASE_URL;S3_ENDPOINT_URL=$config.S3_ENDPOINT_URL;S3_ACCESS_KEY=$config.S3_ACCESS_KEY;S3_SECRET_KEY=$config.S3_SECRET_KEY;S3_BUCKET='researchhub';COOKIE_SECURE='false';CORS_ORIGINS=$config.CORS_ORIGINS;MAX_UPLOAD_BYTES=$config.MAX_UPLOAD_BYTES;API_INTERNAL_URL='http://127.0.0.1:8000';NODE_ENV='production';NEXT_TELEMETRY_DISABLED='1';HOSTNAME='127.0.0.1';PORT='3000'}
if ($Qa) { $values.DATABASE_URL=$config.QA_DATABASE_URL; $values.S3_BUCKET='researchhub-qa' }
$previous=@{}
foreach ($name in $values.Keys) { $previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process'); [Environment]::SetEnvironmentVariable($name,$values[$name],'Process') }
$apiProcess=$null
$webProcess=$null
Push-Location $repoRoot
try {
    & $pythonExe -m alembic -c infrastructure/migrations/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Native PostgreSQL migration failed.' }
    $apiProcess=Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','apps.api.researchhub.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'api.stdout.log') -RedirectStandardError (Join-Path $runtime 'api.stderr.log')
    $standaloneRoot=Join-Path $webRoot '.next/standalone/apps/web'
    $standaloneServer=Join-Path $standaloneRoot 'server.js'
    if (-not (Test-Path -LiteralPath $standaloneServer)) { throw 'Next.js standalone output is missing; rebuild Web.' }
    New-Item -ItemType Directory -Force -Path (Join-Path $standaloneRoot 'public'),(Join-Path $standaloneRoot '.next/static') | Out-Null
    Copy-Item -Path (Join-Path $webRoot 'public/*') -Destination (Join-Path $standaloneRoot 'public') -Recurse -Force
    Copy-Item -Path (Join-Path $webRoot '.next/static/*') -Destination (Join-Path $standaloneRoot '.next/static') -Recurse -Force
    $webProcess=Start-Process -FilePath $nodeExe -ArgumentList @(('"'+$standaloneServer+'"')) -WorkingDirectory $standaloneRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'web.stdout.log') -RedirectStandardError (Join-Path $runtime 'web.stderr.log')
    $ready=$false
    for ($attempt=0;$attempt -lt 60;$attempt++) {
        if ($apiProcess.HasExited -or $webProcess.HasExited) { throw 'Native app process exited; inspect storage/runtime logs.' }
        try {
            $apiHealth=Invoke-WebRequest 'http://127.0.0.1:8000/api/auth/status' -TimeoutSec 2
            $webHealth=Invoke-WebRequest 'http://127.0.0.1:3000' -TimeoutSec 2
            if ($apiHealth.StatusCode -eq 200 -and $webHealth.StatusCode -eq 200) { $ready=$true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Native app did not become ready.' }
    $state=@{api_pid=$apiProcess.Id;web_pid=$webProcess.Id;node_executable=$nodeExe;qa=[bool]$Qa;web_url='http://localhost:3000';api_url='http://127.0.0.1:8000'}
    [IO.File]::WriteAllText($statePath,($state | ConvertTo-Json),(New-Object Text.UTF8Encoding $false))
    Write-Host 'Native Research Hub ready at http://localhost:3000. No account or demo data was automatically created. Docker deployment remains separately unverified.'
} catch {
    foreach ($process in @($apiProcess,$webProcess)) { if ($process -and -not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null } }
    throw
} finally {
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name,$previous[$name],'Process') }
    Pop-Location
}
