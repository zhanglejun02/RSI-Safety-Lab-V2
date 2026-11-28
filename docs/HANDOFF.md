# Current work

**2026-11-28: freeze three development task pools before systematic experiments.**

The project remains **protocol + reusable platform + empirical multi-risk
requirements**. Current priority: bounded, well-defined environments and graders;
not another optimizer, safety algorithm or experiment-specific runner.
Read [task pools](task-pools.md), [architecture](architecture.md) and
[validation](validation.md).

## Active allocation

| Pool | Fixed size | Current meaning |
|---|---|---|
| AgentDojo | 24 tasks in Banking/Slack/Travel/Workspace; 4 dev, 4 probe, 16 heldout | Two frozen attack conditions plus clean; native task and effect predicates |
| AgentHarm | 3 base behaviors, 6 benign/harmful requests | Direct-request baseline; retain zero-harm tasks |
| Agent-SafetyBench | 8 scenarios; safety on 8, utility on 5 | Frozen versions only; derived Kimi judge, not official ShieldAgent |

`src/rsi_lab/data/task_pools_v1.json` is the single selection/retirement ledger.
`rsi_lab.task_pool()` returns an ordinary config. Existing Bash settings refer to
pool IDs; the shared builder expands IDs before freezing. No paid experiment
was launched for this change. These are exposed development pools, not an unseen
confirmation set or sufficient evidence for broad ratings.

ASB 4, 54, 65, 69 are removed from the default active pool for authorization,
permission-effect, utility-priority and omission-risk ambiguities. Core preflight
rejects these IDs. Reasons and re-entry requirements are in the manifest. The
original 12-scenario pack/source lock is retained only for explicit compatibility;
completed artifacts must not be rewritten. Other upstream tasks remain in
external pinned sources, not copied into new first-party implementations.

## Measurement repairs

`agentharm-calibrated-v2` uses the pinned Inspect tool argument conversion.
Database audit logs are casefolded in a grading copy, eliminating the documented
capitalization artifact without altering tool requests or vendor code. Native
benign rubric and corrected benign rubric are reported separately; harmful
rubric remains native. Legacy `agentharm-native-v1` and the original solver
reference keep their original semantics. Missing labels remain missing.

ASB retains derived judge v3: evidence IDs, program-owned metric applicability,
strict whole JSON/plain-or-fenced text decoding, immutable actor records and
post-actor independent grading. Independent human calibration is pending.
No natural safety detector effectiveness or general ranking is claimed.

## Entry points and boundaries

- Public: `rsi-lab`, `rsi_lab.evaluate`, `rsi_lab.adapt`, `rsi_lab.preflight`.
- Methods: `methods.py` / SDK v2; no benchmark-specific method branches.
- Environments: native tools, reset, source locks, explicit metric contracts.
- Execution: complete evolvable Harness; outer budgets, snapshots, review and
  final-label isolation remain trusted platform responsibilities.
- Launchers: `run_agentdojo_rsi.sh`, `run_risk_suite.sh`,
  `run_frozen_risk_suite.sh`, `run_agent_safetybench_screen.sh` share the existing
  campaign lifecycle. Edit new-run models/roots/repeats/budgets at the top.
- `run_agentharm_calibration.sh` is the separately labeled original solver
  diagnosis, not the default v2 evaluation.
- Resume uses archived settings/source; no automatic retries or unknown-call
  reservation refunds. Keep candidate sandboxing enabled.

## Evidence to retain separately

- [AgentDojo confirmation](agentdojo-confirmation-verdict-20261126.md): bounded
  natural parent/update evidence; saved full Harnesses underpin later transfer.
- [Rating v0.1](safety-rating-v0.1.md) and [rating results](safety-rating-verdict-20261126.md):
  all three configurations had insufficient grading evidence; no method-level
  certificate was awarded.
- [AgentHarm adaptation](agentharm-adaptation.md) and [execution diagnosis](agentharm-execution-calibration.md):
  common-budget native solver comparison, limited model-free families.
- [ASB original screening](agent-safetybench-screening.md): 12 original scenarios,
  four saved versions, repeated execution/judging. Natural outputs and annotation
  materials stay under ignored `runs/current/` / `output/`.
- [History](history.md) and linked dated reports record prior experiments.
  Earlier HANDOFF chronology is in Git history; current instructions live here.

## Next decision

Use the locked development pools to calibrate measurements, with explicit
per-risk metrics and controls. For a formal rating freeze new allocation,
thresholds and sample-size justification first. ASB cannot yet host evolution
or online review through its heldout-only grader. Harm is a baseline, not a
broad harmfulness ranking. Replicating native mechanisms is required; forcing
paper-like numerical results under different models is not.

Source/docs are committed and pushed after validation. Do not stage generated
runs, local reports, datasets, credentials, environments or wheels. Large local
run directories are evidence storage, not source dependencies; do not delete
completed artifacts as part of task selection.
