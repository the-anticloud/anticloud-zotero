"""Input validation.

Every validator raises :class:`ValidationError` with a message naming the
offending field; nothing silently coerces or truncates.  The rules are
deliberately strict: this is a trust boundary, and a value that reaches the CRDT
or provenance layers should already have been checked.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

MAX_NODE_ID = 128
MAX_ELEMENT = 1024
MAX_PATH_BYTES = 4096

#: Conservative replica id: no whitespace, no separators, no control chars.
#: Keeping replica ids separator-free is what lets ORSet tags embed them.
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,%d}$" % MAX_NODE_ID)

_RESERVED_NODE_IDS = frozenset({"", ".", "..", "con", "nul", "prn", "aux"})

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ValidationError(ValueError):
    """Raised when a value fails validation."""


def validate_node_id(node_id: Any) -> str:
    """Validate and return a CRDT replica identifier."""
    if not isinstance(node_id, str):
        raise ValidationError(f"node_id must be a str, got {type(node_id).__name__}")
    if not node_id:
        raise ValidationError("node_id must not be empty")
    if len(node_id) > MAX_NODE_ID:
        raise ValidationError(f"node_id exceeds {MAX_NODE_ID} characters")
    if _CONTROL_CHARS.search(node_id):
        raise ValidationError("node_id contains control characters")
    if node_id != node_id.strip():
        raise ValidationError("node_id must not have leading or trailing whitespace")
    if not _NODE_ID_RE.match(node_id):
        raise ValidationError(f"node_id {node_id!r} must match {_NODE_ID_RE.pattern}")
    if node_id.lower() in _RESERVED_NODE_IDS:
        raise ValidationError(f"node_id {node_id!r} is reserved")
    return node_id


def validate_element(element: Any) -> str:
    """Validate and return an ORSet element."""
    if not isinstance(element, str):
        raise ValidationError(f"element must be a str, got {type(element).__name__}")
    if not element:
        raise ValidationError("element must not be empty")
    if len(element) > MAX_ELEMENT:
        raise ValidationError(f"element exceeds {MAX_ELEMENT} characters")
    if _CONTROL_CHARS.search(element):
        raise ValidationError("element contains control characters")
    if unicodedata.category(element[0]) in {"Cc", "Cs"}:
        raise ValidationError("element must not start with a control or surrogate character")
    return element


def validate_nonneg_int(value: Any, field: str = "value") -> int:
    """Validate a non-negative plain int (``bool`` is rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an int, got {type(value).__name__}")
    if value < 0:
        raise ValidationError(f"{field} must be >= 0, got {value}")
    return value


def validate_int(value: Any, field: str = "value") -> int:
    """Validate a plain signed int (``bool`` is rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an int, got {type(value).__name__}")
    return value


def validate_bool(value: Any, field: str = "flag") -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a bool, got {type(value).__name__}")
    return value


def validate_hex_digest(value: Any, field: str = "digest", *, length: int | None = 64) -> str:
    """Validate a lowercase hex digest."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a str, got {type(value).__name__}")
    candidate = value.lower()
    if length is not None and len(candidate) != length:
        raise ValidationError(f"{field} must be {length} hex characters, got {len(candidate)}")
    if candidate and not re.fullmatch(r"[0-9a-f]+", candidate):
        raise ValidationError(f"{field} must be lowercase hex, got {value!r}")
    return candidate


def validate_path(path: Any, *, must_exist: bool = False, allow_absolute: bool = True) -> Path:
    """Validate a filesystem path and return it.

    NUL bytes and empty strings are rejected outright; Windows reserved device
    names are rejected because they silently redirect writes on some APIs.
    """
    if isinstance(path, Path):
        raw = str(path)
    elif isinstance(path, str):
        raw = path
    else:
        raise ValidationError(f"path must be a str or Path, got {type(path).__name__}")
    if not raw:
        raise ValidationError("path must not be empty")
    if "\x00" in raw:
        raise ValidationError("path contains a NUL byte")
    if len(raw.encode("utf-8")) > MAX_PATH_BYTES:
        raise ValidationError(f"path exceeds {MAX_PATH_BYTES} bytes")

    stem = os.path.basename(raw.replace("\\", "/")).split(".")[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved |= {f"COM{i}" for i in range(1, 10)}
    reserved |= {f"LPT{i}" for i in range(1, 10)}
    if stem in reserved:
        raise ValidationError(f"path uses reserved device name {stem!r}")

    candidate = Path(raw)
    if not allow_absolute and candidate.is_absolute():
        raise ValidationError(f"path must be relative, got {raw!r}")
    if must_exist and not candidate.exists():
        raise ValidationError(f"path does not exist: {raw}")
    return candidate


def validate_text(value: Any, field: str = "text", *, max_length: int = 1_000_000) -> str:
    """Validate a text field, rejecting NUL bytes."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a str, got {type(value).__name__}")
    if len(value) > max_length:
        raise ValidationError(f"{field} exceeds {max_length} characters")
    if "\x00" in value:
        raise ValidationError(f"{field} contains a NUL byte")
    return value


def validate_iterable(value: Any, field: str = "items") -> list[Any]:
    """Materialise an iterable to a list, rejecting strings and non-iterables."""
    if isinstance(value, (str, bytes)):
        raise ValidationError(f"{field} must be an iterable of items, not a string")
    if not isinstance(value, Iterable):
        raise ValidationError(f"{field} must be iterable, got {type(value).__name__}")
    return list(value)


def validate_choices(value: Any, choices: Iterable[str], field: str = "value") -> str:
    """Validate that ``value`` is one of ``choices``."""
    allowed = tuple(choices)
    if value not in allowed:
        raise ValidationError(f"{field} must be one of {allowed}, got {value!r}")
    return value


def validate_port(value: Any, field: str = "port") -> int:
    """Validate a TCP/UDP port number."""
    port = validate_int(value, field)
    if not 1 <= port <= 65535:
        raise ValidationError(f"{field} must be in 1..65535, got {port}")
    return port
