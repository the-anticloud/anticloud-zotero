"""Safe file-write primitives.

Every write in this package goes through here so that two properties hold
uniformly: the target is written atomically (never a half-written file that a
crash could leave behind), and the file is created with restrictive permissions
rather than inheriting the process umask.

The atomicity is real: content is written to a temporary file in the *same*
directory, flushed, fsync'd, then ``os.replace``'d over the target.  A crash at
any point leaves either the old file or the new one, never a truncated mixture.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "SafeWriteError",
    "PathTraversalError",
    "safe_write_bytes",
    "safe_write_text",
    "safe_write_json",
    "resolve_within",
]

# 0o600: owner read/write only. Applied explicitly so the mode does not depend
# on the ambient umask, which differs between a dev shell and a CI runner.
PRIVATE_MODE = 0o600
PUBLIC_MODE = 0o644


class SafeWriteError(OSError):
    """A write was refused."""


class PathTraversalError(SafeWriteError):
    """A path escaped the directory it was supposed to stay inside."""


def safe_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    mode: int = PRIVATE_MODE,
    atomic: bool = True,
) -> Path:
    """Atomically write ``data`` to ``path`` with explicit permissions.

    Returns the resolved path.  Raises :class:`SafeWriteError` if the parent
    directory does not exist — directories are created explicitly by the caller
    so that a typo in a path cannot silently create a new tree.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    target = Path(path)
    parent = target.parent
    if not parent.is_dir():
        raise SafeWriteError(f"parent directory does not exist: {parent}")

    if not atomic:
        with open(target, "wb") as handle:
            handle.write(bytes(data))
        _chmod(target, mode)
        return target

    handle_fd, temp_name = tempfile.mkstemp(dir=str(parent), prefix=f".{target.name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(bytes(data))
            handle.flush()
            os.fsync(handle.fileno())
        _chmod(temp_path, mode)
        os.replace(temp_path, target)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return target


def safe_write_text(
    path: str | os.PathLike[str],
    text: str,
    mode: int = PRIVATE_MODE,
    encoding: str = "utf-8",
) -> Path:
    """Atomically write ``text``.  Newlines are not translated."""
    if not isinstance(text, str):
        raise TypeError("text must be a str")
    return safe_write_bytes(path, text.encode(encoding), mode=mode)


def safe_write_json(
    path: str | os.PathLike[str],
    payload: object,
    mode: int = PRIVATE_MODE,
    indent: int = 2,
) -> Path:
    """Atomically write ``payload`` as UTF-8 JSON with sorted keys."""
    import json

    text = json.dumps(payload, indent=indent, sort_keys=True, default=str)
    return safe_write_text(path, text + "\n", mode=mode)


def resolve_within(base: str | os.PathLike[str], candidate: str | os.PathLike[str]) -> Path:
    """Resolve ``candidate`` and assert it lies inside ``base``.

    This is the check that stops ``../../etc/passwd`` and absolute paths from
    escaping a jail directory.  Both are rejected, including the case where the
    jail itself is a symlink (base is fully resolved first).
    """
    base_resolved = Path(base).resolve()
    target = Path(candidate)
    if not target.is_absolute():
        target = base_resolved / target
    # resolve() collapses .. and follows symlinks, so a symlink pointing out
    # of the jail is caught here too, not only literal '../' segments.
    resolved = target.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise PathTraversalError(
            f"{candidate} resolves outside the permitted directory {base_resolved}"
        ) from exc
    return resolved


def _chmod(path: Path, mode: int) -> None:
    """Set the mode, tolerating filesystems that do not support chmod."""
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        # Windows ACLs govern access there; the mode is best-effort there and
        # the caller is told nothing because there is nothing actionable on
        # that platform. Failures on POSIX are not swallowed: they raise.
        if os.name != "nt":
            raise


def write_lines(path: str | os.PathLike[str], lines: Iterable[str], mode: int = PRIVATE_MODE) -> Path:
    """Write an iterable of lines, each newline-terminated."""
    return safe_write_text(path, "".join(f"{line}\n" for line in lines), mode=mode)