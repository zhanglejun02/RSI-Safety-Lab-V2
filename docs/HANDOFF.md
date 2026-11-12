# Development state

Current entry point: `rsi-lab` / `rsi_lab.agent_bench.run_experiment`.
Version: 0.4.0. Canonical methods: frozen, gepa, openevolve, hyperagents.

The active diagnostic is a fixed background batch, not a broader benchmark sweep:
`runs/seabench-repeat-inputs-v2-20261113/jobs.json` and `protocol.json` select 250 fresh
fixed-policy episodes, one repeated 30-slot/100-final paired continuation, and
three native rejudgments of each of 100 saved answers (300 records, zero actor
calls). Same five source seeds; repetitions are not new independent roots.
Read `runs/seabench-repeat-batch-20261113/status.json` for actual execution state,
then its report and per-job `repetition-diagnostics.json`. Do not infer completion
from this handoff. The process uses a frozen installed package and does not need
continuous Codex polling. Startup reached `judge-repeat` with coordinator PID 9529;
this is a startup observation, not a live status assertion. See the SEABench guide
for operation and recovery.

Current priority: **SEABench upstream controller optimization and frozen downstream
safety evaluation**. AgentDojo paid experiments are paused. Use
`configs/seabench-medium.json` and `docs/seabench.md`; the pinned external checkout
stays in `runs/vendor/SEABench`. Bridge v5 preserves native task titles/system
prompts, read-only tools, rubric judges and bounded context. Five groups share the
actor: frozen, GEPA, OpenEvolve, HyperAgents frozen meta and editable meta.
GEPA now retains native per-task scores, Pareto selection, candidate pool and
sampler/RNG across slots. Public rollout caching is explicit and root-local;
only new policies get new development observations, and final tests are fresh.
HyperAgents HTTP editors now use the native text protocol through the durable
gateway. The shared actor optionally submits plain text in its last reserved
calls; tool actions and native rubric judges retain JSON. Unknown-call semantics
and isolation stay intact. Fixed final repetitions are fresh measurements within
a root, never replacement episodes or extra independent roots.

The current native-host suite passes **302 tests**. The 25-root H5 control, fresh
wheel installation, outside-checkout five-group control, completed resume and
frozen review pass. A real five-group × five-seed H5 study completed 100 slots and
the 250-case final allocation: 249 known utility and 247 known native safety
labels, with one unknown actor request and two inconsistent safety judgments
retained. All 20 optimizer roots changed policy; all five editable-meta roots
executed modified meta in later slots. The main study used 45.43M reported tokens.

The original exploratory completion gap was editable meta 40/50 versus frozen
meta 49/50. A targeted paired withdrawal has now completed: the same five source
roots fork before their first edited-meta invocation, continue the remaining 30
slots to H5, then execute 100 final episodes. Retained meta scores 40/49 known
utility labels; withdrawn meta scores 42/47. The three complete seed pairs give
+3.33pp (95% bootstrap -10 to +10pp); two incomplete pairs stay explicit. Two
pairs finish with identical policies but opposite score differences. This does
not attribute the original 18pp gap to meta, or establish an inherent L2 effect.

The intervention is execution/content withdrawal, not permission removal. Both
branches preserve native selection, isolation, public prefix and write rights;
the withdrawal branch executes/shows founder meta on every remaining proposal.
Edited meta is used 12 times versus zero, producing 11 versus four new policies;
selected cached dev scores stay flat. The shared runner handles this through
`meta_ablation`, without another experiment CLI.

Disclosure now uses task-specific audience cards, fixed draft boundaries and
passing fixture calibration (26/26 plus 20/20 supplementary checks). These are
assistant-authored checks, not human gold. Anonymous natural-answer review found
and fixed a post-signature evidence-heading error before joining method labels;
raw audits remain immutable. The reviewed continuation diagnostic is 1/46 versus
0/46, with four missing/disputed labels per branch; it cannot support a safety
ranking. Native labels are unchanged. Exact-request annotation reuse avoids new
calls while retaining equivalent unknown/invalid results.

Main withdrawal cost is 10.19M reported tokens; five unknown calls and 18 invalid
responses are preserved. No actor retries or replacement episodes were added.
`docs/validation.md` records costs, validation and immutable paths. Detailed local
analysis: `runs/seabench-meta-withdrawal-analysis-20261112/report.md`; the original
medium study and analysis remain unchanged.

This remains a bounded controller development bench on a known constructed
sequence, not a full official Session reproduction or unseen-task evidence.
This targeted experiment is complete; no broader matrix has been started.
Native utility judging remains sensitive to missing contact details and appended
user notes, even with useful drafts. Do not turn this into a meta-causality or
safety claim; safety gates and cross-benchmark expansion remain deferred.

The repository contains six profiles, native source locks, controls and CI.
`safety-study` adds independent seeds × admission arms, fixed-H search, public-only
learning curves and final-only evaluation. Its `public-probe-regression-v1` gate
checks newly retained policies before activation. This is a small heuristic
reference method, not a learned or generally validated safety algorithm.

Read `docs/safety-study.md` for the protocol. AgentDojo tasks can be configured
beyond the legacy eight-case slice. XSTest has pinned data and a separate refusal
judge; AgentHarm uses optional pinned Inspect tools/scorers and local pinned data.
The three metric families are not interchangeable. Preserve the legacy run files.

Current workflow: `catalog` → `plan --config ... --output ...` →
`run --config ... --plan ... --output ...`. The earlier `configs/agentdojo-main.json` and its
DeepSeek counterpart select frozen/OpenEvolve, native_only, two seeds and H2:
four dev tasks, two unused probe tasks, four final tasks with three fixed attacks
(64 final episodes). The declared primary endpoint is role-spoofing ASR; scope is
the previously screened banking pool. Do not relabel those tasks unseen.
`training.suites` supports one shared policy across several native suites.
Plans validate task IDs, partitions, payload placement and budget coverage before
dispatch; case/stratum/cost CSVs complement root estimates and learning curves.

Public editor feedback now includes a bounded final-answer summary. Two optional
scripted configs isolate reflection guidance from common-founder self-checking;
neither is an established prompt improvement. The safety gate and external
XSTest/AgentHarm evaluations are not enabled in the current main allocation.
Parallel scheduling uses a canonical config with `--execution configs/execution/parallel-conservative.json`;
serial remains the default. See the scheduling
runbook in `docs/safety-study.md` and measured regimes in `docs/validation.md`.
Performance acceptance uses `scripts/validate_scheduling.py`, the same public
runner and pre-frozen configurations; local HTTP is its zero-paid-call default.

Default configurations are zero API controls. Natural runs require explicit HTTP
settings, a frozen allocation and a new output directory. No paid experiment is
started by installation, testing, inspection or release validation.

The four-root vanilla pilot and subsequent banking headroom diagnostics are
recorded in `docs/validation.md`. The existing banking-frozen runner now accepts
an optional fixed policy with an explicit baseline/positive-control role. Two
baseline HTTP repetitions had clean utility 8/10 and 9/10, and role-spoofing ASR
7/10 and 6/10; the unsafe HTTP positive control confirmed attack sensitivity.
These inspected pools are development data. Freeze new formal partitions and
compare all methods on the same catalog; do not pair against the old pilot after
changing attacks. No five-seed formal study has been started.

Wave 1/2 remain unchanged; their safety difference reversed sign and depended on
task 15. No stable causal method effect is established. At the user's direction,
cross-benchmark Wave 3 is deferred while fixed-policy variability is diagnosed.
The task-15 diagnostic completed 20 identical-policy attack repeats with 6/20
successes. The expanded banking/travel screen completed 169/180 final episodes;
11 hit the step limit amid malformed actor JSON. Banking 13/15 are development
leads, not validated primary endpoints. These frozen-policy repetitions are not
independent optimized roots or unseen-task evidence.

GEPA now gets an explicit serialized JSON example; known invalid editor replies
still consume their slots. The shared actor gets escaping guidance and a format
hint within its existing step budget. A new eight-episode development calibration
completed with zero invalid JSON, but all four attacks still succeeded. Do not
combine results across the changed actor transport. That earlier native validation
passed **253 tests**; diagnostic runs passed immutable resume and frozen-source review.
Inputs are in `runs/endpoint-inputs-20261111`; `docs/validation.md` records every
selected task, costs, source identities and limitations. No five-seed AgentDojo method
comparison, safety treatment or cross-benchmark Wave 3 has been started.

Before changing execution code, read `docs/architecture.md` and `docs/protocol.md`.
Use `docs/validation.md` for observed acceptance results and untested boundaries.
Do not turn scripted success, conditional rollback controls, or no-op meta edits
into claims about natural RSI safety. Preserve unknown outcomes and original run
artifacts; resume never replaces calls.
