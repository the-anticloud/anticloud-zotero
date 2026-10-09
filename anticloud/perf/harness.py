"""Performance harness.

Four measurements, all emitted as one machine-readable JSON document:

``cold_import``
    Interpreter startup plus importing the package, measured in a **fresh
    subprocess** so module caching cannot flatter the number.
``cold_start``
    Time to construct the package's core objects and reach a usable state.
``memory_ceiling``
    Resident set size after the core objects are built, via ``tracemalloc`` for
    the traced allocation and the OS-reported working set for the total.
``microbench``
    Hot-path operations timed over a warm loop, reported with median and p95 so
    a single scheduling hiccup cannot masquerade as a regression.

Every measurement reports the environment it was taken in.  A throughput number
without the interpreter version, platform and iteration count is not evidence.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

#: Package import root, resolved from this file so the harness works from any cwd.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

#: Import statement timed by ``cold_import``.
COLD_IMPORT_TARGET = "anticloud_ref"

#: Ceiling on traced Python heap growth for the core workload, in bytes.
#: 64 MiB is generous for ~2000 CRDT operations and small enough that a
#: pathological leak in any single structure trips it.
MEMORY_CEILING_BYTES = 64 * 1024 * 1024

#: Ceiling on subprocess cold-import wall time, in milliseconds.
#: Generous: this measures "does not hang or drag in a heavy dependency tree",
#: not "is fast".
COLD_IMPORT_CEILING_MS = 5_000.0

#: Iterations for each microbench, chosen so one bench is tens of milliseconds.
MICROBENCH_ITERATIONS = 2_000


class PerfThresholdError(AssertionError):
    """Raised when a measurement breaches its declared ceiling."""


@dataclass
class Measurement:
    """One named measurement with its ceiling and verdict."""

    name: str
    value: float
    unit: str
    ceiling: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        if self.ceiling is None:
            return True
        return self.value <= self.ceiling

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "ceiling": self.ceiling,
            "ok": self.ok,
            "detail": self.detail,
        }


def environment_info() -> dict[str, Any]:
    """Describe the machine and interpreter the measurements were taken on."""
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "executable": sys.executable,
    }


# --------------------------------------------------------------------- cold import
def measure_cold_import(
    target: str = COLD_IMPORT_TARGET,
    *,
    runs: int = 3,
    ceiling_ms: float = COLD_IMPORT_CEILING_MS,
    timeout_s: float = 120.0,
) -> Measurement:
    """Time ``import <target>`` in a fresh interpreter, cold every time.

    Each run is a new process with ``-X importtime`` disabled and no bytecode
    cache reused for the measurement, so this genuinely measures import cost
    rather than a warm module dict.
    """
    code = (
        "import time, sys\n"
        "start = time.perf_counter()\n"
        f"import {target}\n"
        "end = time.perf_counter()\n"
        "print((end - start) * 1000.0)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    samples: list[float] = []
    errors: list[str] = []
    for _ in range(max(1, runs)):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_s,
                check=True,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"import timed out after {timeout_s}s")
            break
        except subprocess.CalledProcessError as exc:
            errors.append(f"import failed: {exc.stderr.strip()[:500]}")
            break
        wall_ms = (time.perf_counter() - started) * 1000.0
        try:
            samples.append(float(completed.stdout.strip().splitlines()[-1]))
        except (ValueError, IndexError):
            errors.append(f"unparseable import output: {completed.stdout!r}")
            break
        del wall_ms

    if errors:
        raise PerfThresholdError(f"cold import failed: {'; '.join(errors)}")
    if not samples:
        raise PerfThresholdError("cold import produced no samples")

    best = min(samples)
    return Measurement(
        name="cold_import",
        value=round(best, 3),
        unit="ms",
        ceiling=ceiling_ms,
        detail={
            "target": target,
            "runs": runs,
            "samples_ms": [round(s, 3) for s in samples],
            "best_ms": round(best, 3),
            "worst_ms": round(max(samples), 3),
            "median_ms": round(statistics.median(samples), 3),
            "process_cold": True,
        },
    )


# -------------------------------------------------------------------- cold start
def measure_cold_start(*, iterations: int = 1) -> Measurement:
    """Time building the core objects from scratch (in-process, no cache).

    This is the "time to first useful state" figure: constructing a counter, a
    set, a register and a provenance chain and performing one operation on each.
    """
    from anticloud_ref.crdt.gcounter import GCounter
    from anticloud_ref.crdt.lww import LWWRegister
    from anticloud_ref.crdt.orset import ORSet
    from anticloud_ref.crdt.pncounter import PNCounter
    from anticloud_ref.provenance.chain import ProvenanceChain

    def build_once() -> None:
        counter = GCounter("perf")
        counter.increment()
        counter.state_dict()

        pn = PNCounter("perf")
        pn.apply(1)
        pn.state_dict()

        members = ORSet("perf")
        members.add("perf")
        members.state_dict()

        register = LWWRegister("perf")
        register.assign("perf")
        register.state_dict()

        chain = ProvenanceChain()
        chain.record("cold_start", payload=b"init", phase="init", status="ready")
        chain.verify()

    samples: list[float] = []
    for _ in range(max(1, iterations)):
        started = time.perf_counter()
        build_once()
        samples.append((time.perf_counter() - started) * 1000.0)

    best = min(samples)
    return Measurement(
        name="cold_start",
        value=round(best, 3),
        unit="ms",
        ceiling=1_000.0,
        detail={
            "iterations": iterations,
            "best_ms": round(best, 3),
            "worst_ms": round(max(samples), 3),
            "median_ms": round(statistics.median(samples), 3),
            "objects": ["GCounter", "PNCounter", "ORSet", "LWWRegister", "ProvenanceChain"],
        },
    )


# ----------------------------------------------------------------- memory ceiling
def measure_memory(*, operations: int = 2_000, ceiling_bytes: int = MEMORY_CEILING_BYTES) -> Measurement:
    """Measure peak traced allocation while exercising every core structure."""
    from anticloud_ref.crdt.gcounter import GCounter
    from anticloud_ref.crdt.lww import LWWRegister
    from anticloud_ref.crdt.orset import ORSet
    from anticloud_ref.crdt.pncounter import PNCounter
    from anticloud_ref.provenance.chain import ProvenanceChain

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        baseline, _ = tracemalloc.get_traced_memory()

        counter = GCounter("mem")
        pn = PNCounter("mem")
        members = ORSet("mem")
        register = LWWRegister("mem")
        chain = ProvenanceChain()

        for index in range(operations):
            counter.increment()
            pn.apply(1 if index % 2 else -1)
            members.add(f"element-{index}")
            register.assign(index)
            if index % 50 == 0:
                chain.record("mem", payload=str(index).encode(), i=index)

        peak, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    growth = max(0, peak - baseline)
    working_set = _process_working_set_bytes()
    return Measurement(
        name="memory_ceiling",
        value=float(growth),
        unit="bytes",
        ceiling=float(ceiling_bytes),
        detail={
            "operations": operations,
            "baseline_bytes": baseline,
            "peak_bytes": peak,
            "growth_bytes": growth,
            "growth_mib": round(growth / (1024 * 1024), 3),
            "chain_records": len(chain),
            "orset_elements": len(members),
            "process_working_set_bytes": working_set,
            "process_working_set_mib": round((working_set or 0) / (1024 * 1024), 3),
        },
    )


def _process_working_set_bytes() -> int | None:
    """Return the OS-reported working set, or None where unavailable."""
    try:
        import resource
    except ImportError:
        pass
    else:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB, macOS reports bytes.
        return usage * 1024 if sys.platform != "darwin" else usage

    if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI
        try:
            import ctypes

            class _Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_uint32),
                    ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        except (AttributeError, OSError):
            return None
    return None


# --------------------------------------------------------------------- microbench
def _time_operation(fn: Callable[[int], Any], iterations: int) -> list[float]:
    """Run ``fn`` ``iterations`` times, returning per-call microseconds."""
    samples: list[float] = []
    for index in range(iterations):
        started = time.perf_counter()
        fn(index)
        samples.append((time.perf_counter() - started) * 1e6)
    return samples


def _summarise(name: str, samples_us: Sequence[float], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    ordered = sorted(samples_us)
    total_ms = sum(samples_us) / 1000.0
    return {
        "name": name,
        "iterations": len(ordered),
        "total_ms": round(total_ms, 4),
        "mean_us": round(statistics.fmean(ordered), 4),
        "median_us": round(statistics.median(ordered), 4),
        "p95_us": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 4),
        "max_us": round(ordered[-1], 4),
        "ops_per_sec": round(len(ordered) / total_ms * 1000.0, 2) if total_ms > 0 else None,
        "detail": detail or {},
    }


def run_microbenches(*, iterations: int = MICROBENCH_ITERATIONS) -> dict[str, Any]:
    """Time the hot paths of every core structure.

    Each bench builds its own fixture so the timed region measures the
    operation, not the setup.
    """
    from anticloud_ref.crdt.gcounter import GCounter
    from anticloud_ref.crdt.lww import LWWRegister
    from anticloud_ref.crdt.orset import ORSet
    from anticloud_ref.crdt.pncounter import PNCounter
    from anticloud_ref.provenance.chain import ProvenanceChain

    n = max(1, iterations)
    results: dict[str, Any] = {}

    g = GCounter("bench")
    results["gcounter_increment"] = _summarise("gcounter_increment", _time_operation(lambda _i: g.increment(), n))

    g2 = GCounter("bench-b")
    g2.increment(10)
    results["gcounter_merge"] = _summarise("gcounter_merge", _time_operation(lambda _i: g.merged(g2), n))

    p = PNCounter("bench")
    results["pncounter_apply"] = _summarise("pncounter_apply", _time_operation(lambda i: p.apply(1 if i % 2 else -1), n))

    s = ORSet("bench")
    results["orset_add"] = _summarise("orset_add", _time_operation(lambda i: s.add(f"e{i}"), n))
    results["orset_contains"] = _summarise("orset_contains", _time_operation(lambda i: s.contains(f"e{i // 2}"), n))

    r = LWWRegister("bench")
    results["lww_assign"] = _summarise("lww_assign", _time_operation(lambda i: r.assign(i), n))

    chain = ProvenanceChain()
    results["provenance_record"] = _summarise(
        "provenance_record",
        _time_operation(lambda i: chain.record("bench", payload=str(i).encode(), i=i), max(50, n // 10)),
    )
    results["provenance_verify"] = _summarise(
        "provenance_verify",
        _time_operation(lambda _i: chain.verify(), max(20, n // 50)),
        {"chain_length": len(chain)},
    )

    return results


# ----------------------------------------------------------------------- report
def run_full_report(
    *,
    cold_import_runs: int = 3,
    memory_operations: int = 2_000,
    microbench_iterations: int = MICROBENCH_ITERATIONS,
) -> dict[str, Any]:
    """Run every measurement and return one JSON-ready document."""
    measurements: list[Measurement] = [
        measure_cold_import(runs=cold_import_runs),
        measure_cold_start(),
        measure_memory(operations=memory_operations),
    ]

    report: dict[str, Any] = {
        "schema": "anticloud-ref.perf/1",
        "environment": environment_info(),
        "measurements": [m.as_dict() for m in measurements],
        "microbench": run_microbenches(iterations=microbench_iterations),
        "thresholds": {
            "cold_import_ms": COLD_IMPORT_CEILING_MS,
            "cold_start_ms": 1_000.0,
            "memory_ceiling_bytes": MEMORY_CEILING_BYTES,
        },
    }
    report["all_within_ceilings"] = all(m.ok for m in measurements)
    report["breaches"] = [m.name for m in measurements if not m.ok]
    return report


def write_report(report: dict[str, Any], path: str | os.PathLike[str]) -> Path:
    """Write the report as deterministic JSON and return its path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def format_summary(report: dict[str, Any]) -> str:
    """Render a short human-readable summary of a report."""
    lines = [f"anticloud-ref perf report ({report['environment']['python_version']} on {report['environment']['platform']})"]
    for measurement in report["measurements"]:
        ceiling = "n/a" if measurement["ceiling"] is None else f"{measurement['ceiling']:g}"
        status = "PASS" if measurement["ok"] else "FAIL"
        lines.append(f"  [{status}] {measurement['name']}: {measurement['value']:g} {measurement['unit']} (ceiling {ceiling})")
    lines.append(f"  microbench groups: {len(report['microbench'])}")
    for name, bench in sorted(report["microbench"].items()):
        rate = bench["ops_per_sec"]
        lines.append(f"    {name}: {bench['median_us']} us median, {rate} ops/s over {bench['iterations']} iterations")
    lines.append(f"  all_within_ceilings={report['all_within_ceilings']}")
    return "\n".join(lines)


def assert_within_ceilings(report: dict[str, Any]) -> None:
    """Raise :class:`PerfThresholdError` if any measurement breached."""
    breaches = report.get("breaches") or []
    if breaches:
        raise PerfThresholdError(f"perf ceilings breached: {', '.join(breaches)}")


def iter_measurements(report: dict[str, Any]) -> Iterable[Measurement]:
    """Yield :class:`Measurement` objects rebuilt from a report document."""
    for entry in report.get("measurements", []):
        yield Measurement(
            name=entry["name"],
            value=entry["value"],
            unit=entry["unit"],
            ceiling=entry.get("ceiling"),
            detail=entry.get("detail", {}),
        )
