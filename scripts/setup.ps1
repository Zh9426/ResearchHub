[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $RepoRoot '.env'
if (Test-Path -LiteralPath $EnvPath) { Write-Host '.env already exists; existing secrets preserved.'; exit 0 }
function New-Secret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_').TrimEnd('=')
}
$config = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot '.env.example')
$config = $config.Replace('POSTGRES_PASSWORD=', 'POSTGRES_PASSWORD=' + (New-Secret))
$config = $config.Replace('S3_ACCESS_KEY=', 'S3_ACCESS_KEY=' + (New-Secret))
$config = $config.Replace('S3_SECRET_KEY=', 'S3_SECRET_KEY=' + (New-Secret))
[System.IO.File]::WriteAllText($EnvPath, $config, (New-Object System.Text.UTF8Encoding $false))
Write-Host 'Created .env with three independent random secrets. Keep this file private and include it in your encrypted backup.'
