param(
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [int]$Season = 2026
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"
& $UvExe run --with requests --with beautifulsoup4 python lib\scraper\nrl_referees.py --season $Season
