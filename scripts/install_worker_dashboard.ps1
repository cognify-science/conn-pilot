$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path $PSScriptRoot -Parent
$pythonw = Join-Path $repoRoot '.venv\Scripts\pythonw.exe'
$module = 'conn_pilot.worker_dashboard'

if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Python windowed executable is missing: $pythonw"
}

$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$targets = @((Join-Path $desktop 'CONN Pilot Monitor.lnk'))

foreach ($target in $targets) {
    $shortcut = $shell.CreateShortcut($target)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "-m $module"
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.Description = 'Monitor visual del worker de CONN Pilot'
    $shortcut.Save()
    Write-Output "Installed CONN Pilot monitor shortcut: $target"
}

$taskName = 'CONN Pilot Monitor'
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m $module" -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Installed and started scheduled task: $taskName"
