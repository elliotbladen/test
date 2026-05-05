param(
    [string]$UvExe = "C:\Users\ElliotBladen\.local\bin\uv.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$snapshotScript = Join-Path $repoRoot "lib\scraper\odds_snapshot.py"
$trackerScript = Join-Path $repoRoot "lib\scraper\odds_movement_tracker.py"
$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"

Set-Location $repoRoot

& $UvExe run --with requests python $snapshotScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $UvExe run python $trackerScript
exit $LASTEXITCODE
