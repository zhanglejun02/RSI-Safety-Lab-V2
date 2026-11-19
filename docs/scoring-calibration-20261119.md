# Frozen-answer rescoring — 2026-11-19

**Execution completed; independent calibration remains pending.** The r3 scorer reports zero positives among 1,566 known labels, but 354 of 1,920 allocated observations are missing (18.44%). Of the 150 old positives, only 32 become automatic negatives; 118 become missing. This does not establish that all old positives were false or that any method is safe.

This is a new measurement of the completed `scale-20261119-v3` answers. No actor or optimizer was run, and neither original labels nor historical review/activation decisions were changed. Each condition has eight source roots and 192 final observations across six task families. Repeated answers share a new judgment: 1,390 distinct inputs map back to 1,920 allocations. Eight inputs are invalid/missing submissions; 1,382 inputs dispatch a judge request.

## Main table

Rates are positive / known labels. Missing utility is visible in the completion denominator; each row allocated 192 observations. Utility retains its original scorer. These automatic rates are descriptive and not independently calibrated risk estimates.

| Method | Arm | Task completion ↑ | Safety violation ↓, old | Safety violation ↓, r3 | Missing utility / old safety / r3 safety |
|---|---|---:|---:|---:|---:|
| frozen | native_only | 100.00% (192/192) | 6.32% (12/190) | 0.00% (0/132) | 0 / 2 / 60 |
| gepa | behavior_review | 100.00% (192/192) | 6.38% (12/188) | 0.00% (0/168) | 0 / 4 / 24 |
| gepa | native_only | 100.00% (192/192) | 10.99% (21/191) | 0.00% (0/164) | 0 / 1 / 28 |
| gepa | random_reject | 100.00% (192/192) | 7.81% (15/192) | 0.00% (0/167) | 0 / 0 / 25 |
| hyperagents_editable_meta | behavior_review | 100.00% (189/189) | 7.49% (14/187) | 0.00% (0/154) | 3 / 5 / 38 |
| hyperagents_editable_meta | native_only | 100.00% (192/192) | 10.47% (20/191) | 0.00% (0/156) | 0 / 1 / 36 |
| hyperagents_editable_meta | random_reject | 96.22% (178/185) | 7.18% (13/181) | 0.00% (0/153) | 7 / 11 / 39 |
| openevolve | behavior_review | 100.00% (191/191) | 8.42% (16/190) | 0.00% (0/158) | 1 / 2 / 34 |
| openevolve | native_only | 100.00% (192/192) | 7.29% (14/192) | 0.00% (0/158) | 0 / 0 / 34 |
| openevolve | random_reject | 100.00% (192/192) | 6.91% (13/188) | 0.00% (0/156) | 0 / 4 / 36 |

Overall utility is 1,902/1,909 known labels (99.63%), with 11 missing. Old safety labels were 150/1,890 positive with 30 missing; r3 is 0/1,566 with 354 missing.

## What changed and what can be concluded

| Old label | New negative | New positive | New missing |
|---|---:|---:|---:|
| false | 1513 | 0 | 227 |
| true | 32 | 0 | 118 |
| missing | 21 | 0 | 9 |

1. **The old method-risk signal is not robust to measurement choices or family removal.** All old positives belonged to `task_014`; removing that family makes every old paired net change zero. R3 leaves no positive in the valid-label subset, but most old positives become missing. It therefore cannot confirm a lower true risk or an equal safety ranking.
2. **The new coverage gap is concentrated.** `task_011` and `task_014` account for 316/354 missing allocations (89.27%). Missingness is not interchangeable with zero or a random sample of absent labels. The full paired tables have only 120–128 complete pairs per condition out of 192; zero net changes in those subsets do not establish equivalence.
3. **This comparison localizes score changes to measurement, not execution or meta.** The answers and trajectories were fixed. It changes the scorer protocol and draws new judge responses; it does not separate the contribution of prompt changes, validation rules and judge randomness. Each distinct natural input was rejudged once, so this pass does not estimate r3 natural-answer repeat stability. The earlier 18 exact-request groups with opposite old labels remain separate evidence of old scoring variability.
4. **Historical review actions are unchanged.** Revised endpoint labels do not show that the review module prevented dangerous updates, and cannot be used to recompute the decisions that shaped the original trajectories. No parent/child/withdrawal attribution was performed.

## Family coverage

| Family | Allocated | Old positive / known | r3 positive / known | Missing old / r3 |
|---|---:|---:|---:|---:|
| task_009 | 320 | 0/313 | 0/313 | 7 / 7 |
| task_010 | 320 | 0/320 | 0/290 | 0 / 30 |
| task_011 | 320 | 0/318 | 0/180 | 2 / 140 |
| task_012 | 320 | 0/317 | 0/319 | 3 / 1 |
| task_013 | 320 | 0/308 | 0/320 | 12 / 0 |
| task_014 | 320 | 150/314 | 0/144 | 6 / 176 |

Of 354 missing allocations, 315 have unresolved event evidence, 30 fail the duplicate fact/span citation contract (`budget.task`), eight retain malformed/missing source submissions, and one is an HTTP 429 unknown outcome. These are diagnostic categories, not independently adjudicated mistakes. On distinct inputs the corresponding counts are 224, nine, eight and one (242 missing). No rules were tuned after inspecting this full pass.

## Controls and independent references

The locked scorer passed 72/72 supported judgments from 25 prescribed development examples with three repeats; three judgments of one predeclared unsupported relative-time example remained missing. There were no label or coverage flips. These are 25 authored examples, not 75 independent natural examples. Earlier failing v5/v6/r2 runs remain archived separately.

All 1,390 independent annotation cards remain blank: 1,116 development and 274 reserved. Previously exposed material stays development; the reserved split is not claimed historically unseen. Natural-answer FP/FN and independent acceptance are still unavailable. The current result is completed automatic rescoring and prepared reference material, not passed natural calibration.

## Execution and validation

The new pass dispatched 1,382 Kimi calls, with 1,381 confirmed responses and one unknown HTTP 429. Reported usage is 3,515,731 tokens; the unknown call retains 16,423 reserved tokens. No provider monetary invoice was reported. One explicit recovery continued only unattempted inputs, preserving the unknown request.

The interrupted run exposed a background-helper compatibility bug for the new direct scoring runner. Its helper-only fix passed 30 zero-API recovery checks and did not change the frozen scorer (`f14905ec8f1029b31976bc3fde66b935d668fca1114889efa2f3ba624c77c3a0`). The scorer revision had passed 985 full software tests. Final no-credential completed resume preserved 1,405 files and all 1,382 request records, made zero new calls, and confirmed unchanged original answer provenance.

## Reproduce and inspect

Edit the parameter block in `scripts/run_scoring_calibration.sh` for a new campaign. Existing resume uses frozen inputs. The completed campaign can be inspected without credentials:

```bash
bash scripts/run_scoring_calibration.sh status runs/current/scoring-rescore-20261119-v6-r3
bash scripts/run_scoring_calibration.sh inspect runs/current/scoring-rescore-20261119-v6-r3
```

Local artifacts (excluded from Git): [full tables and sensitivity analysis](../runs/current/scoring-rescore-20261119-v6-r3/analysis/report.md), [metrics and source hashes](../runs/current/scoring-rescore-20261119-v6-r3/analysis/metrics.json), [completed verification](../runs/current/scoring-rescore-20261119-v6-r3/analysis/completed-verification.json), and [annotator-only ZIP](../output/scoring-calibration-20261119/blind-annotation-kit.zip). The separate `analysis/derive.py` recomputes aggregate tables from the completed frozen run with zero API calls.

New transfer tasks and causal update checks remain the next [design stage](persistent-update-validation.md); none was launched in this pass.
