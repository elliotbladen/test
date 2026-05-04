param(
    [string]$TaskName = "BetMate NRL Historical Results",
    [string]$UvExe = "uv",
    [string]$RunTime = "17:00"
)

$ErrorActionPreference = "Stop"

$repoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..")
$scriptPath = Join-Path $repoRoot "lib\scraper\nrl_historical_results.py"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find scraper at $scriptPath"
}

$argument = "run --with playwright python `"$scriptPath`" --headless true --max-attempts 3 --retry-delay-seconds 60"
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
    -Description "Downloads NRL historical results xlsx from aussportsbetting.com every Monday at $RunTime. Saved to data/nrl/historical/latest.xlsx for BettingEngine ELO rebuild." `
    -Force

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: every Monday at $RunTime"
Write-Host "Output: data/nrl/historical/latest.xlsx"
