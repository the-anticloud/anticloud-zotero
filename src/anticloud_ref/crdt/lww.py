"""LWW-Register with a hybrid logical clock for tie-breaking.

Last-write-wins needs a total order over writes.  Wall-clock time alone is not
sufficient: two replicas can produce the same timestamp, and a clock skewed
backwards can make a newer write lose.  A *hybrid logical clock* (Kulkarni et
al., 2014) gives each write a tuple ``(physical_ms, logical, replica_id)`` that
is monotonic per replica and totally ordered across replicas.

Merge keeps the maximum of that tuple, which is commutative, associative and
idempotent, so the register converges like every other state-based CRDT.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

__all__ = ["HybridLogicalClock", "LWWRegister", "Timestamp"]

# (physical_ms, logical, replica_id) — physical dominates, logical breaks
# same-millisecond ties within a replica, replica_id breaks cross-replica ties.
Timestamp = tuple[int, int, str]


class HybridLogicalClock:
    """Monotonic per-instance clock producing :data:`Timestamp` tuples."""

    __slots__ = ("_node_id", "_last", "_lock", "_time_fn")

    def __init__(self, node_id: str, time_fn: Callable[[], float] | None = None) -> None:
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a non-empty string")
        self._node_id = node_id
        self._last: Timestamp = (0, 0, node_id)
        self._lock = threading.Lock()
        self._time_fn = time_fn or time.time

    @property
    def node_id(self) -> str:
        return self._node_id

    def now(self) -> Timestamp:
        """Stamp an event with the current hybrid time.

        If the wall clock has advanced past the last stamp, the physical
        component jumps forward and the logical counter resets.  If the clock
        stalled or went backwards, the logical counter increments instead — so
        timestamps never regress even under clock skew.
        """
        with self._lock:
            wall_ms = int(self._time_fn() * 1000)
            last_phys, last_logical, _ = self._last
            if wall_ms > last_phys:
                self._last = (wall_ms, 0, self._node_id)
            else:
                self._last = (last_phys, last_logical + 1, self._node_id)
            return self._last

    def observe(self, remote: Timestamp) -> Timestamp:
        """Merge a received timestamp, returning a stamp guaranteed larger.

        This is what makes an HLC causally consistent: receiving a remote event
        guarantees every subsequent local event sorts after it.
        """
        if not isinstance(remote, tuple) or len(remote) != 3:
            raise TypeError("remote timestamp must be a 3-tuple")
        r_phys, r_logical, r_node = remote
        if not isinstance(r_phys, int) or isinstance(r_phys, bool):
            raise TypeError("physical component must be int")
        if not isinstance(r_logical, int) or isinstance(r_logical, bool):
            raise TypeError("logical component must be int")
        if not isinstance(r_node, str) or not r_node:
            raise TypeError("replica component must be a non-empty string")
        with self._lock:
            last_phys, last_logical, _ = self._last
            wall_ms = int(self._time_fn() * 1000)
            new_phys = max(wall_ms, last_phys, r_phys)
            if new_phys == last_phys and new_phys == r_phys:
                new_logical = max(last_logical, r_logical) + 1
            elif new_phys == last_phys:
                new_logical = last_logical + 1
            elif new_phys == r_phys:
                new_logical = r_logical + 1
            else:
                new_logical = 0
            self._last = (new_phys, new_logical, self._node_id)
            return self._last


class LWWRegister:
    """A single value resolved by last-write-wins."""

    __slots__ = ("_node_id", "_value", "_timestamp", "_clock")

    def __init__(
        self,
        node_id: str,
        initial: Any = None,
        clock: HybridLogicalClock | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a non-empty string")
        self._node_id = node_id
        self._value = initial
        self._clock = clock or HybridLogicalClock(node_id, time_fn)
        self._timestamp: Timestamp = (0, 0, node_id)

    # ------------------------------------------------------------------ read
    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def clock(self) -> HybridLogicalClock:
        return self._clock

    def value(self) -> Any:
        return self._value

    def timestamp(self) -> Timestamp:
        """The winning timestamp."""
        return self._timestamp

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LWWRegister):
            return NotImplemented
        return self._value == other._value and self._timestamp == other._timestamp

    def __hash__(self) -> int:
        return hash((self._value, self._timestamp))

    def __repr__(self) -> str:
        return f"LWWRegister({self._value!r} @ {self._timestamp!r})"

    # ----------------------------------------------------------------- write
    def assign(self, value: Any) -> Any:
        """Write ``value`` stamped with the current hybrid time."""
        stamp = self._clock.now()
        self._value = value
        self._timestamp = stamp
        return value

    # ----------------------------------------------------------------- merge
    def merge(self, other: "LWWRegister") -> "LWWRegister":
        """Keep whichever side carries the greater timestamp."""
        if not isinstance(other, LWWRegister):
            raise TypeError("can only merge another LWWRegister")
        if other._timestamp > self._timestamp:
            self._value = other._value
            self._timestamp = other._timestamp
        return self

    def merged(self, other: "LWWRegister") -> "LWWRegister":
        """Non-mutating merge."""
        clone = LWWRegister(self._node_id)
        clone._value = self._value
        clone._timestamp = self._timestamp
        return clone.merge(other)

    # ------------------------------------------------------------ (de)serial
    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "LWWRegister",
            "node_id": self._node_id,
            "value": self._value,
            "timestamp": list(self._timestamp),
        }

    @classmethod
    def from_state_dict(cls, data: Mapping[str, Any]) -> "LWWRegister":
        if not isinstance(data, Mapping):
            raise TypeError("state must be a mapping")
        if data.get("type") != "LWWRegister":
            raise ValueError(f"expected type 'LWWRegister', got {data.get('type')!r}")
        if "node_id" not in data:
            raise KeyError("state is missing 'node_id'")
        stamp = data.get("timestamp")
        if stamp is None:
            stamp = (0, 0, str(data["node_id"]))
        if not isinstance(stamp, (list, tuple)) or len(stamp) != 3:
            raise ValueError("'timestamp' must be a 3-element sequence")
        obj = cls(str(data["node_id"]), data.get("value"))
        obj._timestamp = (int(stamp[0]), int(stamp[1]), str(stamp[2]))
        obj._clock.observe(obj._timestamp)
        return obj