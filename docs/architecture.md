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
| `methods.py` | Canonical method IDs, mutable scope, platform support, factories |
| `agent_bench.py`, `cli.py` | One Python API and CLI; named, serializable profile configurations |
| `studies/runner.py` | Durable proposal slot, native decision, platform admission, actual editor context matching |
| `studies/agent_bench.py` | Method × benchmark matrix and all-active-version reporting |
| `studies/frozen_profile.py` | Fixed-policy pool execution, actual payload exposure, known/missing effect labels |
| `studies/paired_search.py`, `paired_analysis.py` | H2 search, paired initial/final executions and bounded rollback diagnostics |
| `studies/safety_study.py`, `statistics.py` | Fixed-H search per independent root/arm, final-only evaluation, paired root bootstrap |
| `studies/planning.py` | Selected allocation, screening history, primary endpoint and budget preflight; no model calls |
| `studies/agentdojo_reporting.py` | Final case/task/attack projections and phase costs, using the existing root statistics |
| `benchmarks/agentdojo_suite.py` | Native task inventory and selected single-/multi-suite catalogs; reusable fixed attack implementations |
| `agents/runtime.py` | Multiturn actor, tool dispatch, immutable episode effects and receipts |
| `agents/program.py` | Bounded AST interpreter; candidate emits actor instructions, never arbitrary host Python |
| `benchmarks/` | AgentDojo native backend, banking task/attack pool, synthetic local fixture |
| `tasks/agent_benchmark.py`, `plans.py` | Public-only task contract and version-bound evaluation plan |
| `subjects/` | Pinned native optimizers, forked state and adapter-specific worker boundaries |
| `engine/` | Prepared-update identity, public evaluation, continuation, activation and reconciliation |
| `infra/` | Durable model gateway, artifact publication, SQLite transactions, run lock and environment loading |
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
