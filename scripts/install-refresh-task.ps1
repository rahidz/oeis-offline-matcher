param(
    [string]$TaskName = "OEIS Refresh",
    [string]$Distribution = "Ubuntu",
    [string]$LinuxUser = "rahidz",
    [string]$ProjectRoot = "/home/rahidz/coding/oeis",
    [datetime]$FirstRun = (Get-Date).Date.AddDays(28).AddHours(4)
)

$ErrorActionPreference = "Stop"
$arguments = "-d `"$Distribution`" -u `"$LinuxUser`" --cd `"$ProjectRoot`" `"$ProjectRoot/scripts/oeis-refresh`""
$action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\wsl.exe" `
    -Argument $arguments
$trigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 4 -DaysOfWeek $FirstRun.DayOfWeek -At $FirstRun
# An offset-free boundary preserves the local clock time across DST changes.
$trigger.StartBoundary = $FirstRun.ToString("yyyy-MM-dd'T'HH:mm:ss")
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 2) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskPath "\" `
    -TaskName $TaskName `
    -Description "Refresh OEIS exports, metadata and b-files and rebuild local indexes every four weeks." `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Get-ScheduledTaskInfo -TaskPath "\" -TaskName $TaskName |
    Select-Object TaskName, NextRunTime, LastRunTime, LastTaskResult
