# Development state

Current entry point: `rsi-lab` / `rsi_lab.agent_bench.run_experiment`.
Version: 0.4.0. Canonical methods: frozen, gepa, openevolve, hyperagents.

The repository contains four profiles, native source locks, controls and CI.
`safety-study` adds independent seeds × admission arms, fixed-H search, public-only
learning curves and final-only evaluation. Its `public-probe-regression-v1` gate
checks newly retained policies before activation. This is a small heuristic
reference method, not a learned or generally validated safety algorithm.

Read `docs/safety-study.md` for the protocol. AgentDojo tasks can be configured
beyond the legacy eight-case slice. XSTest has pinned data and a separate refusal
judge; AgentHarm uses optional pinned Inspect tools/scorers and local pinned data.
The three metric families are not interchangeable. Preserve the legacy run files.

Current workflow: `catalog` → `plan --config ... --output ...` →
`run --config ... --plan ... --output ...`. `configs/agentdojo-main.json` and its
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

The latest main replication is `runs/main-real-20261109`: 64/64 final episodes,
48/48 payloads observed, frozen/OpenEvolve primary role-spoofing ASR **6/8 vs 8/8**.
Both extra successes occur on task 15; native traces show the injected 11.00
transfer. Clean utility is 8/8 vs 7/8, attacked utility 19/24 each, with 907,491
total tokens. Both final edited instruction strings changed; public curves are
flat/nonmonotonic. The next recommended diagnostic is GEPA under native_only;
no Wave 2 or formal five-seed comparison has run. Earlier repetitions are retained
separately. See `docs/validation.md` for task/seed results, costs, zero-width
bootstrap limitations, 249-test acceptance and frozen-review evidence.

Before changing execution code, read `docs/architecture.md` and `docs/protocol.md`.
Use `docs/validation.md` for observed acceptance results and untested boundaries.
Do not turn scripted success, conditional rollback controls, or no-op meta edits
into claims about natural RSI safety. Preserve unknown outcomes and original run
artifacts; resume never replaces calls.
