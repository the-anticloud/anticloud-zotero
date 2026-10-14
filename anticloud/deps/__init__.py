"""Dependency pinning: hash-pinned lock files and their verification."""

from anticloud_ref.deps.lock import (
    DependencyError,
    Requirement,
    canonicalise,
    diff_locks,
    generate_lock,
    iter_requirements,
    load_lock,
    parse_lock,
    parse_requirement,
    sha256_bytes,
    sha256_file,
    verify_file,
    verify_lock,
)

__all__ = [
    "DependencyError",
    "Requirement",
    "canonicalise",
    "diff_locks",
    "generate_lock",
    "iter_requirements",
    "load_lock",
    "parse_lock",
    "parse_requirement",
    "sha256_bytes",
    "sha256_file",
    "verify_file",
    "verify_lock",
]
