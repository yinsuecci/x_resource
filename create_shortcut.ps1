$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $project "打开新闻台.bat"
$desktop = [Environment]::GetFolderPath("Desktop")
# Windows 快捷方式在部分环境下对中文 .lnk 文件名不友好，使用英文名
$shortcutPath = Join-Path $desktop "ViralNewsDesk.lnk"
$batCopy = Join-Path $desktop "打开流量新闻台.bat"

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($shortcutPath)
$sc.TargetPath = $bat
$sc.WorkingDirectory = $project
$sc.WindowStyle = 1
$sc.Description = "流量新闻台：Nature / 经济学人等冲突向全球新闻中文摘要"
$sc.Save()

Copy-Item -Force $bat $batCopy

Write-Host "已创建桌面快捷方式: $shortcutPath"
Write-Host "已复制启动脚本: $batCopy"
