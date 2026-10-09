"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow running the suite from a source checkout without installing.
SRC = Path(__file__).resolve().parent.parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def tmp_json(tmp_path: Path) -> Path:
    """A path for a JSON artefact inside a temporary directory."""
    return tmp_path / "artifact.json"


@pytest.fixture()
def fixed_wall_clock():
    """A deterministic wall clock returning a constant epoch seconds value."""
    return lambda: 1767225600.0  # 2026-01-01T00:00:00Z


@pytest.fixture()
def signing_key():
    """A freshly generated Ed25519 signing keypair."""
    from anticloud_ref.provenance import generate_signing_key

    return generate_signing_key()
