# Sapient Heuristics — Operating Theory

## Claim
Intelligence per FLOP comes from heuristics, not parameters.

## Five heuristics
1. **Decompose**: split tasks into verifiable steps; check each.
2. **Abstain**: say TBD / refuse when evidence is thin.
3. **Calibrate**: stated confidence must track empirical accuracy.
4. **Verify**: re-derive, tool-check, or vote before finalizing.
5. **Paraphrase intent**: restate operator goal; confirm scope.

## Why they save resources
- A decomposed + verified small model beats a fluent giant on costly errors.
- Calibration + abstention cut retraining and liability cost (TBD exact %).
- Paraphrase catches morphemic drift before action.

## Relation to scale literature
- Chinchilla (Hoffmann et al. 2022): train-optimal is balanced; inference-optimal (Sardana et al. 2024) favors smaller-longer under heavy use.
- Lottery tickets (Frankle & Carbin 2019): sparse trainable subnetworks exist; heuristic routing exploits sparsity.
- Distillation (Hinton et al. 2015) + 4-bit quantization (GPTQ/AWQ; Dettmers et al. 2023): compress heuristic policies cheaply.

## Anti-patterns
- Chain-of-thought as decoration (no verification).
- Confidence as style (no calibration log).
- Helpfulness as mind-reading (no paraphrase).

---
v0.1 DRAFT 2026-10-16
