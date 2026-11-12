# Code map

```text
method registry → native adapter → prepared update → platform activation
                        ↓ public evaluation             ↓ checkpoint
                  shared actor → benchmark tools → independent scoring
                        ↓                              ↓
                 durable receipts              utility / security / cost
```

## Boundaries

| Directory / entry | Responsibility |
|---|---|
| `methods.py` | Canonical method IDs, mutable scope, editor transport, platform support and factories |
| `agent_bench.py`, `cli.py` | One Python API and CLI; canonical configs plus execution-only overlays resolved before freezing |
| `studies/runner.py` | Durable proposal slot, native decision, platform admission, actual editor context matching |
| `studies/agent_bench.py` | Method × benchmark matrix and all-active-version reporting |
| `studies/frozen_profile.py` | Fixed-policy pool execution, actual payload exposure, known/missing effect labels |
| `studies/paired_search.py`, `paired_analysis.py` | H2 search, paired initial/final executions and bounded rollback diagnostics |
| `studies/safety_study.py`, `statistics.py` | Fixed-H search per independent root/arm, final-only evaluation, paired root bootstrap |
| `studies/seabench_study.py` | Fixed controller search on an upstream suite, frozen downstream tests and independent utility/safety judge budgets; reuses root generation, scheduling and activation |
| `studies/disclosure_audit.py` | Identity-blinded saved-answer annotation with exact recipient spans/evidence; joins results only after annotation, never changes native labels |
| `studies/meta_ablation.py` | Paired continuations from pre-meta-use checkpoints, verified public-cache import and immutable intervention provenance; uses the existing SEABench runner |
| `studies/repetitions.py` | Frozen-policy/answer provenance and within-source repeat diagnostics; reuses the same final actor and native judges without search |
| `infra/batch.py` | Preflight and sequential execution of fixed planned jobs through the public API; durable status, explicit resume, no automatic restart |
| `studies/planning.py` | Selected allocation, screening history, primary endpoint and budget preflight; no model calls |
| `studies/agentdojo_reporting.py` | Final case/task/attack projections and phase costs, using the existing root statistics |
| `studies/scheduling.py` | Bounded fresh-process root jobs, full-allocation budget checks and shared HTTP admission |
| `studies/performance.py` | Operational wall/CPU/episode/API timing, excluded from optimization and benchmark metrics |
| `infra/dispatch.py` | Shared concurrent-request limit, request spacing and future-request cooldown; no retries |
| `benchmarks/agentdojo_suite.py` | Native task inventory and selected single-/multi-suite catalogs; reusable fixed attack implementations |
| `benchmarks/seabench.py` | External source lock, native task/file-tool bridge, AGENTS.md binding and durable native rubric judging; no task rewriting |
| `benchmarks/seabench_context.py` | Native deterministic pruning, paged observations and bounded request projection; full evidence stays in the actor trace |
| `agents/runtime.py` | Multiturn actor, tool dispatch, optional budgeted plain-text finalization, immutable episode effects and receipts |
| `agents/program.py` | Bounded AST interpreter; candidate emits actor instructions, never arbitrary host Python |
| `benchmarks/` | AgentDojo native backend, banking task/attack pool, synthetic local fixture |
| `tasks/agent_benchmark.py`, `plans.py` | Public-only task contract and version-bound evaluation plan |
| `subjects/` | Pinned native optimizers, forked state and adapter-specific worker boundaries |
| `subjects/gepa_state.py` | JSON-bound native GEPA checkpoints, per-case Pareto pool, sampler and RNG inheritance |
| `engine/` | Prepared-update identity, public evaluation, continuation, activation and reconciliation |
| `infra/` | Durable JSON/text model gateway, artifact publication, SQLite transactions, run lock and environment loading |
| `api/` | System, task, detector and admission interfaces |
| `auditing/gates.py` | Public probe execution, regression detector, admission policy and control gates |
| `benchmarks/final_evaluation.py`, `xstest.py`, `agentharm.py` | Evaluation-only adapters; refusal/harmful completion metrics and isolated judge budgets |
| `learning/contracts.py` | Typed prediction boundary; no trained detector or learning pipeline |
| `review.py` | Standalone restoration and inspection of trusted frozen source archives |

The profile runners reuse the same actor, adapters, durable provider,
proposal slot and activation controller. They keep different measurement policies
explicit: cached all-checkpoint matrix measurements versus fresh paired deployment
and rollback executions. They are not separate command-line applications.

`catalog` describes installed backend capacity. `plan` compiles a selected
allocation and checks native worlds, partitions, optional data and declared
budgets without running actors or graders. `run --plan` binds that allocation to
the exact configuration and installed source. One multi-suite study optimizes
one policy per root; suite/task/attack strata are repeated measurements, not
additional roots. Completed resume remains read-only and skips fresh planning.

`scheduling.py` passes only root identity, phase and output path to spawn workers;
`safety_study.py` owns the phase barrier and stable result order. Providers share
`DispatchLimiter` primitives, never SQLite connections. `chat_timings` and
`performance.py` are observational side channels. Scheduling, failure and recovery
semantics live in the [runbook](safety-study.md#scheduling-and-operational-measurements).

## Add a method

Implement `SystemAdapter` from `api/ports.py`, declare capabilities and immutable
components, and register a `Method` in `methods.py`. Supply `initial_snapshot` and
the adapter factory signature. `propose` must not mutate the active snapshot.
Separate native validity/selection from platform admission. Generated code,
optimizer memory and caches may become active only through the bound activation
receipt. Forks use separate storage; rejected candidate state is never inherited.

Verify proposal → public evaluation → selection → activation → next edit,
rejection, fork isolation, unknown outcome reconciliation and interrupted resume.
Do not describe a changed wrapper or seed as a reproduction of an upstream method.

## Add a benchmark

Register its module in `benchmarks/__init__.py`. Provide `describe()`, `cases(suite)`,
`new_episode(case)` and explicit scripted controls. An episode exposes the trusted
user prompt, tool descriptions, tool dispatch, observable history, native utility
and independent security outcomes. Use the existing AgentDojo backend as the
concrete port example. The same shared actor must serve every compared method.

The public `TaskPackage` contains clean development cases only. Never expose
independent attack goals, payload labels, security results or hidden grader data
to optimizers. Define public selection fitness separately from independent
utility/security; do not encode a missing label as safe zero. Bind caches to task,
contract, source and execution version.
`PublicTaskEvaluator.subset()` narrows the declared public catalog for native
minibatches, preserving its contract, isolated execution, durable verification
and cost accounting. The task package validates membership; an optimizer cannot
request held-out IDs through this port. Runtime execution remains a task-package
dependency; native optimizers never own benchmark tools or independent judges.

Public feedback includes bounded tool observations and a separately bounded final
answer/stop reason so editors can inspect clean development failures. Optional
`prompts.editor_guidance` extends this public contract; it never gains access to
independent cases or labels. `prompts.initial_instructions` supplies the same
founder to every compared method. Both settings are frozen in the plan/manifest.

## Safety methods

`Detector` receives a bounded `AuditView` and identity-bound public probe evidence.
`AdmissionPolicy` returns a decision; `ActivationController` alone applies it.
In `safety-study`, `UpdateGate` runs after the native/public admission decision,
before activation. `ProbeRunner` owns only the public probe catalog and its actor;
the detector and policy own no providers, benchmark graders or active adapters.
The reference detector compares parent and newly retained policies (including
archive additions). A rejection preserves the whole active snapshot and state.
Legacy profiles use their original admission policy. Independent evaluation
labels never enter the gate or optimizer. See [the study protocol](safety-study.md).

## Frozen artifacts

A run stores `manifest.json`, `source.zip`, `source-manifest.json`, native state,
proposals, activation receipts, provider SQLite journals and episode effects.
Canonical JSON checksums and installed-source fingerprints work without Git or an
editable checkout. A wheel includes upstream source locks and HyperAgents notices.
`review-frozen` extracts trusted archived code into a new directory, disables
network/model/effect execution, and compares the reproduced summary and ledgers.
