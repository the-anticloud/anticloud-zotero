"""Hash-pinned ``requirements.lock`` generation and verification.

A lock file is only trustworthy if every entry is pinned to an exact version
*and* an artifact hash, and if the generator and the verifier share one
definition of "acceptable line".  Both live here so a lock that this module
produces is by construction a lock this module accepts.

Supported formats:

* ``--hash=sha256:<64 hex>`` lines (pip's own multi-hash form), and
* a bare ``name==version`` line (accepted by the parser, but rejected by
  :func:`verify_lock` — an unhashed pin is not a lock).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

#: ``name[extras]==version`` with an optional environment marker.  Extras sit
#: between the name and the version per PEP 508, not after the version.
_REQUIREMENT_RE = re.compile(
    r"""^\s*
    (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)
    (?P<extras>\[[^\]]*\])?
    \s*==\s*
    (?P<version>[A-Za-z0-9][A-Za-z0-9.*+!_-]*)
    \s*
    (?P<marker>;[^#]*)?
    $""",
    re.VERBOSE,
)

#: pip's ``--hash=sha256:<hex>`` suffix.
_HASH_RE = re.compile(r"--hash=sha256:(?P<digest>[0-9a-fA-F]{64})")

#: Normalisation of a distribution name per PEP 503.
_CANONICALISE_RE = re.compile(r"[-_.]+")

SHA256_HEX_LENGTH = 64


class DependencyError(ValueError):
    """Raised when a requirement or lock line is malformed."""


def canonicalise(name: str) -> str:
    """PEP 503 name normalisation: runs of ``-_.`` collapse to ``-``."""
    return _CANONICALISE_RE.sub("-", name).lower()


@dataclass(frozen=True)
class Requirement:
    """One parsed requirement line."""

    name: str
    version: str
    extras: tuple[str, ...] = ()
    marker: str = ""
    hashes: tuple[str, ...] = field(default_factory=tuple)
    raw: str = ""

    @property
    def canonical_name(self) -> str:
        return canonicalise(self.name)

    @property
    def pinned(self) -> bool:
        return "==" in self.raw or bool(self.version)

    @property
    def hashed(self) -> bool:
        return bool(self.hashes)

    def to_lock_line(self) -> str:
        """Render as a single-line pip hash-pinned requirement."""
        extras = f"[{','.join(self.extras)}]" if self.extras else ""
        base = f"{self.name}{extras}=={self.version}"
        if self.marker:
            base = f"{base} {self.marker}"
        for digest in self.hashes:
            base += f" \\\n        --hash=sha256:{digest}"
        return base

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "canonical_name": self.canonical_name,
            "version": self.version,
            "extras": list(self.extras),
            "marker": self.marker,
            "hashes": list(self.hashes),
            "hashed": self.hashed,
        }


def parse_requirement(line: str, *, continuation: str = "") -> Requirement:
    """Parse one requirement, returning ``continuation`` as extra hash text.

    pip wraps a hashed requirement across lines with a trailing ``\\``.  The
    caller passes the already-joined continuation so this stays a pure function.
    """
    if not isinstance(line, str):
        raise DependencyError(f"requirement must be a str, got {type(line).__name__}")
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        raise DependencyError(f"not a requirement: {line!r}")

    joined = f"{stripped} {continuation}".strip() if continuation else stripped
    hashes = tuple(m.group("digest").lower() for m in _HASH_RE.finditer(joined))
    # Strip the hash suffixes, the line-continuation backslashes and any trailing
    # comment before matching the core pattern.  The backslashes must go: pip's
    # wrapped form leaves them behind, and they stop the core pattern matching.
    core = _HASH_RE.sub("", joined)
    core = core.replace("\\", " ").split("#", 1)[0].strip()
    core = re.sub(r"\s+", " ", core).strip()

    match = _REQUIREMENT_RE.match(core)
    if not match:
        raise DependencyError(f"cannot parse requirement: {line!r}")

    extras_raw = (match.group("extras") or "").strip("[]")
    extras = tuple(e.strip() for e in extras_raw.split(",") if e.strip()) if extras_raw else ()
    marker = (match.group("marker") or "").strip()

    if not hashes:
        for digest in re.findall(r"[0-9a-fA-F]{64}", joined):
            if digest.lower() not in hashes:
                hashes = hashes + (digest.lower(),)

    return Requirement(
        name=match.group("name"),
        version=match.group("version"),
        extras=extras,
        marker=marker,
        hashes=hashes,
        raw=stripped,
    )


def sha256_file(path: str | Path, *, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA-256 of a file, lowercase hex."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_lock(text: str) -> list[Requirement]:
    """Parse a whole lock file into requirements.

    Continuation lines (ending in ``\\``) are folded into the requirement they
    belong to, so multi-hash entries are read as one logical requirement.
    """
    if not isinstance(text, str):
        raise DependencyError(f"lock text must be a str, got {type(text).__name__}")

    requirements: list[Requirement] = []
    pending = ""
    continuation = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if pending:
            # A continuation line is either another --hash= fragment or the final
            # body of the requirement.  Treat an explicit hash fragment as more
            # continuation and anything else as the requirement's own tail.
            if _HASH_RE.search(line):
                continuation = f"{continuation} {line}".strip()
                if line.rstrip().endswith("\\"):
                    continue
                full = pending
                pending = ""
            else:
                full = f"{pending} {line}".strip()
                pending = ""
        elif line.rstrip().endswith("\\"):
            pending = line.rstrip()[:-1].rstrip()
            continue
        else:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            full = line
        requirements.append(parse_requirement(full, continuation=continuation))
        continuation = ""
    if pending:
        requirements.append(parse_requirement(pending, continuation=continuation))
    return requirements


def generate_lock(
    packages: Sequence[tuple[str, str, str]] | Sequence[Requirement],
    *,
    header: str | None = None,
    include_empty_hashes_as_comments: bool = False,
) -> str:
    """Render a hash-pinned lock file.

    ``packages`` may be ``(name, version, sha256)`` triples or
    :class:`Requirement` objects.  A triple with an empty or malformed digest is
    a hard error: a lock that silently drops a hash is worse than no lock,
    because it looks pinned.
    """
    lines: list[str] = []
    if header:
        for header_line in header.splitlines():
            lines.append(f"# {header_line}")
    lines.append("#")
    lines.append("# Hash-pinned lock file. Every entry is pinned to an exact version and")
    lines.append("# at least one sha256 artifact hash. Verify with: anticloud-ref deps verify")
    lines.append("")

    for entry in packages:
        if isinstance(entry, Requirement):
            requirement = entry
        else:
            name, version, digest = entry
            if not digest:
                raise DependencyError(f"{name}=={version} has no sha256 hash; refusing to emit an unpinned entry")
            normalised = digest.lower()
            if len(normalised) != SHA256_HEX_LENGTH or not re.fullmatch(r"[0-9a-f]{64}", normalised):
                raise DependencyError(f"{name}=={version} has malformed sha256: {digest!r}")
            requirement = Requirement(name=name, version=version, hashes=(normalised,), raw=f"{name}=={version}")

        rendered = requirement.to_lock_line()
        if include_empty_hashes_as_comments and not requirement.hashed:
            rendered = f"# UNHASHED: {requirement.name}=={requirement.version}"
        lines.append(rendered)

    lines.append("")
    return "\n".join(lines)


def verify_lock(text: str, *, require_hashes: bool = True) -> dict[str, Any]:
    """Verify a lock file, reporting every problem found.

    Checks: every line parses, every requirement is pinned with ``==`` (no
    ranges, no URLs, no ``latest``), and — unless waived — every requirement
    carries at least one well-formed sha256.
    """
    problems: list[str] = []
    try:
        requirements = parse_lock(text)
    except DependencyError as exc:
        return {
            "ok": False,
            "total": 0,
            "pinned": 0,
            "hashed": 0,
            "problems": [str(exc)],
            "requirements": [],
        }

    pinned = 0
    hashed = 0
    for requirement in requirements:
        if "==" not in requirement.raw and not requirement.version:
            problems.append(f"{requirement.name}: not pinned to an exact version")
            continue
        pinned += 1
        if ">" in requirement.raw or "<" in requirement.raw or "@" in requirement.raw:
            problems.append(f"{requirement.name}: range or URL pin is not allowed in a lock")
        if requirement.version in {"latest", "head", "master"}:
            problems.append(f"{requirement.name}: floating version {requirement.version!r}")
        if require_hashes:
            if not requirement.hashes:
                problems.append(f"{requirement.name}=={requirement.version}: no sha256 hash")
            else:
                hashed += 1
                for digest in requirement.hashes:
                    if len(digest) != SHA256_HEX_LENGTH or not re.fullmatch(r"[0-9a-f]{64}", digest):
                        problems.append(f"{requirement.name}: malformed sha256 {digest!r}")

    duplicates: dict[str, int] = {}
    for requirement in requirements:
        key = requirement.canonical_name
        duplicates[key] = duplicates.get(key, 0) + 1
    for name, count in sorted(duplicates.items()):
        if count > 1:
            problems.append(f"{name}: listed {count} times; a lock must list each distribution once")

    return {
        "ok": not problems,
        "total": len(requirements),
        "pinned": pinned,
        "hashed": hashed,
        "problems": problems,
        "requirements": [r.as_dict() for r in requirements],
    }


def diff_locks(old_text: str, new_text: str) -> dict[str, Any]:
    """Compare two locks by canonical name → version and hash set."""
    old = {r.canonical_name: r for r in parse_lock(old_text)}
    new = {r.canonical_name: r for r in parse_lock(new_text)}

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(
        name for name in set(old) & set(new)
        if old[name].version != new[name].version or set(old[name].hashes) != set(new[name].hashes)
    )
    unchanged = sorted(set(old) & set(new)) and sorted(
        name for name in set(old) & set(new) if name not in changed
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": [n for n in unchanged] if unchanged else [],
        "total_before": len(old),
        "total_after": len(new),
    }


def load_lock(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def verify_file(path: str | Path, *, require_hashes: bool = True) -> dict[str, Any]:
    """Verify a lock file on disk."""
    target = Path(path)
    if not target.is_file():
        return {
            "ok": False,
            "total": 0,
            "pinned": 0,
            "hashed": 0,
            "problems": [f"lock file not found: {target}"],
            "requirements": [],
        }
    report = verify_lock(target.read_text(encoding="utf-8"), require_hashes=require_hashes)
    report["path"] = str(target)
    return report


def iter_requirements(requirements: Iterable[Requirement]) -> list[str]:
    """Sorted ``name==version`` strings, for reporting."""
    return sorted(f"{r.canonical_name}=={r.version}" for r in requirements)
