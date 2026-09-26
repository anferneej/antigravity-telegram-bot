param(
    [string]$Action = "install"
)

$TaskNamePrefix = "AntiGravity_TG_Push"
$PythonPath = (Get-Command python).Source
$ScriptPath = "e:\antigravity-telegeam\src\main.py"
$SettingsPath = "e:\antigravity-telegeam\config\settings.json"

if ($Action -eq "uninstall") {
    $existingTasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "$TaskNamePrefix*" }
    foreach ($task in $existingTasks) {
        Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false
        Write-Host "Removed task: $($task.TaskName)"
    }
    Write-Host "All AntiGravity push tasks have been removed."
    exit 0
}

if (-not (Test-Path $SettingsPath)) {
    Write-Host "Config not found: $SettingsPath"
    exit 1
}

$settings = Get-Content $SettingsPath -Raw | ConvertFrom-Json
$times = $settings.schedule_times

if (-not $times -or $times.Count -eq 0) {
    Write-Host "No schedule times found in settings.json"
    exit 1
}

$existingTasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "$TaskNamePrefix*" }
foreach ($task in $existingTasks) {
    Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false
}

$idx = 1
foreach ($timeStr in $times) {
    $cleanTime = $timeStr.Replace(':', '')
    $taskName = "${TaskNamePrefix}_${cleanTime}"
    $actionObj = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`" --once" -WorkingDirectory "e:\antigravity-telegeam"
    $triggerObj = New-ScheduledTaskTrigger -Daily -At $timeStr
    $settingsObj = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Register-ScheduledTask -TaskName $taskName -Action $actionObj -Trigger $triggerObj -Settings $settingsObj -Description "AntiGravity Telegram Push at $timeStr" | Out-Null
    Write-Host "Registered task [$idx]: Daily at $timeStr ($taskName)"
    $idx++
}

Write-Host "Success: All schedule tasks registered to Windows Task Scheduler."
