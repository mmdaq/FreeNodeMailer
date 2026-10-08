<#
.SYNOPSIS
  Register / update the FreeNodeMailer daily scheduled task (default 08:00).

.EXAMPLE
  # Register (default 08:00, current user, no admin needed)
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1

  # Custom time
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time 07:30

  # Show status
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Status

  # Remove task
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Unregister

  # Run immediately
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -RunNow

.NOTES
  - Registered as the current user, "run only when logged on" by default (no admin password).
  - Add -RunWhenLoggedOff to also run while logged off (asks for your Windows password).
  - The PC must be powered on and online at 08:00. Add -StartWhenAvailable to catch up
    if the time was missed.
#>
[CmdletBinding()]
param(
    [string]$Time = "08:00",
    [string]$TaskName = "FreeNodeMailer-DailyPush",
    [switch]$Unregister,
    [switch]$Status,
    [switch]$RunNow,
    [switch]$RunWhenLoggedOff,
    [switch]$StartWhenAvailable,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot "run.bat"
$logDir = Join-Path $projectRoot "logs"

function Write-Info([string]$msg) { Write-Host "[i] $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host "[!] $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- status
if ($Status) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) {
        Write-Warn2 "Task not found: $TaskName"
        exit 1
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Task name   : $($t.TaskName)"
    Write-Host "State       : $($t.State)"
    Write-Host "Trigger     : $(($t.Triggers | ForEach-Object { $_.StartBoundary }) -join ', ')"
    Write-Host "Last run    : $($info.LastRunTime)"
    Write-Host "Last result : 0x$('{0:X}' -f $info.LastTaskResult)"
    Write-Host "Next run    : $($info.NextRunTime)"
    foreach ($a in $t.Actions) {
        Write-Host "Action      : $($a.Execute) $($a.Arguments)"
    }
    exit 0
}

# ---------------------------------------------------------------- unregister
if ($Unregister) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Ok "Removed scheduled task: $TaskName"
    } else {
        Write-Warn2 "Task not found: $TaskName"
    }
    exit 0
}

# ---------------------------------------------------------------- run now
if ($RunNow) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) {
        Write-Warn2 "Task not found: $TaskName (register it first)"
        exit 1
    }
    Start-ScheduledTask -TaskName $TaskName
    Write-Ok "Triggered task: $TaskName (use -Status to check the result)"
    exit 0
}

# ---------------------------------------------------------------- register
if (-not (Test-Path $target)) {
    Write-Host "Cannot find $target" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not $Force) {
    Write-Warn2 "Task already exists: $TaskName (use -Force to overwrite, or -Unregister first)"
    Write-Info "Current status:"
    Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, LastTaskResult, NextRunTime
    exit 1
}

$action = New-ScheduledTaskAction -Execute $target -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $Time
if ($StartWhenAvailable) {
    $trigger.StartWhenAvailable = $true
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable:$StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
    -MultipleInstances IgnoreNew `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10)

$userId = "$env:USERDOMAIN\$env:USERNAME"
if ($RunWhenLoggedOff) {
    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Password -RunLevel Limited
    Write-Info "Using -RunWhenLoggedOff; you may be prompted for your Windows password"
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force:$Force | Out-Null

Write-Ok "Scheduled task registered: $TaskName"
Write-Host "  Schedule : daily at $Time (local time)"
Write-Host "  Command  : $target"
Write-Host "  Workdir  : $projectRoot"
Write-Host ""
Write-Host "Status   : powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Status" -ForegroundColor DarkGray
Write-Host "Run now  : powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -RunNow" -ForegroundColor DarkGray
Write-Host "Remove   : powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Unregister" -ForegroundColor DarkGray
