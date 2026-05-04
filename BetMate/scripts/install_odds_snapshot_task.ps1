param(
    [string]$TaskName = "BetMate Daily Odds Snapshot",
    [string]$UvExe   = "uv",
    [string]$RunTime  = "09:00"
)

$ErrorActionPreference = "Stop"

$repoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\odds_snapshot.py"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find snapshot script at $scriptPath"
}

$argument = "run --with requests python `"$scriptPath`""
$action   = New-ScheduledTaskAction -Execute $UvExe -Argument $argument -WorkingDirectory $repoRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At $RunTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily odds snapshot from The Odds API. Saves NRL + AFL prices to data/odds_snapshots/YYYY/YYYY-MM-DD.csv for end-of-year analysis." `
    -Force

Write-Host "Installed: $TaskName"
Write-Host "Schedule:  daily at $RunTime"
Write-Host "Output:    data/odds_snapshots/YYYY/YYYY-MM-DD.csv"
