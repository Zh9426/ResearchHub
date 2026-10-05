[CmdletBinding()]
param([string]$Destination = [Environment]::GetFolderPath('Desktop'))
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { throw '快捷方式目标目录不存在。' }
$launcher = Join-Path $PSScriptRoot 'open-hub.ps1'
$shortcutPath = Join-Path $Destination 'Research Hub.lnk'
if (Test-Path -LiteralPath $shortcutPath) { throw '同名快捷方式已存在，请保留它或选择另一个目标目录。' }
$iconPath = Join-Path $repoRoot 'storage/runtime/researchhub.ico'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $iconPath) | Out-Null
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object Drawing.Bitmap((Join-Path $repoRoot 'apps/web/public/icons/icon-192.png'))
$icon = [Drawing.Icon]::FromHandle($bitmap.GetHicon())
$stream = [IO.File]::Create($iconPath)
try { $icon.Save($stream) } finally { $stream.Dispose(); $icon.Dispose(); $bitmap.Dispose() }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"'
$shortcut.WorkingDirectory = $repoRoot
$shortcut.IconLocation = $iconPath
$shortcut.Description = '启动个人科研工作区：Research Hub'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Host ('已建立桌面入口：' + $shortcutPath)
