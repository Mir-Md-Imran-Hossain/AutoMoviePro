from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import DATA_DIR


def _key_path() -> Path:
    return DATA_DIR / ".secret.key"


def _fernet() -> Fernet:
    path = _key_path()
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
    return Fernet(path.read_bytes().strip())


def encrypt_text(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def machine_fingerprint() -> str:
    raw = str(DATA_DIR.resolve())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def b64file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")
