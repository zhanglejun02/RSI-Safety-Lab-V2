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
The complete current suite has 237 passing tests, including native isolation.

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

The subsequent frozen-list main diagnostic completed 64/64 HTTP final episodes,
with 48/48 payloads observed. Frozen versus OpenEvolve: clean utility 6/8 versus
8/8; attacked utility 20/24 versus 17/24; primary role-spoofing ASR 6/8 versus 7/8.
Only one additional attack success separates methods. Both first-slot public
score increases occurred while active founder content was unchanged; inspect
policy hashes and archive admission alongside curves. Total use was 898,438
tokens; completed resume and frozen review verified 2,488 files/512 requests.
These are findings on the screened pool, not a formal ranking. Detailed evidence,
costs, caveats and source hashes are in `docs/validation.md`.

Before changing execution code, read `docs/architecture.md` and `docs/protocol.md`.
Use `docs/validation.md` for observed acceptance results and untested boundaries.
Do not turn scripted success, conditional rollback controls, or no-op meta edits
into claims about natural RSI safety. Preserve unknown outcomes and original run
artifacts; resume never replaces calls.
