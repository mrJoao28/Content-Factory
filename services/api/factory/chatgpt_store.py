"""All ChatGPT credential records are encrypted by the existing OS vault."""

import copy
import os
from contextlib import contextmanager
from uuid import uuid4

from filelock import FileLock, Timeout

from .config import settings
from .security import ConfigurationRequired, Vault


class ChatGPTStore:
    def __init__(self, vault=None, root=None):
        self._vault = vault
        self._root = root

    @contextmanager
    def locked(self):
        root = self._root or settings.storage_root / "credentials"
        try:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if root.is_symlink():
                raise ConfigurationRequired("Unsafe ChatGPT credential directory")
            if os.name != "nt":
                os.chmod(root, 0o700)
                if self._vault is None:
                    import keyring

                    backend = keyring.get_keyring()
                    backends = getattr(backend, "backends", [backend])
                    allowed = (
                        "keyring.backends.SecretService",
                        "keyring.backends.kwallet",
                        "keyring.backends.macOS",
                    )
                    secure = next(
                        (b for b in backends if type(b).__module__.startswith(allowed) and b.priority > 0),
                        None,
                    )
                    if secure is None:
                        raise ConfigurationRequired(
                            "Secure OS credential storage unavailable. Configure a system keyring."
                        )
                    # Use the selected secure backend only, never an alternate plaintext fallback.
                    self._vault = _SystemVault(secure)
            with FileLock(str(root / "chatgpt.lock"), timeout=15):
                vault = self._vault or Vault(root)
                yield vault
        except (OSError, Timeout):
            raise ConfigurationRequired(
                "ChatGPT secure storage unavailable or busy. Retry from the same Windows account."
            ) from None

    def read(self):
        with self.locked() as vault:
            return copy.deepcopy(vault.get("chatgpt") or {"accounts": [], "active_id": None, "host_id": None})

    def update(self, change):
        with self.locked() as vault:
            value = vault.get("chatgpt") or {"accounts": [], "active_id": None, "host_id": None}
            if not value.get("host_id"):
                value["host_id"] = "urn:uuid:" + str(uuid4())
            result = change(value)
            vault.put("chatgpt", value)
            return copy.deepcopy(result)


class _SystemVault:
    def __init__(self, backend):
        self.backend = backend

    def get(self, name):
        import json

        try:
            value = self.backend.get_password("ai-content-factory", name)
            return json.loads(value) if value else None
        except Exception:
            raise ConfigurationRequired("Secure system credential storage unavailable") from None

    def put(self, name, value):
        import json

        try:
            self.backend.set_password("ai-content-factory", name, json.dumps(value))
        except Exception:
            raise ConfigurationRequired("Secure system credential storage unavailable") from None
