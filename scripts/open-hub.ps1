# 本机桌面入口：幂等启动已有原生环境，不下载依赖、不创建账号或导入数据。
[CmdletBinding()]
param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repoRoot 'storage/runtime'
$url = 'http://localhost:3000'
$lockHash = [Security.Cryptography.SHA256]::Create()
try { $lockId = [BitConverter]::ToString($lockHash.ComputeHash([Text.Encoding]::UTF8.GetBytes($repoRoot.ToLowerInvariant()))).Replace('-','').Substring(0,16) }
finally { $lockHash.Dispose() }
$mutex = New-Object Threading.Mutex($false, ('Local\ResearchHubDesktop-' + $lockId))
$locked = $false
function Test-HubReady {
    try {
        $status = Invoke-RestMethod ($url + '/api/auth/status') -TimeoutSec 3
        return ($null -ne $status.setup_required -and (Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200)
    } catch { return $false }
}
try {
    try { $locked = $mutex.WaitOne(60000) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw '另一个入口正在启动服务，请稍后重试。' }
    $statePath = Join-Path $runtime 'native-app-state.json'
    $state = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } else { $null }
    if (Test-HubReady) {
        if (-not $state -or $state.qa) { throw '3000 端口不是已登记的个人 Hub 环境，请先停止其占用进程。' }
    } else {
        foreach ($required in @('.venv/Scripts/python.exe','apps/web/.next/BUILD_ID','storage/runtime/native-env.json','storage/runtime/pgsql/bin/pg_ctl.exe','storage/runtime/bin/minio.exe')) {
            if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $required))) { throw '本机运行环境尚未准备好，请按 README 完成原生环境安装与生产构建。' }
        }
        # 原生服务脚本仅停止其登记且可执行路径匹配的进程。
        if ($state) { & (Join-Path $PSScriptRoot 'native-app.ps1') -Action Stop }
        & (Join-Path $PSScriptRoot 'native-qa.ps1') -Action Start
        & (Join-Path $PSScriptRoot 'native-app.ps1') -Action Start
        if (-not (Test-HubReady)) { throw 'Hub 启动后未就绪，请检查 storage/runtime 中的日志。' }
    }
    if (-not $NoBrowser) { Start-Process -FilePath $url -WindowStyle Hidden }
    Write-Host 'Research Hub 已就绪：http://localhost:3000'
} catch {
    $message = $_.Exception.Message
    if ($NoBrowser) { throw }
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($message, 'Research Hub 启动失败', 'OK', 'Error') | Out-Null
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
