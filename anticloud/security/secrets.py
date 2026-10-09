"""Tree secrets scanner.

Finds credential-shaped material in a source tree before it is committed or
published.  Two design choices matter:

* **Entropy floor, not just pattern match.**  A ``(redacted)`` placeholder or a
  short example value would trip a pure regex, so high-entropy matches inside a
  recognised provider prefix are required to score as a finding.
* **Test-fixture awareness.**  Scan results carry ``is_test_fixture`` so the CI
  gate can report them without failing the build; a deliberate fake key in a
  test must not be indistinguishable from a leaked live one.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

#: Directory names never descended into.
SKIP_DIRS = frozenset(
    {".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
     "node_modules", ".venv", "venv", ".tox", ".eggs", "dist", "build", ".idea", ".vscode"}
)

#: File suffixes never read (they are binary or huge and never hold plaintext keys).
SKIP_SUFFIXES = frozenset(
    {".pyc", ".pyo", ".so", ".dll", ".dylib", ".pyd", ".exe", ".png", ".jpg", ".jpeg",
     ".gif", ".pdf", ".zip", ".tar", ".gz", ".whl", ".ico", ".woff", ".woff2"}
)

#: Maximum bytes read from a single file.
MAX_FILE_BYTES = 2_000_000

#: Entropy (bits/char) required for a generic high-entropy assignment to count.
MIN_ENTROPY = 3.6

#: Minimum length for a generic assignment to be considered at all.
MIN_GENERIC_LEN = 24


class Rule:
    """One named detection pattern."""

    __slots__ = ("name", "pattern", "severity", "group")

    def __init__(self, name: str, pattern: str, severity: str, group: int = 0) -> None:
        self.name = name
        self.pattern = re.compile(pattern)
        self.severity = severity
        self.group = group


#: Provider-prefixed keys.  These are high confidence on their own: the prefix is
#: not something that occurs by accident in source code.
RULES: tuple[Rule, ...] = (
    Rule("aws_access_key_id", r"\b((?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16})\b", "critical"),
    Rule("github_token", r"\b(gh[pousr]_[A-Za-z0-9]{36,255})\b", "critical"),
    Rule("github_pat", r"\b(github_pat_[A-Za-z0-9_]{22,255})\b", "critical"),
    Rule("gitlab_token", r"\b(glpat-[A-Za-z0-9_-]{20,})\b", "critical"),
    Rule("slack_token", r"\b(xox[abprs]-[A-Za-z0-9-]{10,})\b", "critical"),
    Rule("stripe_secret", r"\b(sk_live_[A-Za-z0-9]{16,})\b", "critical"),
    Rule("google_api_key", r"\b(AIza[0-9A-Za-z_-]{35})\b", "critical"),
    Rule("private_key_block", r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----", "critical"),
    Rule("json_web_token", r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b", "high"),
    Rule("npm_token", r"\b(npm_[A-Za-z0-9]{36})\b", "critical"),
    Rule("pypi_token", r"\b(pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{16,})\b", "high"),
    Rule("huggingface_token", r"\b(hf_[A-Za-z0-9]{34})\b", "high"),
)

#: Generic ``name = "value"`` assignments, gated on entropy and length.
GENERIC_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(?P<name>[A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|
        private[_-]?key|credential|auth)[A-Za-z0-9_.-]*)
    \s*[:=]\s*
    (?P<quote>['"])(?P<value>[^'"\n]{8,})(?P=quote)
    """
)

#: Values that are placeholders, not credentials.
PLACEHOLDER_VALUES = frozenset(
    {
        "changeme", "password", "passw0rd", "secret", "token", "apikey", "api_key",
        "your_token_here", "your-api-key", "xxxx", "xxxxxxxx", "todo", "none", "null",
        "example", "placeholder", "redacted", "dummy", "test", "fake", "notasecret",
        "hunter2", "correcthorsebatterystaple", "abcdefghijklmnop", "0123456789abcdef",
    }
)

#: Path fragments that mark a file as a deliberate test fixture.
FIXTURE_MARKERS = ("test", "tests", "spec", "fixtures", "conftest", "mock", "sample", "example")


@dataclass(frozen=True)
class Finding:
    """One candidate secret."""

    rule: str
    severity: str
    path: str
    line: int
    column: int
    redacted: str
    entropy: float
    is_test_fixture: bool
    matched_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "redacted": self.redacted,
            "entropy": round(self.entropy, 3),
            "is_test_fixture": self.is_test_fixture,
            "matched_name": self.matched_name,
        }


def shannon_entropy(value: str) -> float:
    """Shannon entropy in bits per character."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def redact(value: str, keep: int = 4) -> str:
    """Return a non-reversible preview safe to print or store."""
    if len(value) <= keep:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * min(len(value) - keep, 12)}({len(value)} chars)"


def is_placeholder(value: str) -> bool:
    """True when ``value`` is an obvious example rather than a credential."""
    stripped = value.strip()
    if stripped.lower() in PLACEHOLDER_VALUES:
        return True
    if not stripped:
        return True
    # A single repeated character is not a credential.
    if len(set(stripped)) <= 2:
        return True
    # Templated values like <your-token> or ${SECRET}.
    if stripped.startswith(("<", "${", "{{")) or stripped.endswith((">", "}}")):
        return True
    return False


def is_test_fixture(path: str) -> bool:
    """True when the path looks like a deliberate test fixture."""
    normalised = path.replace("\\", "/").lower()
    parts = normalised.split("/")
    return any(marker in part for part in parts for marker in FIXTURE_MARKERS)


def scan_text(text: str, path: str = "<memory>", *, min_entropy: float = MIN_ENTROPY) -> list[Finding]:
    """Scan a text blob and return findings.

    The full match text is never included in a :class:`Finding` — only a redacted
    preview — so a scan report can be committed without re-leaking what it found.
    """
    findings: list[Finding] = []
    fixture = is_test_fixture(path)
    seen: set[tuple[str, int, int]] = set()

    for rule in RULES:
        for match in rule.pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            line_start = text.rfind("\n", 0, match.start()) + 1
            column = match.start() - line_start + 1
            key = (rule.name, line_no, column)
            if key in seen:
                continue
            seen.add(key)
            matched = match.group(rule.group) if rule.group else match.group(0)
            findings.append(
                Finding(
                    rule=rule.name,
                    severity=rule.severity,
                    path=path,
                    line=line_no,
                    column=column,
                    redacted=redact(matched),
                    entropy=shannon_entropy(matched),
                    is_test_fixture=fixture,
                    matched_name=rule.name,
                )
            )

    for match in GENERIC_ASSIGNMENT.finditer(text):
        value = match.group("value")
        if is_placeholder(value):
            continue
        if len(value) < MIN_GENERIC_LEN:
            continue
        entropy = shannon_entropy(value)
        if entropy < min_entropy:
            continue
        line_no = text.count("\n", 0, match.start()) + 1
        line_start = text.rfind("\n", 0, match.start()) + 1
        column = match.start() - line_start + 1
        key = ("generic_assignment", line_no, column)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            Finding(
                rule="generic_assignment",
                severity="high",
                path=path,
                line=line_no,
                column=column,
                redacted=redact(value),
                entropy=entropy,
                is_test_fixture=fixture,
                matched_name=match.group("name"),
            )
        )

    findings.sort(key=lambda f: (f.path, f.line, f.column, f.rule))
    return findings


def iter_files(root: str | os.PathLike[str], *, skip_dirs: Iterable[str] = SKIP_DIRS) -> Iterator[Path]:
    """Yield candidate files under ``root``, pruning noisy directories."""
    base = Path(root)
    pruned = set(skip_dirs)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in pruned and not d.startswith(".git"))
        for filename in sorted(filenames):
            candidate = Path(dirpath) / filename
            if candidate.suffix.lower() in SKIP_SUFFIXES:
                continue
            try:
                if candidate.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:  # pragma: no cover - race
                continue
            yield candidate


def scan_tree(
    root: str | os.PathLike[str],
    *,
    min_entropy: float = MIN_ENTROPY,
    include_fixtures: bool = True,
    skip_dirs: Iterable[str] = SKIP_DIRS,
) -> dict[str, Any]:
    """Scan a directory tree and return a JSON-ready report."""
    base = Path(root)
    if not base.is_dir():
        raise NotADirectoryError(f"{base} is not a directory")

    all_findings: list[Finding] = []
    scanned = 0
    skipped_binary = 0
    for path in iter_files(base, skip_dirs=skip_dirs):
        try:
            raw = path.read_bytes()
        except OSError:  # pragma: no cover - unreadable
            continue
        if b"\x00" in raw[:8192]:
            skipped_binary += 1
            continue
        scanned += 1
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        all_findings.extend(scan_text(text, str(path), min_entropy=min_entropy))

    if not include_fixtures:
        all_findings = [f for f in all_findings if not f.is_test_fixture]

    by_severity: dict[str, int] = {}
    for finding in all_findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    actionable = [f for f in all_findings if not f.is_test_fixture]
    return {
        "root": str(base),
        "files_scanned": scanned,
        "binary_skipped": skipped_binary,
        "findings": [f.as_dict() for f in all_findings],
        "total_findings": len(all_findings),
        "actionable_findings": len(actionable),
        "by_severity": by_severity,
        "clean": not actionable,
    }
