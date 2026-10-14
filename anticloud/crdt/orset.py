"""Observed-Remove Set (OR-Set) with unique tags.

Each add writes a unique tag.  A concurrent add/remove pair resolves in favour
of the add: the remove deletes only the tags it actually observed, so a tag
born concurrently with the remove survives.  This gives *add-wins* semantics
while retaining a single state-based merge (union of tags), which is what makes
the type an OR-Set rather than a grow-only set.

Reference: Shapiro et al. 2011, section 2.2.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

__all__ = ["ORSet"]

_TAG_WIDTH = 36  # len(str(uuid.UUID()))


def _new_tag(node_id: str) -> str:
    """Mint a tag that is unique per (replica, call).

    The replica prefix makes tags self-describing, which turns a merge conflict
    into a readable audit record instead of an opaque collision.
    """
    return f"{node_id}:{uuid.uuid4()}"


def _tag_replica(tag: str) -> str:
    return tag[: -_TAG_WIDTH - 1]


def _validate_tag(tag: str) -> None:
    if not isinstance(tag, str) or ":" not in tag or len(tag) < _TAG_WIDTH + 2:
        raise ValueError(f"malformed OR-Set tag: {tag!r}")
    try:
        uuid.UUID(tag[-_TAG_WIDTH:])
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"malformed OR-Set tag: {tag!r}") from exc


class ORSet:
    """Add-wins observed-remove set."""

    __slots__ = ("_node_id", "_tags", "_removed")

    def __init__(self, node_id: str) -> None:
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a non-empty string")
        self._node_id = node_id
        self._tags: dict[str, set[str]] = {}
        self._removed: dict[str, set[str]] = {}

    # ------------------------------------------------------------------ read
    @property
    def node_id(self) -> str:
        return self._node_id

    def contains(self, element: str) -> bool:
        """True iff ``element`` has at least one live (un-removed) tag."""
        live = self._tags.get(element)
        if not live:
            return False
        dead = self._removed.get(element)
        if not dead:
            return True
        return bool(live - dead)

    def __contains__(self, element: object) -> bool:
        if not isinstance(element, str):
            return False
        return self.contains(element)

    def elements(self) -> frozenset[str]:
        """All live elements."""
        if not self._tags:
            return frozenset()
        dead_all = self._removed
        out: set[str] = set()
        for element, tags in self._tags.items():
            dead = dead_all.get(element)
            if dead is None or (tags - dead):
                out.add(element)
        return frozenset(out)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self.elements()))

    def __len__(self) -> int:
        return len(self.elements())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ORSet):
            return NotImplemented
        return self._tags == other._tags and self._removed == other._removed

    def __hash__(self) -> int:
        return hash(
            (
                tuple(sorted((k, tuple(sorted(v))) for k, v in self._tags.items())),
                tuple(sorted((k, tuple(sorted(v))) for k, v in self._removed.items())),
            )
        )

    def __repr__(self) -> str:
        return f"ORSet({sorted(self.elements())!r})"

    def tags_for(self, element: str) -> frozenset[str]:
        """All tags ever observed for ``element``, live and removed."""
        return frozenset(self._tags.get(element, ())) | frozenset(self._removed.get(element, ()))

    def tombstone_count(self) -> int:
        """Number of removed tags retained.  Garbage collection would shrink this."""
        return sum(len(v) for v in self._removed.values())

    # ----------------------------------------------------------------- write
    def add(self, element: str) -> str:
        """Add ``element`` with a fresh tag.  Returns the tag."""
        if not isinstance(element, str) or not element:
            raise ValueError("element must be a non-empty string")
        tag = _new_tag(self._node_id)
        self._tags.setdefault(element, set()).add(tag)
        return tag

    def add_with_tag(self, element: str, tag: str) -> str:
        """Re-apply a *previously received* tag during merge.  Returns the tag."""
        _validate_tag(tag)
        self._tags.setdefault(element, set()).add(tag)
        return tag

    def remove(self, element: str) -> bool:
        """Observed-remove ``element``.

        Returns True iff the element was present (i.e. some live tag existed)
        at the moment of the call.
        """
        if not isinstance(element, str) or not element:
            raise ValueError("element must be a non-empty string")
        live = self._tags.get(element)
        if not live:
            return False
        dead = self._removed.setdefault(element, set())
        observable = live - dead
        if not observable:
            return False
        dead |= observable
        return True

    def purge_tombstones(self, observed_by_all: Iterable[ORSet]) -> int:
        """Drop tags known removed by *every* replica.  Returns tags dropped.

        Safe only once the caller can prove all replicas have observed the
        removals; until then, dropping a tag allows a stale replica to resurrect
        the element, which is why the number of live replicas is required.
        """
        peers = list(observed_by_all)
        for peer in peers:
            if not isinstance(peer, ORSet):
                raise TypeError(
                    f"purge_tombstones expects ORSet observers, got {type(peer).__name__}"
                )
        if not peers:
            return 0

        # A tag is droppable only when EVERY observer has it tombstoned, so this
        # is an intersection across observers, not a union.  A union would purge
        # on the strength of one replica and let any lagging peer resurrect the
        # element -- exactly the failure the tombstone exists to prevent.
        per_peer = [{tag for tags in peer._removed.values() for tag in tags} for peer in peers]
        acknowledged: set[str] = set.intersection(*per_peer)

        dropped = 0
        for element in list(self._tags):
            dead = self._removed.get(element, set())
            droppable = dead & acknowledged
            if not droppable:
                continue
            dropped += len(droppable)
            self._tags[element] -= droppable
            self._removed[element] = dead - droppable
            if not self._tags[element]:
                self._tags.pop(element, None)
                self._removed.pop(element, None)
            elif not self._removed[element]:
                self._removed.pop(element, None)
        return dropped

    # ----------------------------------------------------------------- merge
    def merge(self, other: "ORSet") -> "ORSet":
        """In-place join: union of tags and union of removal tombstones."""
        if not isinstance(other, ORSet):
            raise TypeError("can only merge another ORSet")
        for element, tags in other._tags.items():
            mine = self._tags.setdefault(element, set())
            mine |= tags
        for element, tags in other._removed.items():
            mine = self._removed.setdefault(element, set())
            mine |= tags
        return self

    def merged(self, other: "ORSet") -> "ORSet":
        """Non-mutating join."""
        clone = ORSet(self._node_id)
        clone.merge(self)
        return clone.merge(other)

    def clone_as(self, node_id: str) -> "ORSet":
        """Copy this set's full state onto a handle owned by ``node_id``.

        Used to fork a replica in tests and simulations: the fork inherits every
        observed tag and tombstone, but writes new tags under its own id.  That
        is exactly the divergent-then-converge topology the convergence checks
        need, and it avoids the copy inheriting the original handle's identity.
        """
        fork = ORSet(node_id)
        fork._tags = {k: set(v) for k, v in self._tags.items()}
        fork._removed = {k: set(v) for k, v in self._removed.items()}
        return fork

    # ------------------------------------------------------------ (de)serial
    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "ORSet",
            "node_id": self._node_id,
            "tags": {k: sorted(v) for k, v in sorted(self._tags.items())},
            "removed": {k: sorted(v) for k, v in sorted(self._removed.items())},
        }

    @classmethod
    def from_state_dict(cls, data: Mapping[str, Any]) -> "ORSet":
        if not isinstance(data, Mapping):
            raise TypeError("state must be a mapping")
        if data.get("type") != "ORSet":
            raise ValueError(f"expected type 'ORSet', got {data.get('type')!r}")
        if "node_id" not in data:
            raise KeyError("state is missing 'node_id'")
        node_id = str(data["node_id"])
        # Tags are self-describing, so a mismatch between the handle's replica id
        # and the tag prefix is a genuine corruption signal, not a cosmetic one.
        obj = cls(node_id)
        tags = data.get("tags") or {}
        removed = data.get("removed") or {}
        if not isinstance(tags, Mapping) or not isinstance(removed, Mapping):
            raise TypeError("'tags' and 'removed' must be mappings")
        for element, tag_list in tags.items():
            if not isinstance(tag_list, (list, tuple, set, frozenset)):
                raise TypeError(f"tags for {element!r} must be a sequence")
            for tag in tag_list:
                obj.add_with_tag(str(element), str(tag))
        for element, tag_list in removed.items():
            bucket = obj._removed.setdefault(str(element), set())
            for tag in tag_list:
                _validate_tag(str(tag))
                bucket.add(str(tag))
        return obj