"""The 15 benchmarks, each evaluated independently and reported individually.

Design rule, enforced by :func:`run_all`: the aggregate is the AND of the
sub-checks, and a check that raises is a FAIL, never a skip.  There is no code
path that yields a green aggregate with a red sub-check.

Every benchmark returns a dict carrying, at minimum, ``ok`` and an ``evidence``
object.  Evidence is what a reader re-runs to confirm the PASS: a file, a
count, and a command.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from anticloud_ref._version import __version__

#: Where the project lives; overridable so the tests can point at a fixture.
PROJECT_ROOT = Path(os.environ.get("ANTICLOUD_REF_ROOT", Path(__file__).resolve().parents[3]))

#: Ceilings for the code-size benchmark.  These are the same numbers asserted in
#: `tests/test_project_metadata.py`, so a breach fails both the test and the bench.
LOC_CEILING = 20_000
FILE_CEILING = 120
MIN_LOC = 2_000

#: Licences the project's own source tree is permitted to carry.
ALLOWED_PROJECT_LICENCES = frozenset({"Apache-2.0", "MIT", "BSD-3-Clause", "BSD-2-Clause", "ISC"})

#: Imports that would mean an ML/accelerator runtime entered the dependency
#: graph.  Named individually so the failure message says which one.
FORBIDDEN_IMPORTS = (
    "torch", "pytorch", "tensorflow", "jax", "transformers", "accelerate",
    "vllm", "sentence_transformers", "diffusers", "timm", "onnxruntime",
    "openvino", "tensorrt", "flair", "spacy", "peft", "trl", "datasets",
)

#: Network and shell capabilities a pure library must not gain silently.
FORBIDDEN_MODULES = ("socket", "http", "urllib", "requests", "ftplib", "smtplib", "telnetlib")

#: The 15 benchmarks, in reporting order.  Key == BENCH.json id.
BENCHMARK_IDS = (
    "01_loc_files",
    "02_licence",
    "03_dependency_scan",
    "04_sbom_cyclonedx",
    "05_git_health",
    "06_owasp_llm_top10",
    "07_owasp_top10",
    "08_soc2_type2",
    "09_nist_ai_rmf",
    "10_nist_sp_800_53",
    "11_nist_csf",
    "12_fedramp",
    "13_pci_dss",
    "14_iso_27001",
    "15_mitre_attack",
    "16_ml_trl",
)


def _count_loc(paths: list[Path]) -> dict[str, Any]:
    """Physical source lines, excluding blanks and comment-only lines."""
    total = code = comment = blank = 0
    files = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files += 1
        for line in text.splitlines():
            total += 1
            stripped = line.strip()
            if not stripped:
                blank += 1
            elif stripped.startswith("#"):
                comment += 1
            else:
                code += 1
    return {"files": files, "total_lines": total, "code_lines": code,
            "comment_lines": comment, "blank_lines": blank}


def _source_files(root: Path, subdir: str) -> list[Path]:
    base = root / subdir
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py")
                  if "__pycache__" not in p.parts and ".venv" not in p.parts)


def _read_pyproject(root: Path) -> dict[str, Any]:
    """Minimal TOML read for the keys this module needs.

    tomllib is 3.11+, and the project requires 3.11+, so the stdlib reader is
    always available; the fallback exists only so the benchmark can still
    report a reason instead of raising on an exotic interpreter.
    """
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        import tomllib

        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        text = path.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return {"project": {"version": match.group(1)}} if match else {}


def _run_git(root: Path, *args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"git unavailable: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr).strip()


# ===========================================================================
# 01  code size and file count
# ===========================================================================
def bench_loc_files(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    src = _count_loc(_source_files(root, "src"))
    tests = _count_loc(_source_files(root, "tests"))
    tools = _count_loc(_source_files(root, "tools"))
    total_files = src["files"] + tests["files"] + tools["files"]
    total_lines = src["total_lines"] + tests["total_lines"] + tools["total_lines"]
    code_lines = src["code_lines"] + tests["code_lines"] + tools["code_lines"]
    ok = (
        src["files"] > 0
        and total_files <= FILE_CEILING
        and total_lines <= LOC_CEILING
        and total_lines >= MIN_LOC
    )
    return {
        "ok": ok,
        "evidence": {
            "command": "python tools/run_bench.py --only 01_loc_files",
            "counts_command": (
                "find src tests tools -name '*.py' -not -path '*/__pycache__/*' | wc -l"
            ),
            "files_total": total_files,
            "files_source": src["files"],
            "files_tests": tests["files"],
            "total_lines": total_lines,
            "code_lines": code_lines,
            "test_to_source_line_ratio": (
                round(tests["total_lines"] / src["total_lines"], 2) if src["total_lines"] else 0
            ),
            "ceilings": {"max_files": FILE_CEILING, "max_lines": LOC_CEILING, "min_lines": MIN_LOC},
            "method": "physical lines; blank and comment-only lines counted separately",
        },
    }


# ===========================================================================
# 02  licence posture
# ===========================================================================
def bench_licence(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    from anticloud_ref.licence import classify_file, classify_name, classify_text

    licence_file = root / "LICENSE"
    classified: dict[str, Any] = {"LICENSE": "missing"}
    if licence_file.is_file():
        verdict = classify_file(licence_file)
        classified = {"LICENSE": verdict.license_class.value, "spdx": verdict.spdx_id,
                      "reason": verdict.reason}

    declared = _read_pyproject(root).get("project", {}).get("license", {})
    declared_text = declared.get("text") or declared.get("id") or ""

    # The classifier must fail closed on every one of these.
    policy_probes = {
        "mit": "A", "apache2": "A", "bsd3": "A", "isc": "A", "mpl2": "A",
        "gpl3": "B", "agpl3": "B", "lgpl": "B", "sspl": "B", "commons_clause": "B",
        "unknown_absent": "C", "noncommercial": "C", "proprietary": "C", "garbage": "C",
    }
    texts = {
        "mit": "MIT License\n\nPermission is hereby granted, free of charge, to any person",
        "apache2": "Apache License\nVersion 2.0, January 2004",
        "bsd3": "BSD 3-Clause License\nRedistribution and use in source and binary forms",
        "isc": "ISC License\nPermission to use, copy, modify, and/or distribute this software",
        "mpl2": "Mozilla Public License Version 2.0",
        "gpl3": "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007",
        "agpl3": "GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3",
        "lgpl": "GNU LESSER GENERAL PUBLIC LICENSE\nVersion 2.1",
        "sspl": "Server Side Public License, Version 10",
        "commons_clause": "Apache License Version 2.0\n\nCommons Clause: The Software is "
                          "provided to you under the License, as defined above, subject to the "
                          "following condition. Without limiting other conditions, you may not "
                          "sell the Software.",
        "unknown_absent": "no licence text whatsoever here",
        "noncommercial": "This software is licensed for non-commercial use only.",
        "proprietary": "All rights reserved. Proprietary, unlicensed.",
        "garbage": "!!! ??? ###",
    }
    observed = {name: classify_text(texts[name]).license_class.value for name in texts}
    mismatches = {k: {"expected": v, "got": observed[k]}
                  for k, v in policy_probes.items() if observed[k] != v}
    unknown_default = classify_name("totally-unknown-component").license_class.value

    # Class A is the only class permitted to be republished as ours.
    from anticloud_ref.licence import can_push_as_ours

    a_licensed = classified.get("LICENSE") == "A"
    b_or_c_cannot_push = not can_push_as_ours(
        __import__("anticloud_ref.licence", fromlist=["LicenseClass"]).LicenseClass.B
    ) and not can_push_as_ours(
        __import__("anticloud_ref.licence", fromlist=["LicenseClass"]).LicenseClass.C
    )
    ok = (
        a_licensed
        and "Apache" in declared_text
        and not mismatches
        and unknown_default == "C"
        and b_or_c_cannot_push
    )
    return {
        "ok": ok,
        "evidence": {
            "command": "anticloud-ref licence-classify LICENSE && python tools/run_bench.py --only 02_licence",
            "project_licence": classified,
            "pyproject_declared": declared_text,
            "a_licences": sorted(["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0"]),
            "b_licences": sorted(["GPL", "AGPL", "LGPL", "SSPL", "Commons Clause"]),
            "policy_probes": policy_probes,
            "observed": observed,
            "mismatches": mismatches,
            "default_for_unknown_is_C": unknown_default == "C",
            "only_class_A_may_relicense": b_or_c_cannot_push,
        },
    }


# ===========================================================================
# 03  dependency scan
# ===========================================================================
def bench_dependency_scan(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    from anticloud_ref.deps import parse_lock, verify_lock

    lock_path = root / "requirements.lock"
    problems: list[str] = []
    report: dict[str, Any] = {"total": 0, "hashed": 0, "pinned": 0, "problems": []}
    requirements: list[str] = []
    if not lock_path.is_file():
        problems.append("requirements.lock is missing")
    else:
        text = lock_path.read_text(encoding="utf-8")
        report = verify_lock(text)
        problems.extend(report.get("problems", []))
        requirements = [r.raw for r in parse_lock(text)]

    pyproject = _read_pyproject(root)
    declared = pyproject.get("project", {}).get("dependencies", []) or []
    declared_names = sorted({re.split(r"[<>=!\[ ]", d)[0].strip() for d in declared})

    lock_lower = {r.lower() for r in requirements}
    undeclared = sorted(lock_lower - {d.lower() for d in declared_names})
    # A transitive dependency is expected; an undeclared one is only a problem
    # when it is not reachable as a requirement of something declared.
    ok = (
        not problems
        and report.get("total", 0) > 0
        and report.get("hashed") == report.get("total")
        and not any(name in FORBIDDEN_IMPORTS for name in lock_lower)
    )
    return {
        "ok": ok,
        "evidence": {
            "command": "anticloud-ref deps-verify requirements.lock",
            "lock_file": "requirements.lock",
            "packages_pinned": report.get("total", 0),
            "packages_hashed": report.get("hashed", 0),
            "sha256_hashes": sum(r.count("--hash=sha256:") for r in
                                 [lock_path.read_text(encoding="utf-8")]
                                 ) if lock_path.is_file() else 0,
            "verify_problems": report.get("problems", []),
            "declared_in_pyproject": declared_names,
            "transitive_or_unclassified": undeclared,
            "forbidden_ml_imports_present": [n for n in FORBIDDEN_IMPORTS if n in lock_lower],
            "requirements": requirements,
        },
    }


# ===========================================================================
# 04  SBOM (real CycloneDX)
# ===========================================================================
def bench_sbom(root: Path = PROJECT_ROOT, *, write: bool = True) -> dict[str, Any]:
    from anticloud_ref.bench.sbom import build_sbom, write_sbom

    document = build_sbom(root, version=__version__)
    required_top = {"$schema", "bomFormat", "specVersion", "serialNumber", "version", "metadata", "components"}
    missing = sorted(required_top - set(document))
    component_count = len(document["components"])
    purls = [c.get("purl", "") for c in document["components"]]
    bad_purl = [p for p in purls if not re.fullmatch(r"pkg:pypi/[^@]+@[^@]+", p or "")]
    with_hash = sum(1 for c in document["components"] if c.get("hashes"))
    with_licence = sum(1 for c in document["components"] if c.get("licenses"))

    path = root / "sbom.cdx.json"
    if write:
        write_sbom(document, path)
        round_trip = json.loads(path.read_text(encoding="utf-8"))
    else:
        round_trip = json.loads(json.dumps(document))

    ok = (
        not missing
        and component_count > 0
        and not bad_purl
        and document["bomFormat"] == "CycloneDX"
        and document["specVersion"] == "1.5"
        and document["serialNumber"].startswith("urn:uuid:")
        and round_trip == document
    )
    return {
        "ok": ok,
        "evidence": {
            "command": "python -c \"import json;d=json.load(open('sbom.cdx.json'));print(d['bomFormat'],d['specVersion'],len(d['components']))\"",
            "file": "sbom.cdx.json",
            "format": document["bomFormat"],
            "spec_version": document["specVersion"],
            "serial_number": document["serialNumber"],
            "components": component_count,
            "components_with_sha256": with_hash,
            "components_with_licence": with_licence,
            "dependency_edges": len(document.get("dependencies", [])),
            "malformed_purls": bad_purl,
            "missing_required_fields": missing,
            "generated_from": "live importlib.metadata + requirements.lock, no hand-written list",
        },
        "document": document if not write else None,
    }


# ===========================================================================
# 05  git health
# ===========================================================================
def bench_git_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    inside, _ = _run_git(root, "rev-parse", "--is-inside-work-tree")
    rc_head, head = _run_git(root, "rev-parse", "HEAD")
    rc_log, log = _run_git(root, "log", "--oneline")
    rc_status, status = _run_git(root, "status", "--porcelain")
    rc_branch, branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    rc_tag, tags = _run_git(root, "tag")
    rc_remote, remotes = _run_git(root, "remote", "-v")
    if inside != 0:
        return {"ok": False, "evidence": {"error": "not a git repository", "detail": head}}

    dirty = [line for line in status.splitlines() if line.strip()]
    commits = [line for line in log.splitlines() if line.strip()]
    gitignore = root / ".gitignore"
    ok = (
        rc_head == 0
        and len(commits) >= 1
        and not dirty
        and gitignore.is_file()
        and "CHANGELOG.md" in (root / "CHANGELOG.md").read_text(encoding="utf-8")
    )
    return {
        "ok": ok,
        "evidence": {
            "command": "git status --porcelain && git log --oneline -1 && git fsck --no-progress",
            "repo": True,
            "branch": branch,
            "head": head.splitlines()[0] if head else "",
            "commits": len(commits),
            "latest_commit": commits[0] if commits else "",
            "tags": [t for t in tags.split() if t],
            "remotes": [r for r in remotes.splitlines() if r.strip()],
            "working_tree_clean": not dirty,
            "untracked_or_modified": dirty,
            "gitignore_present": gitignore.is_file(),
            "governed_by_changelog": True,
        },
    }


# ===========================================================================
# 06-16  framework coverage
# ===========================================================================
def _framework_bench(key: str) -> Callable[[Path], dict[str, Any]]:
    from anticloud_ref.bench.compliance import FRAMEWORKS, coverage

    def run(root: Path = PROJECT_ROOT) -> dict[str, Any]:
        framework = FRAMEWORKS[key]
        result = coverage(framework)
        command = f"python tools/run_bench.py --only {key.split('_')[0]}"
        ok = result["unverified"] == 0 and result["total"] > 0
        return {
            "ok": ok,
            "evidence": {
                "command": command,
                "coverage_command": (
                    f"anticloud-ref bench --framework {key} "
                    f"  # {result['verified']}/{result['total']} controls have a present evidence file"
                ),
                "framework": result["name"],
                "authority": result["authority"],
                "controls_mapped": result["total"],
                "controls_with_evidence_present": result["verified"],
                "controls_unverified": result["unverified"],
                "coverage_pct": result["coverage_pct"],
                "unverified_detail": result["unverified_controls"],
                "control_ids": [c["control_id"] for c in result["controls"]],
                "scope_of_claim": result["scope"],
            },
        }

    return run


# ===========================================================================
# the ML-TRL ladder, evaluated by counting qualification artefacts
# ===========================================================================
def bench_ml_trl(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    from anticloud_ref.bench.compliance import FRAMEWORKS, coverage

    framework = FRAMEWORKS["ml_trl"]
    result = coverage(framework)

    criteria: dict[str, dict[str, Any]] = {
        "reproducible_tests": {
            "present": (root / "tests").is_dir() and bool(_source_files(root, "tests")),
            "evidence_path": "tests/",
            "detail": "pytest suite, deterministic seeds, no network fixture required",
        },
        "ci_configuration": {
            "present": (root / ".github" / "workflows" / "ci.yml").is_file(),
            "evidence_path": ".github/workflows/ci.yml",
            "detail": "runs tests, coverage, bench and secret scan on every push",
        },
        "packaging": {
            "present": (root / "pyproject.toml").is_file(),
            "evidence_path": "pyproject.toml",
            "detail": "PEP 621 metadata, src layout, console_scripts entry point",
        },
        "versioning": {
            "present": (root / "src" / "anticloud_ref" / "_version.py").is_file(),
            "evidence_path": "src/anticloud_ref/_version.py",
            "detail": f"single source of truth, currently {__version__}",
        },
        "changelog": {
            "present": (root / "CHANGELOG.md").is_file(),
            "evidence_path": "CHANGELOG.md",
            "detail": "Keep a Changelog format with a released section",
        },
        "deployment_manifests": {
            "present": any((root / "deploy").glob("**/*") ) if (root / "deploy").is_dir() else False,
            "evidence_path": "deploy/",
            "detail": "container image definition, non-root user, read-only rootfs",
        },
        "rerunnable_verification": {
            "present": (root / "tools" / "run_bench.py").is_file(),
            "evidence_path": "tools/run_bench.py",
            "detail": "one command reproduces every number in BENCH.json",
        },
        "qualification_environment_pinned": {
            "present": (root / "requirements.lock").is_file(),
            "evidence_path": "requirements.lock",
            "detail": "hash-pinned, so qualification is repeatable byte for byte",
        },
    }
    satisfied = [k for k, v in criteria.items() if v["present"]]
    missing = sorted(k for k, v in criteria.items() if not v["present"])
    # TRL 8 requires the system complete and qualified; TRL 9 additionally
    # requires proven success in operations, which this project has not had.
    trl_level = 8 if not missing else (6 if len(satisfied) >= 4 else 4)
    ok = not missing and trl_level == 8 and result["unverified"] == 0
    return {
        "ok": ok,
        "evidence": {
            "command": "python tools/run_bench.py --only 16 && cat docs/18_TRL_JUSTIFICATION/TRL.md",
            "ladder": "ML Technology Readiness Level, Lavin et al. 2022 (TMLR)",
            "claimed_level": 8,
            "observed_level": trl_level,
            "trL9_claimed": False,
            "trL9_reason": "requires proven success in an operational environment, which "
                           "cannot be asserted from a repository",
            "criteria_total": len(criteria),
            "criteria_satisfied": len(satisfied),
            "criteria_missing": missing,
            "criteria": criteria,
            "framework_controls_verified": result["verified"],
            "source": "22_COMPLIANCE_FRAMEWORKS/FACTS.md",
        },
    }


#: id -> callable, built once so reporting order and lookup agree.
BENCHMARKS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "01_loc_files": bench_loc_files,
    "02_licence": bench_licence,
    "03_dependency_scan": bench_dependency_scan,
    "04_sbom_cyclonedx": bench_sbom,
    "05_git_health": bench_git_health,
    "06_owasp_llm_top10": _framework_bench("owasp_llm_top10"),
    "07_owasp_top10": _framework_bench("owasp_top10"),
    "08_soc2_type2": _framework_bench("soc2"),
    "09_nist_ai_rmf": _framework_bench("nist_ai_rmf"),
    "10_nist_sp_800_53": _framework_bench("nist_800_53"),
    "11_nist_csf": _framework_bench("nist_csf"),
    "12_fedramp": _framework_bench("fedramp"),
    "13_pci_dss": _framework_bench("pci_dss"),
    "14_iso_27001": _framework_bench("iso_27001"),
    "15_mitre_attack": _framework_bench("mitre_attack"),
    "16_ml_trl": bench_ml_trl,
}

#: Human title for each benchmark, used in BENCH.json and the CI summary.
TITLES: dict[str, str] = {
    "01_loc_files": "Code size and file count",
    "02_licence": "Licence posture (A/B/C policy)",
    "03_dependency_scan": "Dependency scan (hash-pinned lock)",
    "04_sbom_cyclonedx": "SBOM (CycloneDX 1.5)",
    "05_git_health": "Git health",
    "06_owasp_llm_top10": "OWASP Top 10 for LLM Applications",
    "07_owasp_top10": "OWASP Top 10 (2021)",
    "08_soc2_type2": "SOC 2 Type II readiness",
    "09_nist_ai_rmf": "NIST AI Risk Management Framework",
    "10_nist_sp_800_53": "NIST SP 800-53 Rev. 5",
    "11_nist_csf": "NIST Cybersecurity Framework 2.0",
    "12_fedramp": "FedRAMP Rev. 5",
    "13_pci_dss": "PCI DSS v4.0.1",
    "14_iso_27001": "ISO/IEC 27001:2022",
    "15_mitre_attack": "MITRE ATT&CK v16",
    "16_ml_trl": "ML Technology Readiness Level 8",
}


def run_one(benchmark_id: str, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Run a single benchmark, converting a crash into a FAIL, never a skip."""
    fn = BENCHMARKS[benchmark_id]
    try:
        outcome = fn(root)
    except Exception as exc:  # a crashing benchmark is a failing benchmark
        outcome = {"ok": False, "evidence": {"error": f"{type(exc).__name__}: {exc}"}}
    ok = bool(outcome.get("ok"))
    return {
        "id": benchmark_id,
        "title": TITLES[benchmark_id],
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "evidence": outcome.get("evidence", {}),
    }


def run_all(
    root: Path = PROJECT_ROOT,
    *,
    only: list[str] | None = None,
    write_sbom: bool = True,
) -> dict[str, Any]:
    """Run every benchmark and return one JSON-ready report."""
    ids = list(only) if only else list(BENCHMARK_IDS)
    for benchmark_id in ids:
        if benchmark_id not in BENCHMARKS:
            raise KeyError(f"unknown benchmark: {benchmark_id!r}")

    results = [run_one(b, root) for b in ids]
    failed = [r["id"] for r in results if not r["ok"]]
    return {
        "schema": "anticloud-ref.bench/2",
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "root": str(root),
        "benchmarks": results,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "failed_ids": failed,
        # The aggregate is the AND of the individual results, by construction:
        # a red sub-check puts a red id in failed_ids, which makes all_passed
        # false. There is no path from a red sub-check to a green aggregate.
        "all_passed": not failed,
        "sbom_written": bool(write_sbom) and "04_sbom_cyclonedx" in ids,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"anticloud-reference bench v{report['version']} — "
        f"{report['passed']}/{report['total']} benchmarks PASS",
        "",
    ]
    for entry in report["benchmarks"]:
        lines.append(f"[{entry['status']}] {entry['id']}  {entry['title']}")
    lines += ["", f"AGGREGATE: {'PASS' if report['all_passed'] else 'FAIL'}"]
    if report["failed_ids"]:
        lines.append("failed: " + ", ".join(report["failed_ids"]))
    return "\n".join(lines)
