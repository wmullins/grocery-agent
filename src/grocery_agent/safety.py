from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import tempfile
from pathlib import Path

AGENT_MARKER = "agent: grocery-agent"
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
LONG_NUMBER_RE = re.compile(r"\b\d{9,}\b")
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)


class SafetyError(RuntimeError):
    pass


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def ensure_private_file(path: Path) -> Path:
    if path.exists():
        path.chmod(0o600)
    return path


def atomic_write_text(path: Path, content: str, mode: int = 0o600) -> None:
    ensure_private_dir(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
        path.chmod(mode)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_or_create_hmac_key(path: Path) -> bytes:
    ensure_private_dir(path.parent)
    if path.exists():
        ensure_private_file(path)
        key = path.read_bytes()
        if len(key) < 32:
            raise SafetyError(f"HMAC key is too short: {path}")
        return key
    key = secrets.token_bytes(32)
    atomic_write_text(path, key.hex() + "\n")
    return key


class IdHasher:
    def __init__(self, key_path: Path) -> None:
        self._key = load_or_create_hmac_key(key_path)

    def hash(self, value: str) -> str:
        return hmac.new(self._key, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def short(self, value: str, length: int = 12) -> str:
        return self.hash(value)[:length]


def redact(value: str) -> str:
    text = EMAIL_RE.sub("[email]", value)
    text = POSTCODE_RE.sub("[postcode]", text)
    text = LONG_NUMBER_RE.sub("[number]", text)
    return text


def is_agent_owned(content: str) -> bool:
    return AGENT_MARKER in content


def assert_within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise SafetyError(f"Path escapes allowed root: {path}")
    return resolved
