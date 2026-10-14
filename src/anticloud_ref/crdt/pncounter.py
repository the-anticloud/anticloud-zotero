"""PN-Counter: counter supporting both increment and decrement.

A PN-Counter is the composition of two G-Counters: ``P`` tracks increments and
``N`` tracks decrements.  ``value() == P.value() - N.value()``.  Both halves are
grow-only, so the same join-semilattice convergence argument applies and the
difference of two monotonically non-decreasing registers is well defined.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .gcounter import GCounter

__all__ = ["PNCounter"]


class PNCounter:
    """Positive/negative counter replica."""

    __slots__ = ("_node_id", "_p", "_n")

    def __init__(self, node_id: str) -> None:
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a non-empty string")
        self._node_id = node_id
        self._p = GCounter(node_id)
        self._n = GCounter(node_id)

    # ------------------------------------------------------------------ read
    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def positive(self) -> GCounter:
        return self._p

    @property
    def negative(self) -> GCounter:
        return self._n

    def value(self) -> int:
        return self._p.value() - self._n.value()

    def __int__(self) -> int:
        return self.value()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PNCounter):
            return NotImplemented
        return self._p == other._p and self._n == other._n

    def __hash__(self) -> int:
        return hash((self._p, self._n))

    def __repr__(self) -> str:
        return f"PNCounter(p={self._p.counts!r}, n={self._n.counts!r})"

    # ----------------------------------------------------------------- write
    def increment(self, amount: int = 1) -> int:
        """Add ``amount`` to the value."""
        self._p.increment(amount)
        return self.value()

    def decrement(self, amount: int = 1) -> int:
        """Subtract ``amount`` from the value."""
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise TypeError("amount must be int")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        self._n.increment(amount)
        return self.value()

    def apply(self, delta: int) -> int:
        """Apply a signed delta; positive dispatches to :meth:`increment`."""
        if not isinstance(delta, int) or isinstance(delta, bool):
            raise TypeError("delta must be int")
        if delta > 0:
            return self.increment(delta)
        if delta < 0:
            return self.decrement(-delta)
        return self.value()

    # ----------------------------------------------------------------- merge
    def merge(self, other: "PNCounter") -> "PNCounter":
        """In-place join of both halves."""
        if not isinstance(other, PNCounter):
            raise TypeError("can only merge another PNCounter")
        self._p.merge(other._p)
        self._n.merge(other._n)
        return self

    def merged(self, other: "PNCounter") -> "PNCounter":
        """Non-mutating join."""
        clone = PNCounter(self._node_id)
        clone._p = self._p.merged(other._p)
        clone._n = self._n.merged(other._n)
        return clone

    # ------------------------------------------------------------ (de)serial
    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "PNCounter",
            "node_id": self._node_id,
            "positive": self._p.counts,
            "negative": self._n.counts,
        }

    @classmethod
    def from_state_dict(cls, data: Mapping[str, Any]) -> "PNCounter":
        if not isinstance(data, Mapping):
            raise TypeError("state must be a mapping")
        if data.get("type") != "PNCounter":
            raise ValueError(f"expected type 'PNCounter', got {data.get('type')!r}")
        if "node_id" not in data:
            raise KeyError("state is missing 'node_id'")
        counter = cls(str(data["node_id"]))
        positive = data.get("positive") or {}
        negative = data.get("negative") or {}
        if not isinstance(positive, Mapping) or not isinstance(negative, Mapping):
            raise TypeError("'positive' and 'negative' must be mappings")
        counter._p = GCounter(counter._node_id, positive)
        counter._n = GCounter(counter._node_id, negative)
        return counter