"""Credential storage with Fernet symmetric encryption.

Why not Supabase Vault? Because Vault is per-row and we want per-user-key
indexing + RLS-clean access. Why not KMS? Overkill for v0.1 and adds a cloud
dependency. Fernet + a strong env-provided key is plenty for now; swap to
cloud KMS later by changing this file only.
"""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken


def _key() -> bytes:
    raw = os.environ.get("JAI_CREDENTIALS_KEY", "")
    if not raw:
        raise RuntimeError(
            "JAI_CREDENTIALS_KEY not set. Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    # accept either a raw base64 url-safe key or 32 raw bytes hex
    if len(raw) == 44 and raw.endswith("="):
        return raw.encode()
    return base64.urlsafe_b64encode(bytes.fromhex(raw))


def encrypt(value: str) -> bytes:
    return Fernet(_key()).encrypt(value.encode("utf-8"))


def decrypt(blob: bytes) -> str:
    try:
        return Fernet(_key()).decrypt(blob).decode("utf-8")
    except InvalidToken as e:
        raise RuntimeError("credential decryption failed (wrong key?)") from e
