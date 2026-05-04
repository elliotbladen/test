param(
    [int]$Season = 2026,
    [string]$TaskName = "BettingEngine NRL Pricing",
    [string]$RunTime = "19:03",
    [string]$VenvPython = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not $VenvPython) {
    $VenvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path $VenvPython)) {
    throw "Python not found at $VenvPython. Run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
}

$scriptPath = Join-Path $repoRoot "scripts\prepare_round.py"

# --round 0 = auto-detect from BetMate fixture
$argument = "`"$scriptPath`" --season $Season --round 0"

$action   = New-ScheduledTaskAction -Execute $VenvPython -Argument $argument -WorkingDirectory $repoRoot
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $RunTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs BettingEngine NRL pricing every Monday at $RunTime. Reads fixture/injuries/referees from BetMate automatically." `
    -Force

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: every Monday at $RunTime"
Write-Host "Python: $VenvPython"
Write-Host "Command: $VenvPython $argument"
