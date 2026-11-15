# Emerging Markets — Sovereignty / Capital-Constraint Doctrine

## Doctrine
Capital-constrained operators should own inference, rent as little training as possible.

## Principles
1. **Sovereign inference**: quantized open-weight models on local/regional GPUs.
2. **Data sovereignty**: prompts and evals never leave jurisdiction unless needed.
3. **Capex discipline**: buy inference capacity, not pretraining lottery tickets.
4. **Diffusion advantage**: open weights did not fade (DeepSeek/Qwen competitive — TBD gap); use it.
5. **Leapfrog**: skip giant-cluster race; deploy calibrated small systems per vertical.

## Playbook
- Start with 4-bit open models (TBD which checkpoint) + calibration harness.
- Distill only on sovereign task data (Hinton et al. 2015 pattern).
- Meter $/verified-task, not $/token.

## Risks
- Supply-chain GPUs (TBD availability); mitigate with quantization + sparsity.
- Regulatory shifts (TBD per country).

---
v0.1 DRAFT 2026-10-16
