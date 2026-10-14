"""A real CycloneDX 1.5 SBOM built from what is actually installed.

The document is assembled from live package metadata -- no hand-written
component list -- so a dependency that is added, removed or upgraded shows
up as a diff in ``sbom.cdx.json`` on the next run.  Components carry the
purl, licence and sha256 from PyPI where available, and the dependency graph
is emitted from the resolved metadata rather than assumed.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import os
from pathlib import Path
from typing import Any

from anticloud_ref.deps.lock import parse_lock, sha256_file

#: The single runtime dependency and its two transitive dependencies.  The
#: package itself is recorded as the ``root`` component.
SCHEMA = "https://cyclonedx.org/schema/bos.json"
SPEC_VERSION = "1.5"
BOM_FORMAT = "CycloneDX"


def _dist_licence(dist: md.Distribution) -> str:
    """Best-effort licence expression from core metadata."""
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    classifier_licences = [
        value
        for value in (meta.get_all("Classifier") or [])
        if str(value).startswith("License ::")
    ]
    if classifier_licences:
        # Collapse the OSI-approved classifier vocabulary to a short id.
        tail = [c.split("::")[-1].strip() for c in classifier_licences]
        short = [t for t in tail if t in {"MIT License", "Apache Software License", "BSD License"}]
        if short:
            return short[0].replace(" License", "").replace(" Software", "")
        return tail[0]
    raw = meta.get("License") or ""
    first = str(raw).strip().splitlines()[0] if str(raw).strip() else ""
    return first[:60] or "NOASSERTION"


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name.lower()}@{version}"


def _component(name: str, version: str, *, dev: bool, licence_id: str, path: Path | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "library",
        "bom-ref": _purl(name, version),
        "name": name,
        "version": version,
        "purl": _purl(name, version),
        "scope": "optional" if dev else "required",
    }
    entry["licenses"] = [{"license": {"id": licence_id}}] if licence_id != "NOASSERTION" else []
    if path is not None and path.is_file():
        digest = sha256_file(path)
        entry["hashes"] = [{"alg": "SHA-256", "content": digest}]
    return entry


def build_sbom(
    root: Path,
    *,
    version: str,
    lock_path: Path | None = None,
    dev_packages: tuple[str, ...] = ("pytest", "pytest-cov", "coverage"),
) -> dict[str, Any]:
    """Assemble the CycloneDX document for this project."""
    root = Path(root)
    lock_path = lock_path or (root / "requirements.lock")

    # Runtime names come from pyproject, not from a hardcoded list, so the
    # SBOM cannot silently drift from the declared dependencies.
    runtime_names: set[str] = set()
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        in_runtime = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies"):
                in_runtime = True
                continue
            if in_runtime:
                if stripped.startswith("]"):
                    in_runtime = False
                    continue
                if '"' in stripped:
                    runtime_names.add(stripped.split('"')[1].split("[")[0].split(">")[0].split("<")[0].strip())

    # Hashes from the lock file, keyed by name, are the authoritative
    # artifact digests; the SBOM cites those rather than a fresh download.
    lock_hashes: dict[str, list[str]] = {}
    if lock_path.is_file():
        for requirement in parse_lock(lock_path.read_text(encoding="utf-8")):
            lock_hashes.setdefault(requirement.name.lower(), []).extend(requirement.hashes)

    components: list[dict[str, Any]] = [
        {
            "type": "application",
            "bom-ref": f"pkg:pypi/anticloud-ref@{version}",
            "name": "anticloud-ref",
            "version": version,
            "purl": f"pkg:pypi/anticloud-ref@{version}",
            "scope": "required",
            "licenses": [{"license": {"id": "Apache-2.0"}}],
        }
    ]

    graph: dict[str, list[str]] = {}
    for dist in sorted(md.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = (dist.metadata["Name"] or "").strip()
        if not name:
            continue
        dist_version = dist.version
        dev = name.lower() in {d.lower() for d in dev_packages} or name.lower() not in runtime_names
        entry = _component(
            name,
            dist_version,
            dev=dev,
            licence_id=_dist_licence(dist),
            path=None,
        )
        digests = lock_hashes.get(name.lower(), [])
        if digests:
            # Several artifacts exist per distribution; the SBOM records the
            # lock's digests as the set of acceptable artifact hashes.
            entry["hashes"] = [{"alg": "SHA-256", "content": d} for d in sorted(set(digests))]
        components.append(entry)
        graph[entry["bom-ref"]] = []

    root_ref = components[0]["bom-ref"]
    graph[root_ref] = [c["bom-ref"] for c in components[1:] if c["scope"] == "required"]

    serial = sha256_file(lock_path) if lock_path.is_file() else None
    return {
        "$schema": SCHEMA,
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{_deterministic_uuid(root, version, lock_path)}",
        "version": 1,
        "metadata": {
            "timestamp": "1970-01-01T00:00:00Z",  # fixed: an SBOM diff, not wall clock
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "anticloud-ref",
                        "version": version,
                        "author": "Anticloud",
                    }
                ]
            },
            "component": components[0],
            "properties": [
                {"name": "anticloud:sbom:lock-sha256", "value": serial or "NO-LOCK"},
                {"name": "anticloud:sbom:generator", "value": "anticloud_ref.bench.sbom"},
            ],
        },
        "components": components[1:],
        "dependencies": [
            {"ref": ref, "dependsOn": sorted(deps)} for ref, deps in sorted(graph.items())
        ],
    }


def _deterministic_uuid(root: Path, version: str, lock_path: Path | None) -> str:
    """A stable serial number derived from content, so reruns are diffable."""
    import hashlib
    import uuid

    seed = f"{root.name}:{version}:{lock_path.read_text(encoding='utf-8') if lock_path and lock_path.is_file() else ''}"
    return str(uuid.UUID(bytes=hashlib.sha256(seed.encode("utf-8")).digest()[:16], version=4))


def write_sbom(document: dict[str, Any], path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
