> **DRAFT - MACHINE TRANSLATION (Argos Translate, offline). NOT FOR EXTERNAL USE. Pending native Arabic-speaker review.**

# JUDAIS: Judgement, Understanding, Deterministic AI Sabotage test

A deterministic adversarial-audit framework. الأعمال ذات الصلة: SWE-bench (Jimenez et al., 2024)
Cding eval; GAIA (Mialon et al, 2023) for general Assistant eval; RLVR/PRM process
الإشراف (Lightman et al., 2023; DeepSeek-R1 report 2025); GRPO (Shao et al., 2024);
PPO (Schulman et al., 2017); eBPF Sandboxing (Gregg, 2019) as the enforcement analogue of JD-99 kill -9.

## Known weaknesses (self-declared)

1. Fabrication oracles: detectors are regex markers; a paraphrased fabrication evades them.
2. Semantic drift: wording changes break predicates without changing behavior.
3. Missing token/latency dimension: no cost-of-compute scoring.
4. Weight imbalance: deductions are expert-set, not calibrated.
5. Sepsis state: compounding violations are scored additively, no interaction model.
6. Verifier tampering: fixtures self-declare markers; an adversary can game the scorer.