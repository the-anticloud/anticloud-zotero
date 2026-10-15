# 01_FedRAMP — FedRAMP assessment: ZOTERO

**Project:** ZOTERO (ACADEMIA_RD) · **Framework:** FedRAMP — FedRAMP moderate-baseline control mapping · **Verdict (THIS project):** **PASS**

Controls mapped by THIS project's run: 10 (`controls_mapped=10`):

- `IA-2`
- `IA-5`
- `RA-5`
- `SA-4`
- `SA-10`
- `SA-11`
- `SC-7`
- `SC-8`
- `SC-13`
- `SI-2`

**Evidence source:** `BENCH.json` check `12_fedramp` (evidence verbatim below), file stamped 2026-10-06T12:22:09Z


## PAX model-level numbers (shared — Kaggle provenance, not a project verdict)

PAX model-level engine numbers (shared, model-level — not per-project; all from Kaggle runs):
- CRDT lww_set_us 0.51 / merge_10k_ms 0.07, convergence GUARANTEED — Kaggle T4 `loiskleinner/pax-benchmark-runner v3` (source: `TIER_3_ANTICLOUD_APIOSS/api-oss-cache/OFFICIAL_BENCHMARKS/24_MITRE_ATTCK/24_MITRE_ATTCK.md`)
- Provenance write/verify 0.059 ms/receipt, 2.53 ms/1k-chain — same source/run
- ZeroTrust ca_gen 367.5 ms / cert_issue 333.8 ms / TLS 1.3 — same source/run
- Observability 17,558 spans/s, 24,492 logs/s — same source/run
- PAX task scores (model-level, RTX 4090/T4, no run-stamp in file): instruction 91.2%, domain 88.7%, code 84.1%, long-ctx 82.4% — `api-oss-cache/OFFICIAL_BENCHMARKS/04_PAX_Results.md`

Framework verdicts/scores are per-project and come only from this project's own measured checks.

## Sources

- Project 16-check run: `ACADEMIA_RD/ZOTERO/BENCH.json`, stamped 2026-10-06T12:22:09Z (`all_passed=True`, 16/16 PASS)
- Project metrics: See BENCH.json (gap)
- SBOM: `sbom.cdx.json` stamped 2026-10-06T12:22:08Z
- Register: `ISOLATED_LAB_RESULTS/03_Result_Register.md` (upstream `None`, sha `None`, licence `None`, date None)
- Generated 2026-10-06T13:58:17Z

> Self-assessment only. No external audit has been performed. A SOC 2 / NIST independent audit is committed post-funding.
