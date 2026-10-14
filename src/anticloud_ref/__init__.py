"""Anticloud Reference — the single working exemplar of the Anticloud technical capability.

Six capabilities, no cloud dependency and no third-party signing authority:

* :mod:`anticloud_ref.crdt` — GCounter, PNCounter, ORSet and LWW-Register with
  convergence checked by an executable property suite, not asserted in prose.
* :mod:`anticloud_ref.provenance` — an append-only SHA3-256 hash chain with
  optional Ed25519 signatures, where ``verify()`` names the first record that
  breaks the chain instead of returning a bare ``False``.
* :mod:`anticloud_ref.licence` — an A/B/C licence classifier that fails closed:
  the default and the fallback are both C, and only a positively identified
  permissive licence reaches A.
* :mod:`anticloud_ref.security` — input validators, a tree secrets scanner that
  redacts what it finds, safe file writes and a scrypt + AES-256-GCM vault.
* :mod:`anticloud_ref.deps` — hash-pinned ``requirements.lock`` generation and
  verification.
* :mod:`anticloud_ref.perf` — cold-import, cold-start, memory-ceiling and
  hot-path measurements emitted as one machine-readable JSON document.

The package imports nothing from the ML ecosystem.  Its only third-party
dependency is ``cryptography``, for AES-GCM, scrypt and Ed25519.
"""

from anticloud_ref._version import __version__, version_tuple
from anticloud_ref.crdt import (
    GCounter,
    HybridLogicalClock,
    LWWRegister,
    ORSet,
    PNCounter,
    convergence_report,
)
from anticloud_ref.deps import generate_lock, parse_lock, verify_lock
from anticloud_ref.licence import (
    LicenseClass,
    LicenseVerdict,
    classify_file,
    classify_name,
    classify_text,
    scan_tree as scan_licence_tree,
)
from anticloud_ref.perf import run_full_report
from anticloud_ref.provenance import (
    ProvenanceChain,
    ProvenanceRecord,
    generate_signing_key,
)
from anticloud_ref.security import (
    SecretVault,
    scan_tree as scan_secrets_tree,
    validate_node_id,
)

__all__ = [
    "GCounter",
    "HybridLogicalClock",
    "LWWRegister",
    "LicenseClass",
    "LicenseVerdict",
    "ORSet",
    "PNCounter",
    "ProvenanceChain",
    "ProvenanceRecord",
    "SecretVault",
    "__version__",
    "classify_file",
    "classify_name",
    "classify_text",
    "convergence_report",
    "generate_lock",
    "generate_signing_key",
    "parse_lock",
    "run_full_report",
    "scan_licence_tree",
    "scan_secrets_tree",
    "validate_node_id",
    "verify_lock",
    "version_tuple",
]
