# For the repository owner, after reviewing code and successful local checks.
param([string]$Branch='feat/content-factory')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $PSScriptRoot/test.ps1 -Browser
if($LASTEXITCODE){throw 'Validation failed'}
& git switch -c $Branch
if($LASTEXITCODE){throw 'Could not create feature branch'}
& git add AGENTS.md README.md .env.example .gitignore pyproject.toml alembic.ini apps services packages templates scripts tests docs docker-compose.yml
if($LASTEXITCODE){throw 'Could not stage files'}
& git commit -m 'feat: implement local content production studio and integrations'
if($LASTEXITCODE){throw 'Commit failed'}
Write-Host 'Review the feature branch before merging to main. No push performed.'
