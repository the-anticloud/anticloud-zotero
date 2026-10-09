"""Single source of truth for the package version.

Kept in its own module so ``pyproject.toml`` and the runtime agree without
either one parsing the other.
"""

__version__ = "1.0.0"

#: Parsed tuple form, for programmatic comparisons.
version_tuple = tuple(int(part) for part in __version__.split("."))
