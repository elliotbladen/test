param(
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [int]$Season = 2026,
    [int]$Round = 0,
    [string]$Game = "",
    [double]$ScanDelayHours = 3.0,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"

Set-Location $repoRoot

$argsList = @(
    "run",
    "--with", "requests",
    "--with", "beautifulsoup4",
    "python",
    "lib\scraper\nrl_postgame_scout.py",
    "--season", "$Season",
    "--scan-delay-hours", "$ScanDelayHours"
)

if ($Round -gt 0) {
    $argsList += @("--round", "$Round")
}

if ($Game -ne "") {
    $argsList += @("--game", "$Game")
}

if ($Force) {
    $argsList += "--force"
}

& $UvExe @argsList
