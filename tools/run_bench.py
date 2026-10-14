#!/usr/bin/env python3
"""Run the benchmarks and write BENCH.json.

    python tools/run_bench.py                  # all benchmarks
    python tools/run_bench.py --only 02        # one benchmark
    python tools/run_bench.py --list           # names only
    python tools/run_bench.py --quiet          # exit code only

Exit code is 0 only when every benchmark passes.  A failing benchmark is
reported with its own status and the non-zero exit reflects it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from anticloud_ref.bench import (  # noqa: E402
    BENCHMARK_IDS,
    TITLES,
    format_report,
    run_all,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Anticloud benchmarks and write BENCH.json")
    parser.add_argument("--only", nargs="*", metavar="ID",
                        help="run just these benchmark ids (e.g. 02 04)")
    parser.add_argument("--out", default="BENCH.json", help="report path")
    parser.add_argument("--list", action="store_true", help="list benchmark ids and exit")
    parser.add_argument("--quiet", action="store_true", help="suppress the human report")
    parser.add_argument("--no-sbom", action="store_true", help="do not rewrite sbom.cdx.json")
    args = parser.parse_args(argv)

    if args.list:
        for bid in BENCHMARK_IDS:
            print(f"{bid}\t{TITLES[bid]}")
        return 0

    only: list[str] | None = None
    if args.only:
        only = []
        for token in args.only:
            matches = [b for b in BENCHMARK_IDS if b == token or b.startswith(token)]
            if not matches:
                print(f"unknown benchmark: {token!r}", file=sys.stderr)
                return 2
            only.extend(matches)

    report = run_all(ROOT, only=only, write_sbom=not args.no_sbom)
    report["method"] = {
        "aggregate_rule": "all_passed == AND over benchmarks[*].ok; a FAIL forces the aggregate FAIL",
        "thresholds_note": "no threshold is relaxed by the runner; ceilings live in runner.py "
                           "and are asserted independently in tests/test_project_metadata.py",
        "excluded": "no AI/LLM-latency check is included or required",
        "reproduce": "python tools/run_bench.py && python -m pytest -q",
    }

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.quiet:
        print(format_report(report))
        print(f"\nwrote {out}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
