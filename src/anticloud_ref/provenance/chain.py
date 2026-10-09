"""Append-only SHA3-256 provenance chain with optional Ed25519 signatures.

Every record commits to its predecessor, so altering any historical record
invalidates every record after it.  ``verify()`` walks the chain and, on
failure, reports the *index and digest* of the first record that does not check
out, which is what makes the failure actionable rather than a bare ``False``.

The chain is not a trusted timestamp: a whole chain can be rewritten from
scratch by anyone with write access.  Signing each record with Ed25519 under a
key whose public half is distributed out of band is what prevents that, and
``verify_signatures`` checks exactly that.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

__all__ = [
    "GENESIS_DIGEST",
    "ProvenanceChain",
    "ProvenanceRecord",
    "ChainVerification",
    "SignKeyPair",
    "generate_signing_key",
    "load_signing_key",
    "sha3_256_hex",
]

# The parent digest of the first record.  Any constant would do; making it a
# recognisable 64 '0' chars means a forged chain cannot pass for the real one
# by omitting the genesis link.
GENESIS_DIGEST = "0" * 64

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_INDEX_FIELDS = ("index", "timestamp", "artifact", "artifact_hash", "parent", "nonce")


def sha3_256_hex(payload: bytes) -> str:
    """SHA3-256 of ``payload`` as lowercase hex."""
    import hashlib

    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    return hashlib.sha3_256(bytes(payload)).hexdigest()


def _canonical(record: dict[str, Any]) -> bytes:
    """Deterministic serialisation used for hashing.

    Sort keys and fix separators so the digest depends only on the record's
    content, not on dict insertion order or Python version.
    """
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


@dataclass(frozen=True)
class ProvenanceRecord:
    """One immutable link in the chain."""

    index: int
    timestamp: str
    artifact: str
    artifact_hash: str
    parent: str
    nonce: str
    digest: str
    signature: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "artifact": self.artifact,
            "artifact_hash": self.artifact_hash,
            "parent": self.parent,
            "nonce": self.nonce,
            "digest": self.digest,
            "signature": self.signature,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceRecord":
        if not isinstance(data, dict):
            raise TypeError("record data must be a dict")
        for key in _INDEX_FIELDS + ("digest",):
            if key not in data:
                raise KeyError(f"record is missing required field {key!r}")
        return cls(
            index=int(data["index"]),
            timestamp=str(data["timestamp"]),
            artifact=str(data["artifact"]),
            artifact_hash=str(data["artifact_hash"]),
            parent=str(data["parent"]),
            nonce=str(data["nonce"]),
            digest=str(data["digest"]),
            signature=data.get("signature"),
            extra=data.get("extra") or {},
        )

    def recompute(self) -> str:
        """Recompute this record's digest from its own fields."""
        body = {
            "index": self.index,
            "timestamp": self.timestamp,
            "artifact": self.artifact,
            "artifact_hash": self.artifact_hash,
            "parent": self.parent,
            "nonce": self.nonce,
            "extra": self.extra,
        }
        return sha3_256_hex(_canonical(body))

    def signing_bytes(self) -> bytes:
        """Bytes covered by the Ed25519 signature (the digest)."""
        return bytes.fromhex(self.digest)


@dataclass(frozen=True)
class ChainVerification:
    """Structured verdict from :meth:`ProvenanceChain.verify`."""

    valid: bool
    length: int
    head: str
    broken_at_index: int | None = None
    broken_file: str | None = None
    reason: str | None = None
    signature_invalid_at_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "length": self.length,
            "head": self.head,
            "broken_at_index": self.broken_at_index,
            "broken_file": self.broken_file,
            "reason": self.reason,
            "signature_invalid_at_index": self.signature_invalid_at_index,
        }

    def __bool__(self) -> bool:
        return self.valid


@dataclass(frozen=True)
class SignKeyPair:
    """An Ed25519 signing key, serialisable to PEM."""

    private_pem: bytes
    public_pem: bytes
    fingerprint: str

    def sign(self, message: bytes) -> bytes:
        """Sign ``message`` with the private half."""
        return self._private_key().sign(message)

    def verify(self, message: bytes, signature: bytes) -> bool:
        """Check ``signature`` over ``message`` with the public half."""
        try:
            self._public_key().verify(signature, message)
        except InvalidSignature:
            return False
        return True

    def _private_key(self) -> Ed25519PrivateKey:
        key = serialization.load_pem_private_key(self.private_pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):  # pragma: no cover - type guard
            raise TypeError(f"expected an Ed25519 private key, got {type(key).__name__}")
        return key

    def _public_key(self) -> Ed25519PublicKey:
        key = serialization.load_pem_public_key(self.public_pem)
        if not isinstance(key, Ed25519PublicKey):  # pragma: no cover - type guard
            raise TypeError(f"expected an Ed25519 public key, got {type(key).__name__}")
        return key

    def save(self, directory: str | os.PathLike[str]) -> Path:
        """Write ``<directory>/signing_key.pem`` and ``signing_key.pub.pem``.

        The private key file is written 0600 via :func:`safe_write_bytes`.
        """
        from ..security.safeio import safe_write_bytes

        base = Path(directory)
        safe_write_bytes(base / "signing_key.pem", self.private_pem)
        safe_write_bytes(base / "signing_key.pub.pem", self.public_pem)
        return base / "signing_key.pem"


def generate_signing_key() -> SignKeyPair:
    """Generate a fresh Ed25519 keypair."""
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public_pem = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return SignKeyPair(
        private_pem=private_pem,
        public_pem=public_pem,
        fingerprint=sha3_256_hex(public_pem),
    )


def load_signing_key(path: str | os.PathLike[str]) -> SignKeyPair:
    """Load a private key PEM written by :meth:`SignKeyPair.save`.

    The public half is always re-derived from the private key rather than
    trusted from a neighbouring file, so a swapped ``.pub.pem`` cannot make the
    verifier accept signatures from an attacker.
    """
    private_pem = Path(path).read_bytes()
    if b"PUBLIC KEY" in private_pem:
        raise ValueError("expected a PRIVATE KEY pem, got a public key")
    if b"PRIVATE KEY" not in private_pem:
        raise ValueError("not a PEM private key: missing BEGIN PRIVATE KEY header")
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):  # pragma: no cover - type guard
        raise TypeError(f"expected an Ed25519 private key, got {type(private_key).__name__}")
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    return SignKeyPair(
        private_pem=private_pem,
        public_pem=public_pem,
        fingerprint=sha3_256_hex(public_pem),
    )


class ProvenanceChain:
    """An append-only, hash-linked, optionally signed record chain."""

    def __init__(
        self,
        chain_id: str = "anticloud",
        signer: SignKeyPair | None = None,
        time_fn: Callable[[], datetime] | None = None,
        nonce_fn: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(chain_id, str) or not chain_id:
            raise ValueError("chain_id must be a non-empty string")
        self.chain_id = chain_id
        self._signer = signer
        self._time_fn = time_fn or (lambda: datetime.now(timezone.utc))
        self._nonce_fn = nonce_fn or os.urandom
        self._records: list[ProvenanceRecord] = []
        self._head = GENESIS_DIGEST

    # ------------------------------------------------------------------ read
    @property
    def signer(self) -> SignKeyPair | None:
        return self._signer

    @property
    def head(self) -> str:
        """Digest of the most recent record, or the genesis digest if empty."""
        return self._head

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[ProvenanceRecord]:
        return iter(self._records)

    def __getitem__(self, index: int) -> ProvenanceRecord:
        return self._records[index]

    def records(self) -> list[ProvenanceRecord]:
        """Defensive copy of the record list."""
        return list(self._records)

    # ----------------------------------------------------------------- write
    def record(
        self,
        artifact: str,
        payload: bytes | None = None,
        artifact_hash: str | None = None,
        **extra: Any,
    ) -> ProvenanceRecord:
        """Append a record for ``artifact``.

        Supply either ``payload`` (hashed here) or a pre-computed
        ``artifact_hash``.  Returns the new record; ``chain.head`` advances.
        """
        if not isinstance(artifact, str) or not artifact:
            raise ValueError("artifact must be a non-empty string")
        if payload is None and artifact_hash is None:
            raise ValueError("supply either payload or artifact_hash")
        if payload is not None:
            digest_of_artifact = sha3_256_hex(payload)
        else:
            digest_of_artifact = str(artifact_hash)

        index = len(self._records)
        timestamp = self._time_fn().isoformat()
        nonce = self._nonce_fn(16).hex()
        body = {
            "index": index,
            "timestamp": timestamp,
            "artifact": artifact,
            "artifact_hash": digest_of_artifact,
            "parent": self._head,
            "nonce": nonce,
            "extra": extra,
        }
        digest = sha3_256_hex(_canonical(body))
        signature = self._signer.sign(bytes.fromhex(digest)).hex() if self._signer else None
        record = ProvenanceRecord(digest=digest, signature=signature, **body)
        self._records.append(record)
        self._head = digest
        return record

    def record_file(self, path: str | os.PathLike[str], **extra: Any) -> ProvenanceRecord:
        """Append a record for the contents of ``path``."""
        data = Path(path).read_bytes()
        return self.record(str(Path(path).name), payload=data, **extra)

    # ---------------------------------------------------------------- verify
    def verify(self) -> ChainVerification:
        """Walk the chain, naming the first record that breaks it.

        Checks, in order: index continuity, genesis parent, parent linkage,
        recomputed digest, and (if records are signed) signature validity.
        """
        expected_parent = GENESIS_DIGEST
        for position, record in enumerate(self._records):
            if record.index != position:
                return ChainVerification(
                    valid=False,
                    length=len(self._records),
                    head=self._head,
                    broken_at_index=position,
                    broken_file=record.artifact,
                    reason=(
                        f"index out of order: record at position {position} "
                        f"claims index {record.index}"
                    ),
                )
            if record.parent != expected_parent:
                return ChainVerification(
                    valid=False,
                    length=len(self._records),
                    head=self._head,
                    broken_at_index=position,
                    broken_file=record.artifact,
                    reason=(
                        f"broken link: parent {record.parent[:16]}... does not match "
                        f"preceding digest {expected_parent[:16]}..."
                    ),
                )
            if not _HEX64.match(record.artifact_hash or ""):
                return ChainVerification(
                    valid=False,
                    length=len(self._records),
                    head=self._head,
                    broken_at_index=position,
                    broken_file=record.artifact,
                    reason="artifact_hash is not a 64-character lowercase hex SHA3-256 digest",
                )
            recomputed = record.recompute()
            if recomputed != record.digest:
                return ChainVerification(
                    valid=False,
                    length=len(self._records),
                    head=self._head,
                    broken_at_index=position,
                    broken_file=record.artifact,
                    reason=(
                        f"digest mismatch: stored {record.digest[:16]}... but the "
                        f"record contents hash to {recomputed[:16]}..."
                    ),
                )
            expected_parent = record.digest

        signature_index = self.verify_signatures()
        return ChainVerification(
            valid=signature_index is None,
            length=len(self._records),
            head=self._head,
            signature_invalid_at_index=signature_index,
            reason=(
                None
                if signature_index is None
                else f"invalid Ed25519 signature at index {signature_index}"
            ),
        )

    def verify_signatures(self) -> int | None:
        """Return the index of the first bad signature, or None if all valid."""
        signed = [r for r in self._records if r.signature]
        if not signed:
            return None
        if self._signer is None:
            return signed[0].index
        for record in self._records:
            if not record.signature:
                continue
            if not self._signer.verify(record.signing_bytes(), bytes.fromhex(record.signature)):
                return record.index
        return None

    def assert_intact(self) -> None:
        """Raise :class:`ValueError` if the chain does not verify."""
        result = self.verify()
        if not result.valid:
            raise ValueError(
                f"provenance chain broken at index {result.broken_at_index} "
                f"({result.broken_file}): {result.reason}"
            )

    # ------------------------------------------------------------ (de)serial
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "chain_id": self.chain_id,
            "head": self._head,
            "records": [r.to_dict() for r in self._records],
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], signer: SignKeyPair | None = None
    ) -> "ProvenanceChain":
        """Rebuild a chain from :meth:`to_dict` output.

        The chain is *not* trusted on load: it is reconstructed field by field
        and then verified, so a tampered export fails on load rather than at
        some later point.
        """
        if not isinstance(data, dict):
            raise TypeError("chain data must be a dict")
        if "records" not in data:
            raise KeyError("chain data is missing 'records'")
        chain = cls(str(data.get("chain_id") or "anticloud"), signer=signer)
        raw_records = data["records"]
        if not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes)):
            raise TypeError("'records' must be a sequence")
        for raw in raw_records:
            chain._records.append(ProvenanceRecord.from_dict(raw))
        chain._head = chain._records[-1].digest if chain._records else GENESIS_DIGEST
        return chain

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Write the chain as JSON with restrictive permissions."""
        from ..security.safeio import safe_write_bytes

        return safe_write_bytes(Path(path), json.dumps(self.to_dict(), indent=2).encode("utf-8"))

    @classmethod
    def load(cls, path: str | os.PathLike[str], signer: SignKeyPair | None = None) -> "ProvenanceChain":
        """Load a chain from JSON."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")), signer=signer)

    def export_jws_like(self) -> list[dict[str, str]]:
        """Each record as a ``header.payload.signature`` triple (hex payloads).

        Provided so the chain can be inspected by tools that expect JWS-shaped
        objects; this is *not* a compliant JWS and is documented as such.
        """
        import base64

        out: list[dict[str, str]] = []
        for record in self._records:
            header = base64.urlsafe_b64encode(
                json.dumps({"alg": "Ed25519", "typ": "anticloud-record"}).encode()
            ).decode()
            payload = base64.urlsafe_b64encode(
                json.dumps(record.to_dict(), sort_keys=True, default=str).encode()
            ).decode()
            out.append(
                {"header": header, "payload": payload, "signature": record.signature or ""}
            )
        return out