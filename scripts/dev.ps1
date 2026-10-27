param([ValidateRange(1024,65535)][int]$ApiPort=8000,[ValidateRange(1024,65535)][int]$WebPort=3000)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. (Join-Path $PSScriptRoot 'runtime.ps1')
$rootPath=(Get-Location).Path
$pythonPath=Join-Path $rootPath '.venv/Scripts/python.exe'
$nextPath=Join-Path $rootPath 'apps/web/node_modules/next/dist/bin/next'
if (-not (Test-Path $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path $nextPath)) { throw 'Frontend dependencies are incomplete. Run .\scripts\setup.ps1 -StopRunning before starting dev.' }
if ($ApiPort -eq $WebPort) { throw 'API and frontend require different ports.' }
Assert-FactoryPortFree $ApiPort
Assert-FactoryPortFree $WebPort
$nodePath=(Get-Command node -ErrorAction Stop).Source
$env:PYTHONPATH=Join-Path $rootPath 'services/api'
$env:API_PORT="$ApiPort"
$env:WEB_PORT="$WebPort"
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:$ApiPort"
$env:NEXT_TELEMETRY_DISABLED='1'
& $pythonPath -m alembic upgrade head
if($LASTEXITCODE){throw 'Database migration failed. Existing data was preserved; inspect the migration error before starting.'}
$logsPath=Join-Path $rootPath 'data/logs'
New-Item -ItemType Directory -Force -Path $logsPath | Out-Null
$apiProcess=$null
$webProcess=$null
function Read-StartupErrors {
    foreach ($name in @('api-error.log','web-error.log')) {
        $file=Join-Path $logsPath $name
        if (Test-Path $file) { Write-Host "--- $name ---"; Get-Content -LiteralPath $file -Tail 18 | Write-Host }
    }
}
function Wait-FactoryReady([string]$Url, $Process) {
    $deadline=[DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) { Read-StartupErrors; throw "Service exited before becoming ready (exit $($Process.ExitCode)). See data/logs." }
        try {
            $response=Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
    Read-StartupErrors
    throw "Service readiness timed out: $Url. See data/logs."
}
try {
    $apiArgs=@('-m','uvicorn','factory.main:app','--app-dir',('"'+(Join-Path $rootPath 'services/api')+'"'),'--host','127.0.0.1','--port',"$ApiPort",'--no-access-log')
    $apiProcess=Start-Process -FilePath $pythonPath -ArgumentList $apiArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsPath 'api.log') -RedirectStandardError (Join-Path $logsPath 'api-error.log')
    Wait-FactoryReady "http://127.0.0.1:$ApiPort/health" $apiProcess
    # Start the installed entrypoint directly; do not rely on npm's .cmd shim.
    $webProcess=Start-Process -FilePath $nodePath -WorkingDirectory (Join-Path $rootPath 'apps/web') -ArgumentList @(('"'+$nextPath+'"'),'dev','--hostname','127.0.0.1','--port',"$WebPort") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsPath 'web.log') -RedirectStandardError (Join-Path $logsPath 'web-error.log')
    Wait-FactoryReady "http://127.0.0.1:$WebPort" $webProcess
    Write-Host "READY - Web: http://127.0.0.1:$WebPort | API docs: http://127.0.0.1:$ApiPort/docs"
    Write-Host 'Closing the browser keeps the worker running. Ctrl+C stops development.'
    while ($true) {
        $apiProcess.Refresh(); $webProcess.Refresh()
        if ($apiProcess.HasExited -or $webProcess.HasExited) { Read-StartupErrors; throw 'A development service stopped. See data/logs.' }
        Start-Sleep -Seconds 1
    }
} finally {
    foreach ($process in @($webProcess,$apiProcess)) {
        if ($null -ne $process -and -not (Stop-FactoryProcessTree $process.Id)) {
            Write-Warning "Could not stop project process $($process.Id). Run scripts/stop.ps1 from your Windows account."
        }
    }
}
