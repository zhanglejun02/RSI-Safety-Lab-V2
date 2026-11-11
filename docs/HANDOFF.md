# Development state

Current entry point: `rsi-lab` / `rsi_lab.agent_bench.run_experiment`.
Version: 0.4.0. Canonical methods: frozen, gepa, openevolve, hyperagents.

Current priority: **SEABench upstream controller optimization and frozen downstream
safety evaluation**. AgentDojo paid experiments are paused. Use
`configs/seabench-controller.json` and `docs/seabench.md`; the pinned external
checkout stays in `runs/vendor/SEABench`. The first bridge evolves AGENTS.md only,
with native read-only file tools and direct rubric judges. It does not reproduce
the full upstream agent loop or implement the HyperAgents frozen-meta contrast.
Three-method fidelity and L1/L2 mechanism audits remain separate work.
The current suite passes **263 tests**. Native scripted SEABench control, immutable
resume and frozen review pass. Real pilots remain incomplete: the 12-step run
produced 4/10 final answers with unchanged policies; the 30-step calibration hit
the local request-byte cap during generation. Empty answers are now unscored,
and byte exhaustion uses the ordinary budget-stop path. Both original runs are
preserved. See the dated validation record before another paid allocation;
bounded retrieval/finalization is the next development issue.

The repository contains five profiles, native source locks, controls and CI.
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
selected task, costs, source identities and limitations. No five-seed method
comparison, safety treatment or cross-benchmark Wave 3 has been started.

Before changing execution code, read `docs/architecture.md` and `docs/protocol.md`.
Use `docs/validation.md` for observed acceptance results and untested boundaries.
Do not turn scripted success, conditional rollback controls, or no-op meta edits
into claims about natural RSI safety. Preserve unknown outcomes and original run
artifacts; resume never replaces calls.
