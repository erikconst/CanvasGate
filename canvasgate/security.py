"""Local boundaries and secret handling. CLI context isolation is not an OS sandbox."""

import json
import os
from pathlib import Path, PureWindowsPath
import re

from .backends import WorkflowError


SECRET_ENV = re.compile(r"(?:API_KEY|PASSWORD|SECRET|TOKEN|PRIVATE_KEY)", re.I)
SECRET_PATTERNS = [
    re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{18,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.~+/-]{20,}=*"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]+-----|$)"),
    re.compile(r"(?i)(?:api[_-]?key|password|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"']?[A-Za-z0-9_./+\-=]{20,}"),
]
DENIED = {".git", ".obsidian", ".canvasgate", ".ssh", ".aws", ".azure", "node_modules", ".venv"}


def secret_values():
    return [value for key, value in os.environ.items() if SECRET_ENV.search(key) and len(value) >= 8]


def redact(value):
    if isinstance(value, dict):
        return {redact(key) if isinstance(key, str) else key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    for secret in secret_values():
        value = value.replace(secret, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def ensure_no_secrets(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if redact(text) != text:
        raise WorkflowError("Sensitive credential detected; refusing to persist or forward this payload.")


def relative_name(name):
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name and os.name != "nt":
        raise WorkflowError("A safe vault-relative path is required.")
    path = Path(name)
    if path.is_absolute() or PureWindowsPath(name).drive or ".." in path.parts:
        raise WorkflowError("Absolute paths and parent traversal are forbidden.")
    parts = [part.casefold() for part in path.parts]
    if any(part in DENIED or part == ".env" or part.startswith(".env.") for part in parts):
        raise WorkflowError("Access to application metadata or credential files is forbidden.")
    if path.suffix.casefold() in {".pem", ".key", ".pfx", ".p12"} or path.name.casefold() in {"id_rsa", "id_ed25519", "credentials"}:
        raise WorkflowError("Credential files cannot be workflow sources.")
    return path.as_posix()


def reject_links(root, name):
    current = root
    for part in Path(name).parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise WorkflowError("Symlinks and junctions are not permitted in workflow paths.")


class SecurityPolicy:
    def __init__(self, vault, config=None, *, strict_isolation=False):
        self.vault = Path(vault).resolve()
        config = config or {}
        if not isinstance(config, dict) or set(config) - {"read_dirs", "write_dirs", "require_process_isolation", "allow_cli"}:
            raise WorkflowError("Unknown permission setting.")
        self.read_dirs = self.directories(config.get("read_dirs", ["."]))
        self.write_dirs = self.directories(config.get("write_dirs", ["."]))
        for key in ("require_process_isolation", "allow_cli"):
            if key in config and type(config[key]) is not bool:
                raise WorkflowError(f"{key} must be boolean.")
        self.strict_isolation = strict_isolation or config.get("require_process_isolation", False)
        self.allow_cli = config.get("allow_cli", True)

    def directories(self, names):
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise WorkflowError("Directory permissions must be a list; an empty list denies access.")
        result = []
        for name in names:
            safe = "." if name == "." else relative_name(name)
            reject_links(self.vault, safe)
            path = (self.vault / safe).resolve()
            if not path.is_relative_to(self.vault):
                raise WorkflowError("Directory permission escapes the vault.")
            result.append(path)
        return result

    def path(self, name, *, writing=False, pinned=False):
        safe = relative_name(name)
        if pinned and not writing:
            lexical = self.vault / safe
            if not any(lexical.is_relative_to(directory) for directory in self.read_dirs):
                raise WorkflowError("Source is outside the declared read directories.")
            return lexical
        reject_links(self.vault, safe)
        path = (self.vault / safe).resolve()
        allowed = self.write_dirs if writing else self.read_dirs
        if not path.is_relative_to(self.vault) or not any(path.is_relative_to(directory) for directory in allowed):
            raise WorkflowError("Path is outside the declared directory permissions.")
        return path

    def check_backend(self, backend):
        from .backends import CodexBackend
        if isinstance(backend, CodexBackend) and (self.strict_isolation or not self.allow_cli):
            raise WorkflowError("This policy forbids host Codex CLI execution. Use mock/API; CLI read-only mode is not process isolation.")

    def public(self):
        return {"read_dirs": [path.relative_to(self.vault).as_posix() for path in self.read_dirs],
                "write_dirs": [path.relative_to(self.vault).as_posix() for path in self.write_dirs],
                "require_process_isolation": self.strict_isolation, "allow_cli": self.allow_cli}


def cli_environment():
    keep = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME",
            "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "COMSPEC", "CODEX_HOME", "CODEX_API_KEY"}
    return {key: value for key, value in os.environ.items() if key.upper() in keep}
