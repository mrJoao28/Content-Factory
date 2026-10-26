param([int]$ApiPort=8000,[int]$WebPort=3000)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$rootPath=(Get-Location).Path
$pythonPath=Join-Path $rootPath '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonPath)) { throw 'Run scripts/setup.ps1 first' }
$env:PYTHONPATH=Join-Path $rootPath 'services/api'
$env:API_PORT="$ApiPort"
$env:WEB_PORT="$WebPort"
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:$ApiPort"
$env:NEXT_TELEMETRY_DISABLED='1'
$logsPath=Join-Path $rootPath 'data/logs'
New-Item -ItemType Directory -Force -Path $logsPath | Out-Null
$apiProcess=$null
$webProcess=$null
try {
    $apiProcess=Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','factory.main:app','--host','127.0.0.1','--port',"$ApiPort",'--no-access-log') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsPath 'api.log') -RedirectStandardError (Join-Path $logsPath 'api-error.log')
    $npmPath=(Get-Command npm.cmd).Source
    $webProcess=Start-Process -FilePath $npmPath -ArgumentList @('run','dev','--prefix','apps/web','--','--port',"$WebPort") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsPath 'web.log') -RedirectStandardError (Join-Path $logsPath 'web-error.log')
    Write-Host "Web: http://127.0.0.1:$WebPort | API docs: http://127.0.0.1:$ApiPort/docs"
    Write-Host 'Worker runs inside the API process. Closing the browser does not stop it. Ctrl+C stops development.'
    while (-not $apiProcess.HasExited -and -not $webProcess.HasExited) { Start-Sleep -Seconds 1 }
} finally {
    foreach ($process in @($apiProcess,$webProcess)) {
        if ($null -ne $process -and -not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null }
    }
}
