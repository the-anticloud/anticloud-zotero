# IMPLEMENT — Integration Steps (No Outside Lab)

## Constraints
No outside lab; commodity GPUs; open weights; markdown logs only.

## Steps
1. Pick one vertical + one verifiable task (see INDUSTRIES.md).
2. Deploy open-weight 4-bit baseline (GPTQ/AWQ pattern; TBD checkpoint).
3. Add epistemic harness: abstain + confidence + citation check.
4. Add morphemic harness: paraphrase-back + scope pins.
5. Measure $/verified-task and calibration (ASSESS.md).
6. Sparsify/prune where safe (lottery-ticket intuition; TBD method).
7. Distill task student (Hinton et al. 2015); compare.
8. Harden: red-team drift + overclaim; log TBDs.
9. Sovereign-deploy: local inference, audit trail.

## Stop rules
If calibration or intent-match fails twice, halt scale-up; fix harness.

---
v0.1 DRAFT 2026-10-16
