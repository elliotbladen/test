param(
    [string]$TaskName = "BetMate Odds Snapshot 10min",
    [string]$UvExe   = "uv",
    [string]$RunTime  = "00:00",
    [int]$IntervalMinutes = 10
)

$ErrorActionPreference = "Stop"

$repoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\odds_snapshot.py"
$trackerPath = Join-Path $repoRoot "lib\scraper\odds_movement_tracker.py"
$runnerPath = Join-Path $repoRoot "scripts\run_odds_snapshot_cycle.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find snapshot script at $scriptPath"
}
if (-not (Test-Path $trackerPath)) {
    throw "Could not find movement tracker script at $trackerPath"
}
if (-not (Test-Path $runnerPath)) {
    throw "Could not find snapshot runner at $runnerPath"
}

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`" -UvExe `"$UvExe`""
$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $repoRoot
$trigger  = New-ScheduledTaskTrigger -Once -At $RunTime `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 1)
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
    -Description "10-minute odds snapshot from The Odds API, then writes price movements to data/odds_movements/YYYY/YYYY-MM-DD.csv." `
    -Force

Write-Host "Installed: $TaskName"
Write-Host "Schedule:  every $IntervalMinutes minutes, starting at $RunTime"
Write-Host "Output:    data/odds_snapshots/YYYY/YYYY-MM-DD.csv (appended intraday)"
Write-Host "Movements: data/odds_movements/YYYY/YYYY-MM-DD.csv"
