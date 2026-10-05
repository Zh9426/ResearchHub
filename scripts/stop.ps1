[CmdletBinding()]
param([switch]$Lan, [switch]$Dev)
. "$PSScriptRoot/common.ps1"
Push-Location $RepoRoot
try {
    Assert-Docker
    $files = @('-f', 'docker-compose.yml')
    if ($Lan) { $files += @('-f', 'docker-compose.lan.yml') }
    if ($Dev) { $files += @('-f', 'docker-compose.dev.yml') }
    Invoke-Compose @files stop
    Write-Host 'Containers stopped. Database, objects and certificates remain in Docker volumes.'
} finally { Pop-Location }
