$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
foreach($name in @('node','python','npm.cmd','codex')) {
    $command=Get-Command $name -ErrorAction SilentlyContinue
    if($command){ Write-Host "$name : INSTALLED ($($command.Source))" } else { Write-Host "$name : UNAVAILABLE" }
}
$pythonPath=Join-Path (Get-Location) '.venv/Scripts/python.exe'
if(-not (Test-Path $pythonPath)){Write-Host 'Python environment: UNAVAILABLE. Run setup.ps1';exit 1}
$env:PYTHONPATH=Join-Path (Get-Location) 'services/api'
& $pythonPath -m factory.doctor
if($LASTEXITCODE){throw 'Doctor could not execute'}
