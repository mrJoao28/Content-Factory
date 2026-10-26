param([switch]$SkipCodexSdk, [switch]$StopRunning, [switch]$InstallCodexSdk)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. (Join-Path $PSScriptRoot 'runtime.ps1')
if ($StopRunning) { & (Join-Path $PSScriptRoot 'stop.ps1') }
Assert-FactoryFrontendUnlocked (Get-Location).Path
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
# Older reused environments can expose an incomplete global SQLAlchemy installation.
& $pythonPath -c "import sqlalchemy.dialects.postgresql; import alembic"
if ($LASTEXITCODE) {
    Write-Warning 'Repairing the SQLAlchemy installation inside the virtual environment.'
    & $pythonPath -m pip install --ignore-installed --no-deps 'sqlalchemy>=2.0,<3'
    if ($LASTEXITCODE) { throw 'SQLAlchemy repair failed. Recreate an isolated virtual environment or check network settings.' }
    & $pythonPath -c "import sqlalchemy.dialects.postgresql; import alembic"
    if ($LASTEXITCODE) { throw 'Migration dependencies are unavailable. See docs/TROUBLESHOOTING.md.' }
}

if ($InstallCodexSdk -and -not $SkipCodexSdk) {
    & $pythonPath -m pip install openai-codex
    if ($LASTEXITCODE) { Write-Warning 'Official SDK unavailable. The official CLI adapter remains usable.' }
}
foreach ($directory in @('data','output','assets/characters','assets/backgrounds','assets/props','assets/voices','assets/music','assets/sound-effects')) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}
if (-not (Test-Path '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
& npm.cmd ci --prefix apps/web
if ($LASTEXITCODE) { throw 'Frontend dependency installation failed. If npm reports EPERM on a .node file, stop the running frontend (Ctrl+C in scripts/dev.ps1), then rerun setup. Do not delete package-lock.json.' }
$env:PYTHONPATH = Join-Path (Get-Location) 'services/api'
& $pythonPath -m alembic upgrade head
if ($LASTEXITCODE) { throw 'Database migration failed' }
& $pythonPath -c "from factory.db import seed; seed()"
& $pythonPath -m factory.doctor
Write-Host 'Setup complete. Activate missing dependencies shown by doctor.'
Write-Host 'Run: .\scripts\dev.ps1 then connect ChatGPT in Settings. Codex CLI/SDK is optional; use -InstallCodexSdk only for the compatibility provider.'
