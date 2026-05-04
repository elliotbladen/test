param(
    [int]$Season = 2026,
    [string]$TaskName = "BetMate NRL Round Prep",
    [string]$UvExe = "uv",
    [string]$RunTime = "18:05"
)

$ErrorActionPreference = "Stop"

$repoRoot  = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\nrl_round_prep.py"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find scraper at $scriptPath"
}

$argument = "run --with requests --with beautifulsoup4 python `"$scriptPath`" --season $Season --max-attempts 3 --retry-delay-seconds 30"
$action   = New-ScheduledTaskAction -Execute $UvExe -Argument $argument -WorkingDirectory $repoRoot
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $RunTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Scrapes NRL fixture, injuries, and referee assignments into BetMate every Monday at $RunTime. BettingEngine reads these at 7:03 PM." `
    -Force

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: every Monday at $RunTime"
Write-Host "Command: $UvExe $argument"
