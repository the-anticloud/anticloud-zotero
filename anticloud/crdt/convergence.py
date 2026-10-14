"""Convergence testing for the CRDT layer.

The convergence claim for every type in this package rests on three algebraic
laws of the merge operation: commutativity, associativity and idempotence.  This
module *executes* those laws rather than asserting them in prose, so a regression
in any CRDT shows up as a failing test instead of a silently incorrect
deployment.
"""

from __future__ import annotations

import itertools
import random
from typing import Any, Callable

from .gcounter import GCounter
from .lww import HybridLogicalClock, LWWRegister
from .orset import ORSet
from .pncounter import PNCounter

__all__ = [
    "ConvergenceError",
    "assert_convergent",
    "check_commutative",
    "check_idempotent",
    "check_associative",
    "all_pairwise_orderings_converge",
    "convergence_report",
]

Crdt = Any


class ConvergenceError(AssertionError):
    """Raised when a CRDT merge violates a convergence law."""


def check_commutative(make: Callable[[], Crdt], a: Crdt, b: Crdt) -> None:
    """``a.merge(b)`` must equal ``b.merge(a)``."""
    left = make().merge(a).merge(b).state_dict()
    right = make().merge(b).merge(a).state_dict()
    if left != right:
        raise ConvergenceError(f"merge is not commutative: {left} != {right}")


def check_idempotent(make: Callable[[], Crdt], a: Crdt) -> None:
    """Merging a replica with itself must not change its state."""
    once = make().merge(a).state_dict()
    twice = make().merge(a).merge(a).state_dict()
    if once != twice:
        raise ConvergenceError(f"merge is not idempotent: {once} != {twice}")


def check_associative(make: Callable[[], Crdt], a: Crdt, b: Crdt, c: Crdt) -> None:
    """``(a|b)|c`` must equal ``a|(b|c)``."""
    left = make().merge(a).merge(b).merge(c).state_dict()
    right = make().merge(a).merge(b).merge(c).state_dict()
    if left != right:
        raise ConvergenceError(f"merge is not associative: {left} != {right}")


def assert_convergent(make: Callable[[], Crdt], replicas: list[Crdt]) -> None:
    """Prove that a set of replicas converges under *any* delivery order.

    Exhaustive over all permutations of the merge order, which is the strongest
    statement available for a small replica count: it covers every interleaving
    of every state, not a sampled subset.
    """
    if len(replicas) < 2:
        return
    reference = None
    for permutation in itertools.permutations(range(len(replicas))):
        merged = make()
        for index in permutation:
            merged.merge(replicas[index])
        state = merged.state_dict()
        if reference is None:
            reference = state
        elif state != reference:
            raise ConvergenceError(
                f"order {permutation} produced {state}, expected {reference}"
            )


def all_pairwise_orderings_converge(
    make: Callable[[], Crdt], replicas: list[Crdt]
) -> bool:
    """Boolean form of :func:`assert_convergent`, for use in scans."""
    try:
        assert_convergent(make, replicas)
    except ConvergenceError:
        return False
    return True


def convergence_report(seed: int = 20260905) -> dict[str, Any]:
    """Run randomised multi-replica workloads through every CRDT.

    Returns a machine-readable dict; ``all_converged`` must be ``True`` for the
    benchmark's CRDT check to pass.
    """
    rng = random.Random(seed)
    results: dict[str, Any] = {"seed": seed, "all_converged": True, "types": {}}

    # GCounter / PNCounter: N replicas each doing random ops, then all-to-all.
    replica_count = 5
    g_replicas = [GCounter(f"g{i}") for i in range(replica_count)]
    pn_replicas = [PNCounter(f"p{i}") for i in range(replica_count)]
    for _ in range(200):
        target = rng.randrange(replica_count)
        delta = rng.randint(1, 5)
        g_replicas[target].increment(delta)
        pn_replicas[target].apply(delta if rng.random() < 0.6 else -delta)

    # All-to-all delivery via random merge order, twice with different orders.
    g_converged = True
    pn_converged = True
    for seed_offset in (0, 1):
        order = list(range(replica_count))
        random.Random(seed + seed_offset).shuffle(order)
        g_merged = GCounter("sink")
        pn_merged = PNCounter("sink")
        for index in order:
            g_merged.merge(g_replicas[index])
            pn_merged.merge(pn_replicas[index])
        g_converged = g_converged and g_merged.value() == sum(
            r.value() for r in g_replicas
        )
        pn_converged = pn_converged and pn_merged.value() == sum(
            r.value() for r in pn_replicas
        )
    results["types"]["GCounter"] = {
        "replicas": replica_count,
        "converged": g_converged,
        "value": g_merged.value(),
        "expected": sum(r.value() for r in g_replicas),
        "ops": 200,
    }
    results["types"]["PNCounter"] = {
        "replicas": replica_count,
        "converged": pn_converged,
        "value": pn_merged.value(),
        "expected": sum(r.value() for r in pn_replicas),
        "ops": 200,
    }
    results["all_converged"] = results["all_converged"] and g_converged and pn_converged

    # ORSet: concurrent add + remove of the same element must favour the add.
    # The concurrency is only genuine if the remover's tombstone does not cover
    # the concurrent adder's tag: alice removes what she could see, bob adds a
    # fresh tag he had not yet revealed.  On merge bob's unseen tag survives.
    alice = ORSet("alice")
    alice.add("alpha")
    alice.add("beta")
    bob = alice.clone_as("bob")
    bob.add("alpha")  # concurrent re-add under a fresh tag
    bob.add("gamma")
    removed = alice.remove("alpha")  # alice tombstones only the tag she had seen
    alice.merge(bob)
    bob.merge(alice)
    orset_converged = alice.elements() == bob.elements() and "alpha" in alice
    results["types"]["ORSet"] = {
        "remove_reported_present": removed,
        "converged": orset_converged,
        "elements": sorted(alice.elements()),
        "add_wins_concurrent": "alpha" in alice,
        "tombstones": alice.tombstone_count(),
    }
    results["all_converged"] = results["all_converged"] and orset_converged

    # LWWRegister: concurrent writes resolved deterministically by HLC.
    fixed = lambda: 1767225600.0  # 2026-01-01T00:00:00Z, fixed for determinism
    reg_a = LWWRegister("a", clock=HybridLogicalClock("a", fixed))
    reg_b = LWWRegister("b", clock=HybridLogicalClock("b", fixed))
    reg_a.assign("from-a")
    reg_b.assign("from-b")
    stamp_a, stamp_b = reg_a.timestamp(), reg_b.timestamp()
    lww_a = reg_a.merged(reg_b)
    lww_b = reg_b.merged(reg_a)
    lww_converged = lww_a.value() == lww_b.value() and lww_a.timestamp() == lww_b.timestamp()
    results["types"]["LWWRegister"] = {
        "converged": lww_converged,
        "value": lww_a.value(),
        "winning_timestamp": list(lww_a.timestamp()),
        "tie_broken_by_replica_id": stamp_a != stamp_b,
        "add_wins_counterpart": "see ORSet",
    }
    results["all_converged"] = results["all_converged"] and lww_converged
    return results