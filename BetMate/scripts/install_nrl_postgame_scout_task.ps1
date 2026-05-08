param(
    [string]$TaskName = "BetMate NRL Postgame Scout",
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [int]$Season = 2026,
    [double]$ScanDelayHours = 3.0
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\nrl_postgame_scout.py"
$runnerPath = Join-Path $repoRoot "scripts\run_nrl_postgame_scout.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find NRL postgame Scout scraper at $scriptPath"
}

if (-not (Test-Path $runnerPath)) {
    throw "Could not find NRL postgame Scout runner at $runnerPath"
}

if (-not (Test-Path $UvExe)) {
    throw "Could not find uv executable at $UvExe"
}

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"scripts\run_nrl_postgame_scout.ps1`" -UvExe `"$UvExe`" -Season $Season -ScanDelayHours $ScanDelayHours"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $repoRoot

# Common post-game windows. The Python script still checks the fixture and only
# processes games that are far enough past kickoff.
$triggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At "22:50"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday   -At "21:00"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday   -At "23:00"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "18:00"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "20:30"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "22:45"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday   -At "17:00"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday   -At "19:15")
)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 25)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Description "Runs Scout NRL post-game scans after matches and stores material injury, suspension and late-team-news signals." `
    -Force

Write-Host "Installed: $TaskName"
Write-Host "Schedule:  Common Thu-Sun post-game scan windows"
Write-Host "Output:    data\nrl\scout\postgame\processed"
