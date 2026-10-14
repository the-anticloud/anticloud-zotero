"""G-Counter: a grow-only counter CRDT.

State is a map from replica id to a non-negative integer.  A replica may only
increment its *own* entry, so no two replicas ever write the same key and the
merge (per-key maximum) is a join semilattice.  Because merge is commutative,
associative and idempotent, any delivery order of any number of concurrent
updates converges to the same state.

Reference: Shapiro et al., "A comprehensive study of Convergent and Commutative
Replicated Data Types" (INRIA RR-7506, 2011).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

__all__ = ["GCounter"]


class GCounter:
    """Grow-only counter over a fixed or growing set of replica ids."""

    __slots__ = ("_node_id", "_counts")

    def __init__(self, node_id: str, counts: Mapping[str, int] | None = None) -> None:
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a non-empty string")
        self._node_id = node_id
        self._counts: dict[str, int] = {}
        if counts is not None:
            for key, value in counts.items():
                if not isinstance(value, int) or isinstance(value, bool):
                    raise TypeError(f"counter value for {key!r} must be int")
                if value < 0:
                    raise ValueError(f"counter value for {key!r} must be >= 0")
                self._counts[str(key)] = int(value)

    # ------------------------------------------------------------------ read
    @property
    def node_id(self) -> str:
        """The replica identity owning this handle."""
        return self._node_id

    @property
    def counts(self) -> dict[str, int]:
        """A defensive copy of the per-replica counter state."""
        return dict(self._counts)

    @property
    def replicas(self) -> tuple[str, ...]:
        """Sorted tuple of replica ids present in the state."""
        return tuple(sorted(self._counts))

    def value(self) -> int:
        """Total across all replicas."""
        return sum(self._counts.values())

    def local(self) -> int:
        """This replica's own contribution."""
        return self._counts.get(self._node_id, 0)

    def __int__(self) -> int:
        return self.value()

    def __len__(self) -> int:
        return len(self._counts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GCounter):
            return NotImplemented
        return self._counts == other._counts

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._counts.items())))

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._counts))

    def __repr__(self) -> str:
        return f"GCounter({self._counts!r})"

    # ----------------------------------------------------------------- write
    def increment(self, amount: int = 1) -> int:
        """Increment this replica's own entry by ``amount``.

        Returns the new local value.  ``amount`` must be a positive integer;
        a grow-only counter by definition cannot decrement.
        """
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise TypeError("amount must be int")
        if amount <= 0:
            raise ValueError("amount must be > 0 for a grow-only counter")
        current = self._counts.get(self._node_id, 0)
        self._counts[self._node_id] = current + amount
        return self._counts[self._node_id]

    def reset(self) -> None:
        """Zero only this replica's own entry.

        Resetting to 0 is not a legal state transition in the CRDT model: two
        replicas that reset concurrently can permanently lose increments made
        by the resetting replica before it was observed.  The method exists
        only to build test fixtures and is deliberately documented as unsafe.
        Use a fresh :class:`GCounter` instead.
        """
        self._counts[self._node_id] = 0

    # ----------------------------------------------------------------- merge
    def merge(self, other: "GCounter") -> "GCounter":
        """In-place join.  Per-replica maximum."""
        if not isinstance(other, GCounter):
            raise TypeError("can only merge another GCounter")
        for key, value in other._counts.items():
            mine = self._counts.get(key)
            if mine is None or value > mine:
                self._counts[key] = value
        return self

    def merged(self, other: "GCounter") -> "GCounter":
        """Non-mutating join returning a new counter."""
        clone = GCounter(self._node_id, self._counts)
        return clone.merge(other)

    def state_dict(self) -> dict[str, Any]:
        """Serialisable state."""
        return {"type": "GCounter", "node_id": self._node_id, "counts": dict(self._counts)}

    @classmethod
    def from_state_dict(cls, data: Mapping[str, Any]) -> "GCounter":
        """Rebuild from :meth:`state_dict` output, validating the shape."""
        if not isinstance(data, Mapping):
            raise TypeError("state must be a mapping")
        kind = data.get("type")
        if kind != "GCounter":
            raise ValueError(f"expected type 'GCounter', got {kind!r}")
        if "node_id" not in data:
            raise KeyError("state is missing 'node_id'")
        counts = data.get("counts")
        if counts is None:
            counts = {}
        if not isinstance(counts, Mapping):
            raise TypeError("'counts' must be a mapping")
        return cls(str(data["node_id"]), counts)