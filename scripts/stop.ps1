$ErrorActionPreference = 'Stop'
$rootPath = [System.IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
. (Join-Path $PSScriptRoot 'runtime.ps1')
try {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
} catch {
    throw 'Cannot inspect process ownership in this Windows session. Close the original dev terminal with Ctrl+C, or run stop.ps1 from the Windows account that started the app. No processes were stopped.'
}
$targets = @(Select-FactoryProcesses $processes $rootPath)
foreach ($target in $targets) {
    if (-not (Stop-FactoryProcessTree ([int]$target.ProcessId))) {
        throw "Could not stop project process $($target.ProcessId). Close its terminal with Ctrl+C and retry. Other applications were not targeted."
    }
    Write-Host "Stopped project process $($target.ProcessId)."
}
if (-not $targets.Count) { Write-Host 'No matching project API/Next.js processes found.' }
