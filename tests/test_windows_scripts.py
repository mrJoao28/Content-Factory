"""Regression checks for Windows startup and scoped process cleanup."""

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows process scripts")


def powershell(script):
    executable = shutil.which("powershell.exe")
    assert executable
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_stop_only_selects_api_and_next_for_exact_project():
    output = powershell(r"""
$ErrorActionPreference='Stop'
. ./scripts/runtime.ps1
$root='C:\Work\Factory'
$processes=@(
 [pscustomobject]@{Name='python.exe';ProcessId=10;CommandLine='C:\Work\Factory\.venv\Scripts\python.exe -m uvicorn factory.main:app'},
 [pscustomobject]@{Name='node.exe';ProcessId=11;CommandLine='node C:\Work\Factory\apps\web\node_modules\next\dist\server\lib\start-server.js'},
 [pscustomobject]@{Name='node.exe';ProcessId=12;CommandLine='node C:\Work\Factory-other\node_modules\next\dist\bin\next'},
 [pscustomobject]@{Name='python.exe';ProcessId=13;CommandLine='C:\Work\Factory\.venv\Scripts\python.exe unrelated.py'},
 [pscustomobject]@{Name='powershell.exe';ProcessId=14;CommandLine='C:\Work\Factory\test.ps1 uvicorn factory.main:app'}
)
$selected=@(Select-FactoryProcesses $processes $root)
if (($selected.ProcessId -join ',') -ne '10,11') { throw 'Wrong project processes selected' }
'passed'
""")
    assert "passed" in output


def test_busy_port_is_reported_before_launch():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        output = powershell(f"""
$ErrorActionPreference='Stop'
. ./scripts/runtime.ps1
try {{ Assert-FactoryPortFree {port}; throw 'Did not detect occupied port' }}
catch {{ if ($_.Exception.Message -notlike '*already in use*') {{ throw }}; 'passed' }}
""")
    assert "passed" in output


def test_cleanup_does_not_mask_original_error_and_scripts_parse():
    output = powershell(r"""
$ErrorActionPreference='Stop'
. ./scripts/runtime.ps1
try { try { throw 'original startup error' } finally { [void](Stop-FactoryProcessTree 2147483647) } }
catch { if ($_.Exception.Message -ne 'original startup error') { throw }; 'passed' }
Get-ChildItem scripts/*.ps1 | ForEach-Object {
 $parseErrors=$null
 [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$parseErrors)
 if ($parseErrors) { throw ($parseErrors | Out-String) }
}
""")
    assert "passed" in output
