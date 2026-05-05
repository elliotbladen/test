param(
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe",
    [int]$Season = 2026
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"

Set-Location $repoRoot
& $UvExe run --with requests --with beautifulsoup4 python "lib\scraper\nrl_news_flags.py" --season $Season
