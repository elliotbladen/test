param(
    [string]$TaskName = "BettingEngine NRL Referees Fetch",
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [string]$RunTime = "17:00",
    [int]$Season = 2026
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\nrl_referees.py"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find referee scraper at $scriptPath"
}

if (-not (Test-Path $UvExe)) {
    throw "Could not find uv executable at $UvExe"
}

$argument = "run --with requests --with beautifulsoup4 python `"lib\scraper\nrl_referees.py`" --season $Season"
$action = New-ScheduledTaskAction -Execute $UvExe -Argument $argument -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At $RunTime
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
    -Description "Scrapes NRL referee appointments into BetMate every Wednesday at $RunTime." `
    -Force

Write-Host "Installed: $TaskName"
Write-Host "Schedule:  Wednesday at $RunTime"
Write-Host "Output:    data/nrl/referees/processed/latest-referees.csv"
