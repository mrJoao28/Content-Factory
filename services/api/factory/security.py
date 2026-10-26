import ctypes
import hashlib
import json
import os
import subprocess
from pathlib import Path

from .config import settings


class ConfigurationRequired(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


class TransientFailure(RuntimeError):
    pass


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError("Path outside storage root")
    return path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, *, timeout=120, input=None, cwd=None):
    result = subprocess.run([str(x) for x in args], input=input, capture_output=True,
                            timeout=timeout, cwd=cwd, shell=False,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        # Do not expose command arguments, OAuth response bodies or environment variables.
        raise RuntimeError(f"{Path(str(args[0])).stem}: process failed ({result.returncode})")
    return result.stdout


class Vault:
    """Windows user-bound DPAPI. Other systems require an OS keyring backend."""
    def __init__(self, root=None):
        self.root = root or settings.storage_root / "credentials"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name):
        if name not in {"google", "youtube", "tiktok"}:
            raise ValueError("Unknown credential slot")
        return self.root / (name + ".bin")

    def _dpapi(self, value, encrypt):
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        buffer = ctypes.create_string_buffer(value)
        source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        target = Blob()
        method = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
        if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise ConfigurationRequired("Windows credential vault unavailable for this user")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(target.pbData)

    def put(self, name, value):
        serialized = json.dumps(value)
        if os.name == "nt":
            path = self._path(name)
            temp = path.with_suffix(".tmp")
            temp.write_bytes(self._dpapi(serialized.encode(), True))
            temp.replace(path)
        else:
            import keyring
            keyring.set_password("ai-content-factory", name, serialized)

    def get(self, name):
        if os.name == "nt":
            path = self._path(name)
            return json.loads(self._dpapi(path.read_bytes(), False)) if path.exists() else None
        import keyring
        value = keyring.get_password("ai-content-factory", name)
        return json.loads(value) if value else None

    def delete(self, name):
        if os.name == "nt":
            self._path(name).unlink(missing_ok=True)
        else:
            import keyring
            if self.get(name):
                keyring.delete_password("ai-content-factory", name)


def terminate_tree(process):
    """Terminate only this application-owned process and its descendants."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=15, shell=False,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        import signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)
