# Run from any working directory after installing the README dependencies.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Create .venv and install backend requirements first; see README.md.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is required; see README.md.' }
$previousPluginSetting = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
Push-Location $projectRoot
try {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    & $projectPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed.' }
    & $projectPython scripts\prepare_github.py
    if ($LASTEXITCODE -ne 0) { throw 'Publication boundary check failed.' }
    & $projectPython -m pytest -c backend\pytest.ini -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    Set-Location (Join-Path $projectRoot 'frontend')
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    & npm.cmd run build:portfolio
    if ($LASTEXITCODE -ne 0) { throw 'Portfolio build failed.' }
    Set-Location $projectRoot
    & $projectPython scripts\check_portfolio_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Portfolio bundle safety check failed.' }
    & node scripts\check_portfolio_render.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Portfolio render check failed.' }
    Write-Host 'Dependencies, publication audit, backend tests, both builds, and portfolio safety/render checks passed.'
} finally {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = $previousPluginSetting
    Pop-Location
}
