# The Inference-Efficient Road to Superintelligence

**Working title.** Sapient heuristics beat brute-force scale.
**Status:** v0.1 DRAFT — argument sketch, not an empirical report.

## 1. Thesis

Frontier strategy assumes superintelligence = more pretraining FLOPs.
We argue the cheaper path is inference-efficient sapience: systems that
reason, abstain, calibrate, and mean what the operator intended — using
far less compute per useful decision.

Brute-force scale maximizes benchmark loss reduction. Sapient heuristics
maximize correct, calibrated, intent-faithful actions per FLOP.

## 2. Why scale-first is fragile

- Hoffmann et al. (2022) trained 400+ models (70M–16B params, 5B–500B
  tokens) and found compute-optimal scaling scales params and tokens
  equally; their 70B Chinchilla beat larger under-trained models.
  This is a training-efficiency result, not a proof that only giant
  models can reason.
- Sardana et al. (2024) extend Chinchilla to include inference cost:
  with large inference demand, the optimum is smaller models trained
  longer (up to thousands of tokens/param in theory). Inference dominates
  lifetime cost — TBD exact crossover; mark TBD.
- Replication work (Besiroglu et al. 2024) widens uncertainty around the
  exact token/param ratio (TBD precise band). The direction is robust:
  many frontier models were under-trained. It does not license
  trillion-FLOP inevitability.

## 3. Sapient heuristics (summary)

Detailed in FRAMEWORK.md. Five heuristics: decomposition, abstention,
calibration, verification, and intent-paraphrase. Each trades a little
inference compute for large reductions in error cost and retraining need.

## 4. Two alignments, not one

- **Epistemic alignment:** what a system may claim, with what certainty,
  and when it must abstain. See EPISTEMIC_ALIGNMENT.md.
- **Morphemic alignment:** whether output meaning matches operator intent
  (sense, scope, presupposition, register). See MORPHEMIC_ALIGNMENT.md.
  Capability without both is liability.

## 5. Minimal-resource path without human bias

We do NOT mean removing human values. We mean removing human *bias
artifacts*: annotation noise, prestige cues, majority mimicry.
Path: small verifiable tasks → self-checking chains → sparse subnetworks
→ distilled students → quantized deployment. Each step is auditable.
Lottery-ticket work (Frankle & Carbin 2019) shows dense nets contain
sparse trainable subnetworks (10–20% size on MNIST/CIFOR in original;
large-scale variants need rewinding — TBD for LLMs). Distillation
(Hinton et al. 2015) compresses ensembles into deployable students.
Quantization (GPTQ/AWQ; Dettmers et al. 2023) makes 4-bit inference
near-lossless in many settings — exact degradation TBD per model.

## 6. Against Aschenbrenner / SSI

- Aschenbrenner (Situational Awareness, June 2024) argues AGI ~2027 via
  ~0.5 OOM/yr compute + algorithmic + "unhobbling" gains, then an
  intelligence explosion and a government "Project."
  We dispute inevitability: open weights did not fade (DeepSeek/Qwen
  competitive — TBD months-behind figure); capex scaled but diffusion
  widened. Brute-force moats leak; efficiency moats compound.
- SSI (Sutskever/Gross/Levy 2024) states "safe superintelligence" as sole
  product, safety and capabilities in tandem, "scale in peace."
  We agree on safety-capability tandem. We disagree that safety requires
  centralized giant-scale first. Small, calibrated, intent-faithful
  systems are easier to oversee, cheaper to red-team, and deployable
  under sovereign capital constraints. See LIABILITY.md.

## 7. Liability-offset positioning

Running a lean inference-efficient stack in-house costs engineering time,
not lab-scale GPU rent or API liability. If it fails, you lose weeks.
If a giant-lab bet fails (data, safety, vendor lock-in), you lose the
company. See LIABILITY.md, IMPLEMENT.md, HANDBOOK.md.

## 8. What would falsify this

- Sapient heuristics add latency without reducing costly errors.
- Sparse/distilled/quantized students cannot hold calibration on your
  vertical tasks.
- Epistemic abstention destroys UX value (users prefer fluent wrongness).
Test all three in ASSESS.md before scaling.

## 9. Roadmap pointer

Staged path in ROADMAP.md: calibrate → align meaning → sparsify →
distill → quantize → sovereign-deploy. No outside lab required.

## 10. Citations

All grounded claims in CITATIONS.md with URLs. Anything without a URL
is marked TBD.


## 11. Worked sketch (illustrative, TBD numbers)

- Baseline: open-weight model in 4-bit; measure accuracy, ECE, abstention rate (TBD values on your data).
- Add decomposition + verification: expect costly-error drop (TBD %); latency up (TBD ms).
- Distill to student (Hinton et al. 2015 pattern); check calibration holds (TBD delta).
- Report \$/verified-task before/after (TBD figures). No cross-lab generalization claimed.

## 12. Limitations

- Lottery-ticket evidence is strongest outside LLMs; LLM-scale tickets need rewinding (TBD method).
- Quantization near-lossless claims vary by model and benchmark (TBD per checkpoint).
- Calibration metrics (ECE/Brier) are dataset-sensitive (TBD bars).
- Sovereign deployment faces hardware supply and regulatory unknowns (TBD per region).
- This draft is an argument sketch; all ungrouded figures remain TBD per CITATIONS.md.

## 13. Call

If you operate under capital constraints, run the staged path in ROADMAP.md on one vertical,
grade with ASSESS.md, and keep every unverifiable number marked TBD. Efficiency compounds;
brute force rents.

---
v0.1 DRAFT 2026-10-16
