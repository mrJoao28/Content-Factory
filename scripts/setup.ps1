param([switch]$SkipCodexSdk)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Require-Command($Name) { if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Missing $Name. See docs/SETUP_WINDOWS.md" } }
Require-Command node
Require-Command python
Require-Command npm.cmd
$nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 20) { throw 'Install Node.js 22 LTS or later.' }
& python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
if ($LASTEXITCODE) { throw 'Python 3.11+ required' }
if (-not (Test-Path '.venv/Scripts/python.exe')) { & python -m venv .venv }
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
& $pythonPath -m pip install -e '.[dev]'
if ($LASTEXITCODE) { throw 'Dependency installation failed. Check network/proxy settings.' }
if (-not $SkipCodexSdk) {
    & $pythonPath -m pip install openai-codex
    if ($LASTEXITCODE) { Write-Warning 'Official SDK unavailable. The official CLI adapter remains usable.' }
}
foreach ($directory in @('data','output','assets/characters','assets/backgrounds','assets/props','assets/voices','assets/music','assets/sound-effects')) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}
if (-not (Test-Path '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
& npm.cmd ci --prefix apps/web
if ($LASTEXITCODE) { throw 'Frontend dependency installation failed' }
$env:PYTHONPATH = Join-Path (Get-Location) 'services/api'
& $pythonPath -m alembic upgrade head
if ($LASTEXITCODE) { throw 'Database migration failed' }
& $pythonPath -c "from factory.db import seed; seed()"
& $pythonPath -m factory.doctor
Write-Host 'Setup complete. Activate missing dependencies shown by doctor.'
Write-Host 'Run: codex login; .\scripts\dev.ps1'
