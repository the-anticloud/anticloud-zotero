"""Offline AES-256-GCM secret vault with an scrypt-derived key.

Why the layering: AES-GCM is an AEAD, so it provides confidentiality *and*
integrity, but it needs a 32-byte key.  Keying it directly off a passphrase
would make offline guessing trivial, so the passphrase is stretched with scrypt
(N=2**14 by default) and the resulting key feeds GCM.  GCM's nonce is a random
12-byte value per record and is stored alongside the ciphertext.

This module deliberately raises on a missing key instead of falling back to a
weaker cipher.  A silent downgrade is the specific failure mode that turns an
environment problem into an undetected confidentiality breach.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

__all__ = [
    "VaultError",
    "DecryptionError",
    "KDF_PARAMS",
    "derive_key",
    "encrypt",
    "decrypt",
    "SealedBlob",
    "SecretVault",
]

# scrypt cost parameters. N=2**14 / r=8 / p=1 is the RFC 7914 interactive
# profile: ~230 ms on the reference machine, and deliberately slow to move an
# offline guessing attack off linear time.
KDF_PARAMS: dict[str, int] = {"n": 2**14, "r": 8, "p": 1, "dklen": 32, "salt_len": 16}


class VaultError(Exception):
    """Base class for vault failures."""


class DecryptionError(VaultError):
    """The ciphertext did not decrypt: wrong key, or the blob was altered.

    GCM cannot distinguish those two cases, and it must not: telling them apart
    would be an oracle.
    """


@dataclass(frozen=True)
class SealedBlob:
    """A sealed payload: salt, nonce and ciphertext, plus the KDF cost used."""

    salt: bytes
    nonce: bytes
    ciphertext: bytes
    kdf: Mapping[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.kdf:
            object.__setattr__(self, "kdf", dict(KDF_PARAMS))

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe representation with binary fields base64-encoded."""
        import base64

        return {
            "v": 1,
            "kdf": dict(self.kdf),
            "salt": base64.b64encode(self.salt).decode("ascii"),
            "nonce": base64.b64encode(self.nonce).decode("ascii"),
            "ct": base64.b64encode(self.ciphertext).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SealedBlob":
        import base64

        if not isinstance(data, Mapping):
            raise TypeError("blob data must be a mapping")
        if "salt" not in data or "nonce" not in data or "ct" not in data:
            raise KeyError("blob is missing one of 'salt', 'nonce', 'ct'")
        return cls(
            salt=base64.b64decode(data["salt"]),
            nonce=base64.b64decode(data["nonce"]),
            ciphertext=base64.b64decode(data["ct"]),
            kdf=dict(data.get("kdf") or KDF_PARAMS),
        )


def derive_key(
    passphrase: str | bytes,
    salt: bytes,
    n: int = KDF_PARAMS["n"],
    r: int = KDF_PARAMS["r"],
    p: int = KDF_PARAMS["p"],
    dklen: int = KDF_PARAMS["dklen"],
) -> bytes:
    """Stretch ``passphrase`` with scrypt into a 32-byte AES key."""
    if isinstance(passphrase, str):
        material = passphrase.encode("utf-8")
    elif isinstance(passphrase, (bytes, bytearray)):
        material = bytes(passphrase)
    else:
        raise TypeError("passphrase must be str or bytes")
    if not material:
        raise ValueError("passphrase must not be empty")
    if not isinstance(salt, (bytes, bytearray)) or len(salt) < 8:
        raise ValueError("salt must be at least 8 bytes")
    kdf = Scrypt(salt=bytes(salt), length=dklen, n=n, r=r, p=p)
    return kdf.derive(material)


def encrypt(
    plaintext: bytes,
    passphrase: str | bytes,
    *,
    n: int = KDF_PARAMS["n"],
    r: int = KDF_PARAMS["r"],
    p: int = KDF_PARAMS["p"],
    aad: bytes | None = None,
) -> SealedBlob:
    """Seal ``plaintext`` under a key derived from ``passphrase``."""
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("plaintext must be bytes-like")
    salt = os.urandom(KDF_PARAMS["salt_len"])
    nonce = os.urandom(12)  # GCM standard nonce length; random per message
    key = derive_key(passphrase, salt, n=n, r=r, p=p)
    ciphertext = AESGCM(key).encrypt(nonce, bytes(plaintext), aad)
    return SealedBlob(
        salt=salt,
        nonce=nonce,
        ciphertext=ciphertext,
        kdf={"n": n, "r": r, "p": p, "dklen": KDF_PARAMS["dklen"], "salt_len": len(salt)},
    )


def decrypt(blob: SealedBlob, passphrase: str | bytes, *, aad: bytes | None = None) -> bytes:
    """Open a sealed blob.  Raises :class:`DecryptionError` on any failure."""
    if not isinstance(blob, SealedBlob):
        raise TypeError("blob must be a SealedBlob")
    params = dict(blob.kdf or KDF_PARAMS)
    try:
        key = derive_key(
            passphrase,
            blob.salt,
            n=params.get("n", KDF_PARAMS["n"]),
            r=params.get("r", KDF_PARAMS["r"]),
            p=params.get("p", KDF_PARAMS["p"]),
            dklen=params.get("dklen", KDF_PARAMS["dklen"]),
        )
        return AESGCM(key).decrypt(blob.nonce, blob.ciphertext, aad)
    except InvalidTag as exc:
        raise DecryptionError(
            "AES-GCM authentication failed: wrong passphrase, or the ciphertext was altered"
        ) from exc


class SecretVault:
    """A dict of secrets, encrypted at rest as a single AES-GCM blob."""

    def __init__(self, path: str | os.PathLike[str], *, n: int = KDF_PARAMS["n"]) -> None:
        self.path = Path(path)
        self._n = n
        self._cache: dict[str, str] | None = None

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def store(self, secrets: Mapping[str, str], passphrase: str | bytes) -> Path:
        """Encrypt ``secrets`` and write them to disk.  Returns the path."""
        if not isinstance(secrets, Mapping):
            raise TypeError("secrets must be a mapping")
        for key in secrets:
            if not isinstance(key, str) or not key:
                raise ValueError("secret names must be non-empty strings")
        payload = json.dumps(dict(secrets), sort_keys=True).encode("utf-8")
        blob = encrypt(payload, passphrase, n=self._n)
        from .safeio import safe_write_json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        safe_write_json(self.path, blob.to_dict())
        self._cache = dict(secrets)
        return self.path

    def load(self, passphrase: str | bytes) -> dict[str, str]:
        """Decrypt and return the stored secrets."""
        import json as _json

        if not self.exists:
            raise VaultError(f"no vault at {self.path}")
        data = _json.loads(self.path.read_text(encoding="utf-8"))
        blob = SealedBlob.from_dict(data)
        plaintext = decrypt(blob, passphrase)
        try:
            result = _json.loads(plaintext.decode("utf-8"))
        except _json.JSONDecodeError as exc:
            raise DecryptionError("vault decrypted but did not contain valid JSON") from exc
        if not isinstance(result, dict):
            raise DecryptionError("vault decrypted but did not contain a JSON object")
        self._cache = dict(result)
        return dict(result)

    def get(self, name: str, passphrase: str | bytes, default: str | None = None) -> str | None:
        """Read one secret, returning ``default`` if absent."""
        secrets = self._cache if self._cache is not None else self.load(passphrase)
        return secrets.get(name, default)

    def verify_passphrase(self, passphrase: str | bytes) -> bool:
        """True iff the passphrase opens the vault.  Never leaks *why* it failed."""
        try:
            self.load(passphrase)
        except (DecryptionError, VaultError):
            return False
        return True

    def scrub_cache(self) -> None:
        """Drop the decrypted secrets held in memory."""
        self._cache = None