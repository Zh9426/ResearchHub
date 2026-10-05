[CmdletBinding()]
param([switch]$Lan, [switch]$Dev)
. "$PSScriptRoot/common.ps1"
Push-Location $RepoRoot
try {
    Assert-Docker
    if (-not (Test-Path -LiteralPath '.env')) { & "$PSScriptRoot/setup.ps1" }
    if ($Lan -and $Dev) { throw 'Select either LAN deployment or development ports, not both.' }
    $files = @('-f', 'docker-compose.yml')
    if ($Lan) { $files += @('-f', 'docker-compose.lan.yml') }
    if ($Dev) { $files += @('-f', 'docker-compose.dev.yml') }
    Invoke-Compose @files config --quiet
    Invoke-Compose @files up --build --detach --wait --wait-timeout 300
    Write-Host 'Research Hub ready. Desktop: http://localhost:3000. LAN mode: use https://RESEARCHHUB_HOST after trusting the Caddy CA.'
} finally { Pop-Location }
