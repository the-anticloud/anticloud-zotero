"""Benchmark runner: 16 independently-reported checks over this repository.

The aggregate is the AND of the individual results, so a green aggregate can
never hide a red sub-check.  Every PASS carries evidence a reader can re-run.
"""

from anticloud_ref.bench.compliance import (
    FRAMEWORKS,
    Control,
    Framework,
    all_frameworks,
    coverage,
)
from anticloud_ref.bench.runner import (
    BENCHMARK_IDS,
    BENCHMARKS,
    LOC_CEILING,
    PROJECT_ROOT,
    TITLES,
    bench_dependency_scan,
    bench_git_health,
    bench_licence,
    bench_loc_files,
    bench_ml_trl,
    bench_sbom,
    format_report,
    run_all,
    run_one,
)
from anticloud_ref.bench.sbom import build_sbom, write_sbom

__all__ = [
    "BENCHMARKS",
    "BENCHMARK_IDS",
    "Control",
    "FRAMEWORKS",
    "Framework",
    "LOC_CEILING",
    "PROJECT_ROOT",
    "TITLES",
    "all_frameworks",
    "bench_dependency_scan",
    "bench_git_health",
    "bench_licence",
    "bench_loc_files",
    "bench_ml_trl",
    "bench_sbom",
    "build_sbom",
    "coverage",
    "format_report",
    "run_all",
    "run_one",
    "write_sbom",
]
