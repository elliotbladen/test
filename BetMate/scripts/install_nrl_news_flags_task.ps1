param(
    [string]$TaskName = "BetMate NRL News Flags",
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [string]$RunTime = "22:30",
    [int]$Season = 2026
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\nrl_news_flags.py"
$runnerPath = Join-Path $repoRoot "scripts\run_nrl_news_flags.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find NRL news flags scraper at $scriptPath"
}

if (-not (Test-Path $runnerPath)) {
    throw "Could not find NRL news flags runner at $runnerPath"
}

if (-not (Test-Path $UvExe)) {
    throw "Could not find uv executable at $UvExe"
}

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"scripts\run_nrl_news_flags.ps1`" -UvExe `"$UvExe`" -Season $Season"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday,Friday,Saturday,Sunday -At $RunTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Scans NRL injury, judiciary, club and news sources for market-moving post-game flags Thu-Sun at $RunTime." `
    -Force

Write-Host "Installed: $TaskName"
Write-Host "Schedule:  Thu/Fri/Sat/Sun at $RunTime"
Write-Host "Output:    data/nrl/news_flags/processed/latest.json"
