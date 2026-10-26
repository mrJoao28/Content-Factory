param([switch]$Browser)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$pythonPath=Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonPath)) { throw 'Run setup.ps1 first' }
& $pythonPath -m pytest -q --basetemp=./data/pytest-tmp
if ($LASTEXITCODE) { throw 'Pytest failed' }
& $pythonPath -m ruff check services tests scripts
if ($LASTEXITCODE) { throw 'Ruff failed' }
& npm.cmd run typecheck --prefix apps/web
if ($LASTEXITCODE) { throw 'Typecheck failed' }
& npm.cmd test --prefix apps/web
if ($LASTEXITCODE) { throw 'Vitest failed' }
& npm.cmd run build --prefix apps/web
if ($LASTEXITCODE) { throw 'Next.js build failed' }
if ($Browser) {
    & npm.cmd run test:e2e --prefix apps/web
    if ($LASTEXITCODE) { throw 'Playwright failed' }
}
