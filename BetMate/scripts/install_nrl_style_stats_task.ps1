param(
    [int]$Season = 2026,

    [string]$TaskName = "BetMate NRL Style Stats Scrape",

    [string]$UvExe = "uv",

    [string]$RunTime = "21:00"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\nrl_style_stats.py"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find scraper at $scriptPath"
}

$argument = "run --with requests --with beautifulsoup4 python `"$scriptPath`" --season $Season --max-attempts 4 --retry-delay-seconds 600"
$action = New-ScheduledTaskAction -Execute $UvExe -Argument $argument -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $RunTime
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
    -Description "Scrapes NRL T2 style stats into BetMate every Monday at $RunTime, retrying every 10 minutes up to 4 attempts." `
    -Force

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: every Monday at $RunTime"
Write-Host "Retries: scraper attempts 4 times, waiting 10 minutes between attempts"
Write-Host "Command: $UvExe $argument"
