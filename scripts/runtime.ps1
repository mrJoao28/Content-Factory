# Shared local process checks. Dot-source from setup/dev/stop.
function Stop-FactoryProcessTree([int]$TargetId) {
    if ($TargetId -le 0 -or $TargetId -eq $PID) { return $false }
    if (-not (Get-Process -Id $TargetId -ErrorAction SilentlyContinue)) { return $true }
    try {
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = 'taskkill.exe'
        $info.Arguments = "/PID $TargetId /T /F"
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $killer = New-Object System.Diagnostics.Process
        $killer.StartInfo = $info
        [void]$killer.Start()
        $stdout = $killer.StandardOutput.ReadToEndAsync()
        $stderr = $killer.StandardError.ReadToEndAsync()
        if (-not $killer.WaitForExit(10000)) { $killer.Kill() }
        $killer.Dispose()
    } catch { }
    # taskkill may race with a naturally exiting child. Never mask the original error.
    if (Get-Process -Id $TargetId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $TargetId -Force -ErrorAction SilentlyContinue
    }
    return -not [bool](Get-Process -Id $TargetId -ErrorAction SilentlyContinue)
}

function Assert-FactoryPortFree([int]$Port) {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() }
    catch { throw "Port $Port is already in use. Run .\scripts\stop.ps1 for this project, or choose different -ApiPort/-WebPort values." }
    finally { $listener.Stop() }
}

function Assert-FactoryFrontendUnlocked([string]$RootPath) {
    $nativePath = Join-Path $RootPath 'apps/web/node_modules/@next/swc-win32-x64-msvc'
    foreach ($file in @(Get-ChildItem -LiteralPath $nativePath -Filter '*.node' -ErrorAction SilentlyContinue)) {
        try {
            $handle = [System.IO.File]::Open($file.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            $handle.Dispose()
        } catch {
            throw 'Next.js native module is locked or inaccessible. Run .\scripts\setup.ps1 -StopRunning in the same Windows account that started the app. Close old dev terminals with Ctrl+C if needed. No dependencies were changed by this attempt.'
        }
    }
}

function Select-FactoryProcesses($Processes, [string]$RootPath) {
    @($Processes | Where-Object {
        $command = $_.CommandLine
        $_.Name -in @('node.exe','python.exe','pythonw.exe') -and
        $command -and $command.IndexOf($RootPath + '\', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        ($command -match 'uvicorn\s+factory\.main:app' -or $command -match 'node_modules[\\/]next[\\/].*(?:next|start-server\.js)')
    })
}
