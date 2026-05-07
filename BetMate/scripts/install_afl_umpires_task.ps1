param(
    [string]$TaskName = "BetMATE AFL Umpires Fetch",
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [string]$RunTime = "12:00",
    [int]$Season = 2026
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\afl_umpires.py"
$runnerPath = Join-Path $repoRoot "scripts\run_afl_umpires.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find AFL umpire scraper at $scriptPath"
}

if (-not (Test-Path $runnerPath)) {
    throw "Could not find AFL umpire runner at $runnerPath"
}

if (-not (Test-Path $UvExe)) {
    throw "Could not find uv executable at $UvExe"
}

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"scripts\run_afl_umpires.ps1`" -UvExe `"$UvExe`" -Season $Season"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $repoRoot
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
    -Description "Scrapes AFL umpire appointments from AFLUA into BetMATE every Wednesday at $RunTime." `
    -Force

Write-Host "Installed: $TaskName"
Write-Host "Schedule:  Wednesday at $RunTime"
Write-Host "Output:    data/afl/umpires/processed/latest-umpires.csv"
