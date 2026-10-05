$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        $dockerBin = Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin'
        if (Test-Path -LiteralPath (Join-Path $dockerBin 'docker.exe')) { $env:PATH = "$dockerBin;$env:PATH" }
        else { throw 'Docker CLI not found. Install Docker Desktop, enable WSL2/Linux containers, then reopen PowerShell.' }
    }
    & docker info --format '{{.OSType}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker daemon unavailable. Start Docker Desktop and wait until Linux engine is ready.' }
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required (included with Docker Desktop).' }
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ComposeArguments)
    & docker compose @ComposeArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed ($LASTEXITCODE). Check the preceding output." }
}
