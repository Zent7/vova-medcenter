$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "Vova Medcenter Print Agent"
$StartScript = Join-Path $ScriptDir "start-print-agent.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
    Write-Host "Installed scheduled task: $TaskName"
    Write-Host "Start it now from Task Scheduler or run: $StartScript"
}
catch {
    $StartupDir = [Environment]::GetFolderPath("Startup")
    if (-not (Test-Path $StartupDir)) {
        New-Item -ItemType Directory -Path $StartupDir -Force | Out-Null
    }

    $ShortcutPath = Join-Path $StartupDir "$TaskName.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.WindowStyle = 7
    $Shortcut.Save()

    Write-Host "Could not install scheduled task: $($_.Exception.Message)"
    Write-Host "Installed Startup shortcut: $ShortcutPath"
}
