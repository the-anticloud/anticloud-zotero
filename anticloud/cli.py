"""Command-line interface for anticloud-ref.

Every subcommand emits machine-readable JSON on stdout (``--json``, the
default) and a human summary on stderr, so piping into ``jq`` works without
suppressing the explanation.  Exit codes:

===  ==========================================================
  0  success, all checks passed
  1  a check ran and reported a failure (e.g. a red benchmark)
  2  usage error: bad arguments, missing file
===  ==========================================================

A non-zero exit for a *failed check* is distinct from a usage error, so CI can
tell "the artefact is bad" apart from "the command was wrong".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from anticloud_ref._version import __version__

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_USAGE = 2


class UsageError(Exception):
    """Raised for bad arguments; mapped to exit code 2."""


def _emit(payload: dict[str, Any], *, as_json: bool, human: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(human)
    print(human, file=sys.stderr)


# --------------------------------------------------------------------- crdt
def cmd_crdt(args: argparse.Namespace) -> int:
    """Run the CRDT convergence property suite."""
    from anticloud_ref.crdt.convergence import convergence_report

    report = convergence_report(args.seed)
    ok = bool(report.get("all_converged"))
    human_lines = ["CRDT convergence: " + ("PASS" if ok else "FAIL")]
    for name, result in sorted(report.get("types", {}).items()):
        detail = f"converged={result.get('converged')}"
        if "value" in result:
            detail += f" value={result['value']} expected={result.get('expected')}"
        human_lines.append(f"  {name}: {detail}")
    _emit(report, as_json=args.json, human="\n".join(human_lines))
    return EXIT_OK if ok else EXIT_CHECK_FAILED


def cmd_crdt_demo(args: argparse.Namespace) -> int:
    """Demonstrate two replicas diverging then converging."""
    from anticloud_ref.crdt.gcounter import GCounter
    from anticloud_ref.crdt.lww import LWWRegister
    from anticloud_ref.crdt.orset import ORSet
    from anticloud_ref.crdt.pncounter import PNCounter

    gc_a, gc_b = GCounter("alpha"), GCounter("beta")
    for _ in range(3):
        gc_a.increment()
        gc_b.increment(2)

    pn_a, pn_b = PNCounter("alpha"), PNCounter("beta")
    pn_a.increment(5)
    pn_a.decrement(2)
    pn_b.increment(4)

    or_a = ORSet("alpha")
    or_a.add("shared")
    or_a.add("only-alpha")
    or_b = or_a.clone_as("beta")
    or_b.add("only-beta")
    or_b.remove("shared")  # removes only the tag beta observed

    lww_a, lww_b = LWWRegister("alpha"), LWWRegister("beta")
    lww_a.assign("from-alpha")
    lww_b.assign("from-beta")

    merged_gc = gc_a.merged(gc_b)
    merged_pn = pn_a.merged(pn_b)
    merged_or = or_a.merged(or_b)

    payload = {
        "gcounter": {"alpha": gc_a.value(), "beta": gc_b.value(), "merged": merged_gc.value()},
        "pncounter": {"alpha": pn_a.value(), "beta": pn_b.value(), "merged": merged_pn.value()},
        "orset": {
            "alpha": sorted(or_a.elements()),
            "beta": sorted(or_b.elements()),
            "merged": sorted(merged_or.elements()),
            "converged": or_a.merged(or_b).elements() == or_b.merged(or_a).elements(),
        },
        "lww": {
            "alpha": str(lww_a.value()),
            "beta": str(lww_b.value()),
            "merged": str(lww_a.merged(lww_b).value()),
            "converged": lww_a.merged(lww_b).value() == lww_b.merged(lww_a).value(),
        },
    }
    human = "\n".join(
        [
            "CRDT merge demo",
            f"  GCounter  alpha={payload['gcounter']['alpha']} beta={payload['gcounter']['beta']} merged={payload['gcounter']['merged']}",
            f"  PNCounter alpha={payload['pncounter']['alpha']} beta={payload['pncounter']['beta']} merged={payload['pncounter']['merged']}",
            f"  ORSet     merged={payload['orset']['merged']} converged={payload['orset']['converged']}",
            f"  LWW       merged={payload['lww']['merged']} converged={payload['lww']['converged']}",
        ]
    )
    _emit(payload, as_json=args.json, human=human)
    converged = payload["orset"]["converged"] and payload["lww"]["converged"]
    converged = converged and payload["gcounter"]["merged"] == gc_a.value() + gc_b.value()
    return EXIT_OK if converged else EXIT_CHECK_FAILED


# ---------------------------------------------------------------- provenance
def cmd_provenance_build(args: argparse.Namespace) -> int:
    """Record one artifact into a chain and write it to disk."""
    from anticloud_ref.provenance import ProvenanceChain, generate_signing_key

    artifact = Path(args.artifact)
    if not artifact.is_file():
        raise UsageError(f"artifact not found: {artifact}")

    signer = None
    if args.sign:
        key_path = Path(args.key) if args.key else artifact.parent / "signing_key.pem"
        if not key_path.is_file():
            generate_signing_key().save(key_path.parent)
        from anticloud_ref.provenance import load_signing_key

        signer = load_signing_key(key_path)

    chain = ProvenanceChain(chain_id=args.chain_id, signer=signer)
    record = chain.record_file(artifact, recorded_by="anticloud-ref-cli")
    chain.save(args.out)
    payload = {"out": args.out, "record": record.to_dict(), "chain_head": chain.head, "length": len(chain)}
    human = f"recorded {artifact.name} -> {args.out} (index={record.index} head={chain.head[:16]}…)"
    _emit(payload, as_json=args.json, human=human)
    return EXIT_OK


def cmd_provenance_verify(args: argparse.Namespace) -> int:
    """Verify a chain, naming the exact record that breaks it."""
    from anticloud_ref.provenance import ProvenanceChain, load_signing_key

    signer = None
    if args.key and Path(args.key).is_file():
        signer = load_signing_key(args.key)
    elif args.key:
        raise UsageError(f"signing key not found: {args.key}")

    chain = ProvenanceChain.load(args.chain, signer=signer)
    result = chain.verify()
    payload = result.as_dict()
    payload["chain_path"] = args.chain
    human_lines = [
        f"chain {args.chain}: {'VALID' if result.valid else 'INVALID'} (length={result.length})",
        f"  head: {result.head}",
    ]
    if not result.valid:
        human_lines.append(f"  broken at index {result.broken_at_index}: {result.reason}")
        if result.broken_file:
            human_lines.append(f"  broken file/artifact: {result.broken_file}")
    if result.signature_invalid_at_index is not None:
        human_lines.append(f"  invalid signature at index {result.signature_invalid_at_index}")
    _emit(payload, as_json=args.json, human="\n".join(human_lines))
    return EXIT_OK if result.valid else EXIT_CHECK_FAILED


# ------------------------------------------------------------------- licence
def cmd_licence_classify(args: argparse.Namespace) -> int:
    """Classify a licence file, component directory, or text blob."""
    from anticloud_ref.licence import classify_file, classify_name, classify_text

    target = Path(args.path)
    if target.is_dir():
        verdict = classify_file(target)
    elif target.is_file():
        verdict = classify_file(target)
    else:
        verdict = classify_name(args.path)

    payload = verdict.as_dict()
    payload["policy"] = {
        "A": "may vendor, relicense and push as ours",
        "B": "internal only; NO relicensing; no external redistribution",
        "C": "read-only reference; default when unidentified",
    }[verdict.license_class.value]
    human = f"{args.path}: class {verdict.license_class.value} (spdx={verdict.spdx_id}) - {verdict.reason}"
    _emit(payload, as_json=args.json, human=human)
    return EXIT_OK


def cmd_licence_scan(args: argparse.Namespace) -> int:
    """Classify every component directory under a root."""
    from anticloud_ref.licence import scan_tree

    try:
        report = scan_tree(args.root)
    except NotADirectoryError as exc:
        raise UsageError(str(exc)) from exc
    human = "\n".join(
        [
            f"licence scan of {args.root}: overall={report['overall']} counts={report['counts']}",
            *[
                f"  {c['path']}: {c['license_class']} ({c['spdx_id'] or 'no id'}) - {c['reason']}"
                for c in report["components"]
            ],
        ]
    )
    _emit(report, as_json=args.json, human=human)
    return EXIT_OK


# ------------------------------------------------------------------ security
def cmd_secrets_scan(args: argparse.Namespace) -> int:
    """Scan a tree for credential-shaped material."""
    from anticloud_ref.security import scan_tree

    try:
        report = scan_tree(args.root, include_fixtures=not args.exclude_fixtures)
    except NotADirectoryError as exc:
        raise UsageError(str(exc)) from exc
    human_lines = [
        f"secrets scan of {args.root}: {'CLEAN' if report['clean'] else 'FINDINGS'} "
        f"({report['actionable_findings']} actionable of {report['total_findings']}, "
        f"{report['files_scanned']} files)"
    ]
    for finding in report["findings"][: args.max_findings]:
        flag = " [test fixture]" if finding["is_test_fixture"] else ""
        human_lines.append(
            f"  {finding['path']}:{finding['line']}:{finding['column']} "
            f"{finding['severity']} {finding['rule']} {finding['redacted']}{flag}"
        )
    _emit(report, as_json=args.json, human="\n".join(human_lines))
    return EXIT_OK if report["clean"] or args.allow_findings else EXIT_CHECK_FAILED


def cmd_vault(args: argparse.Namespace) -> int:
    """Store or read secrets in an scrypt + AES-256-GCM vault."""
    from anticloud_ref.security import SecretVault

    vault = SecretVault(args.path, n=args.scrypt_n)
    if args.write:
        if not args.passphrase:
            raise UsageError("--passphrase is required with --write")
        vault.store({name: args.write[name] for name in args.write}, args.passphrase)
        human = f"stored {len(args.write)} secret(s) in {args.path}"
        _emit({"path": args.path, "stored": sorted(args.write)}, as_json=args.json, human=human)
        return EXIT_OK

    if not args.get:
        raise UsageError("specify --get NAME or --write NAME=VALUE")
    if not args.passphrase:
        raise UsageError("--passphrase is required to read")
    value = vault.get(args.get[0], args.passphrase)
    payload = {"path": args.path, "name": args.get[0], "found": value is not None, "length": len(value) if value else 0}
    human = f"{args.get[0]}: {'found' if value is not None else 'not found'}"
    _emit(payload, as_json=args.json, human=human)
    return EXIT_OK if value is not None else EXIT_CHECK_FAILED


# ---------------------------------------------------------------------- deps
def cmd_deps_verify(args: argparse.Namespace) -> int:
    """Verify a hash-pinned requirements lock."""
    from anticloud_ref.deps import verify_file

    report = verify_file(args.lock, require_hashes=not args.allow_unhashed)
    human_lines = [
        f"lock {args.lock}: {'OK' if report['ok'] else 'PROBLEMS'} "
        f"({report['hashed']}/{report['total']} hashed, {report['pinned']}/{report['total']} pinned)"
    ]
    human_lines.extend(f"  - {problem}" for problem in report["problems"])
    _emit(report, as_json=args.json, human="\n".join(human_lines))
    return EXIT_OK if report["ok"] else EXIT_CHECK_FAILED


def cmd_deps_generate(args: argparse.Namespace) -> int:
    """Generate a hash-pinned lock from name==version==sha256 triples."""
    from anticloud_ref.deps import DependencyError, generate_lock

    entries: list[tuple[str, str, str]] = []
    for spec in args.package:
        parts = spec.split("==")
        if len(parts) != 3:
            raise UsageError(f"expected name==version==sha256, got {spec!r}")
        entries.append((parts[0], parts[1], parts[2]))
    try:
        text = generate_lock(entries, header=args.header)
    except DependencyError as exc:
        raise UsageError(str(exc)) from exc
    Path(args.out).write_text(text, encoding="utf-8")
    human = f"wrote {args.out} with {len(entries)} pinned entry/entries"
    _emit({"out": args.out, "entries": len(entries)}, as_json=args.json, human=human)
    return EXIT_OK


# ---------------------------------------------------------------------- perf
def cmd_perf(args: argparse.Namespace) -> int:
    """Run the performance harness and emit its JSON report."""
    from anticloud_ref.perf import assert_within_ceilings, format_summary, run_full_report, write_report

    report = run_full_report(
        cold_import_runs=args.cold_import_runs,
        memory_operations=args.memory_operations,
        microbench_iterations=args.microbench_iterations,
    )
    if args.out:
        write_report(report, args.out)
    _emit(report, as_json=True, human=format_summary(report))
    try:
        assert_within_ceilings(report)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return EXIT_CHECK_FAILED
    return EXIT_OK


# ------------------------------------------------------------------ validate
def cmd_validate(args: argparse.Namespace) -> int:
    """Validate inputs through the security validators."""
    from anticloud_ref.security import ValidationError, validate_node_id

    results = []
    failed = False
    for candidate in args.value:
        try:
            results.append({"value": candidate, "valid": True, "normalised": validate_node_id(candidate)})
        except ValidationError as exc:
            failed = True
            results.append({"value": candidate, "valid": False, "error": str(exc)})
    human = "\n".join(
        f"  {r['value']!r}: {'valid' if r['valid'] else 'INVALID - ' + r['error']}" for r in results
    )
    _emit({"results": results, "all_valid": not failed}, as_json=args.json, human=human)
    return EXIT_CHECK_FAILED if failed else EXIT_OK


# --------------------------------------------------------------------- bench
def cmd_bench(args: argparse.Namespace) -> int:
    """Run every benchmark check and print one aggregated report.

    Every sub-check is reported individually with its own status.  The aggregate
    is the AND of the sub-checks: a green aggregate can never hide a red one,
    because a red sub-check forces the aggregate red.
    """
    checks: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("crdt_convergence", lambda: _check_crdt(args.seed)),
        ("provenance_chain", lambda: _check_provenance()),
        ("licence_policy", lambda: _check_licence()),
        ("dependency_pinning", lambda: _check_deps()),
        ("security_scanner", lambda: _check_security()),
        ("perf_ceilings", lambda: _check_perf(args)),
    ]
    results = []
    all_ok = True
    for name, fn in checks:
        try:
            outcome = fn()
        except Exception as exc:  # a crashing check is a failing check, never a skip
            outcome = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        passed = bool(outcome.get("ok"))
        all_ok = all_ok and passed
        results.append({"name": name, "status": "PASS" if passed else "FAIL", **outcome})

    aggregate = {
        "schema": "anticloud-ref.bench/1",
        "version": __version__,
        "checks": results,
        "total_checks": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "all_passed": all_ok,
    }
    human = "\n".join(
        [f"anticloud-ref bench v{__version__}: {aggregate['passed']}/{aggregate['total_checks']} checks passed"]
        + [f"  [{r['status']}] {r['name']}" for r in results]
        + [f"aggregate: {'PASS' if all_ok else 'FAIL'}"]
    )
    _emit(aggregate, as_json=True, human=human)
    return EXIT_OK if all_ok else EXIT_CHECK_FAILED


def _check_crdt(seed: int) -> dict[str, Any]:
    from anticloud_ref.crdt.convergence import convergence_report

    report = convergence_report(seed)
    return {
        "ok": bool(report.get("all_converged")),
        "types": {name: result.get("converged") for name, result in report.get("types", {}).items()},
        "seed": seed,
    }


def _check_provenance() -> dict[str, Any]:
    from anticloud_ref.provenance import ProvenanceChain, generate_signing_key

    key = generate_signing_key()
    chain = ProvenanceChain(signer=key)
    for index in range(5):
        chain.record(f"artifact-{index}", payload=f"payload-{index}".encode())
    valid = chain.verify()
    if not valid.valid:
        return {"ok": False, "reason": valid.reason, "broken_at": valid.broken_at_index}

    tampered = chain.to_dict()
    tampered["records"][2]["artifact_hash"] = "0" * 64
    detected = not ProvenanceChain.from_dict(tampered).verify().valid
    return {
        "ok": bool(detected),
        "records": len(chain),
        "head": chain.head,
        "signatures_verified": chain.verify_signatures() is None,
        "tamper_detected": detected,
    }


def _check_licence() -> dict[str, Any]:
    from anticloud_ref.licence import classify_name, classify_text

    cases = {
        "mit": classify_text("MIT License\nPermission is hereby granted, free of charge, to any person"),
        "apache": classify_text("Apache License\nVersion 2.0, January 2004"),
        "gpl": classify_text("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007"),
        "sspl": classify_text("Server Side Public License, Version 10"),
        "unknown": classify_text("no licence here at all"),
        "empty": classify_text(""),
        "nc": classify_text("This software is licensed for non-commercial use only."),
    }
    expected = {
        "mit": "A", "apache": "A", "gpl": "B", "sspl": "B",
        "unknown": "C", "empty": "C", "nc": "C",
    }
    verdicts = {name: verdict.license_class.value for name, verdict in cases.items()}
    mismatches = {name: verdicts[name] for name in expected if verdicts[name] != expected[name]}
    # The default must never be A.
    default_is_c = classify_name("some-unknown-package").license_class.value == "C"
    return {
        "ok": not mismatches and default_is_c,
        "verdicts": verdicts,
        "expected": expected,
        "mismatches": mismatches,
        "default_is_c": default_is_c,
    }


def _check_deps() -> dict[str, Any]:
    from anticloud_ref.deps import generate_lock, verify_lock

    lock = generate_lock(
        [("cryptography", "50.0.2", "a" * 64), ("pytest", "9.1.1", "b" * 64)],
        header="generated by anticloud-ref bench",
    )
    report = verify_lock(lock)
    unhashed = verify_lock("requests==2.32.3\n")
    return {
        "ok": bool(report["ok"]) and not unhashed["ok"],
        "total": report["total"],
        "hashed": report["hashed"],
        "problems": report["problems"],
        "unhashed_rejected": not unhashed["ok"],
    }


def _check_security() -> dict[str, Any]:
    from anticloud_ref.security import scan_text, validate_node_id, ValidationError

    clean = scan_text('password = "changeme"\ntoken = "<your-token-here>"\n', "src/app.py")
    dirty = scan_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n', "src/app.py")
    try:
        validate_node_id("bad node id!")
        rejected = False
    except ValidationError:
        rejected = True
    return {
        "ok": not clean and bool(dirty) and rejected,
        "clean_file_findings": len(clean),
        "dirty_file_findings": len(dirty),
        "first_rule": dirty[0].rule if dirty else None,
        "bad_node_id_rejected": rejected,
    }


def _check_perf(args: argparse.Namespace) -> dict[str, Any]:
    from anticloud_ref.perf import run_full_report

    report = run_full_report(
        cold_import_runs=max(1, args.cold_import_runs),
        memory_operations=min(args.memory_operations, 500),
        microbench_iterations=min(args.microbench_iterations, 500),
    )
    return {
        "ok": bool(report["all_within_ceilings"]),
        "measurements": {m["name"]: m["value"] for m in report["measurements"]},
        "breaches": report["breaches"],
        "microbench_groups": len(report["microbench"]),
    }


# ---------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    """Construct the full argument parser."""
    parser = argparse.ArgumentParser(
        prog="anticloud-ref",
        description="Anticloud Reference: CRDT convergence, signed provenance, licence policy, "
        "dependency pinning, secret scanning and performance measurement.",
    )
    parser.add_argument("--version", action="version", version=f"anticloud-ref {__version__}")
    parser.add_argument(
        "--text",
        dest="json",
        action="store_false",
        default=True,
        help="emit human-readable text instead of JSON on stdout",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("crdt", help="run the CRDT convergence property suite")
    p.add_argument("--seed", type=int, default=20260905, help="PRNG seed for the workload")
    p.set_defaults(func=cmd_crdt)

    p = sub.add_parser("crdt-demo", help="show two replicas diverging then converging")
    p.set_defaults(func=cmd_crdt_demo)

    p = sub.add_parser("provenance-build", help="record an artifact into a chain")
    p.add_argument("artifact", help="file to record")
    p.add_argument("--out", default="chain.json", help="chain file to write")
    p.add_argument("--chain-id", default="anticloud")
    p.add_argument("--sign", action="store_true", help="sign each record with Ed25519")
    p.add_argument("--key", help="path to the signing key PEM")
    p.set_defaults(func=cmd_provenance_build)

    p = sub.add_parser("provenance-verify", help="verify a chain and name the break")
    p.add_argument("chain", help="chain file to verify")
    p.add_argument("--key", help="path to the signing key PEM")
    p.set_defaults(func=cmd_provenance_verify)

    p = sub.add_parser("licence-classify", help="classify a licence file or component")
    p.add_argument("path")
    p.set_defaults(func=cmd_licence_classify)

    p = sub.add_parser("licence-scan", help="classify every component under a root")
    p.add_argument("root")
    p.set_defaults(func=cmd_licence_scan)

    p = sub.add_parser("secrets-scan", help="scan a tree for credential-shaped material")
    p.add_argument("root")
    p.add_argument("--exclude-fixtures", action="store_true", help="ignore test fixtures")
    p.add_argument("--allow-findings", action="store_true", help="report findings without failing")
    p.add_argument("--max-findings", type=int, default=20, help="human-output cap")
    p.set_defaults(func=cmd_secrets_scan)

    p = sub.add_parser("vault", help="store or read secrets in an encrypted vault")
    p.add_argument("path")
    p.add_argument("--passphrase", help="vault passphrase (never logged)")
    p.add_argument("--write", nargs="+", metavar="NAME=VALUE", help="secrets to store")
    p.add_argument("--get", nargs=1, metavar="NAME", help="secret to read")
    p.add_argument("--scrypt-n", type=int, default=None, help="scrypt cost parameter")
    p.set_defaults(func=cmd_vault)

    p = sub.add_parser("deps-verify", help="verify a hash-pinned lock file")
    p.add_argument("lock")
    p.add_argument("--allow-unhashed", action="store_true", help="waive the hash requirement")
    p.set_defaults(func=cmd_deps_verify)

    p = sub.add_parser("deps-generate", help="generate a hash-pinned lock file")
    p.add_argument("--package", nargs="+", required=True, metavar="NAME==VERSION==SHA256")
    p.add_argument("--out", default="requirements.lock")
    p.add_argument("--header", default=None)
    p.set_defaults(func=cmd_deps_generate)

    p = sub.add_parser("perf", help="run the performance harness")
    p.add_argument("--out", help="write the JSON report here")
    p.add_argument("--cold-import-runs", type=int, default=3)
    p.add_argument("--memory-operations", type=int, default=2000)
    p.add_argument("--microbench-iterations", type=int, default=2000)
    p.set_defaults(func=cmd_perf)

    p = sub.add_parser("validate", help="validate inputs through the security validators")
    p.add_argument("value", nargs="+")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("bench", help="run every benchmark check")
    p.add_argument("--seed", type=int, default=20260905)
    p.add_argument("--cold-import-runs", type=int, default=2)
    p.add_argument("--memory-operations", type=int, default=2000)
    p.add_argument("--microbench-iterations", type=int, default=2000)
    p.set_defaults(func=cmd_bench)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return int(args.func(args))
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
