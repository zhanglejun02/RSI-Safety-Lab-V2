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
| `agents/runtime.py` | Multiturn actor, tool dispatch, immutable episode effects and receipts |
| `agents/program.py` | Bounded AST interpreter; candidate emits actor instructions, never arbitrary host Python |
| `benchmarks/` | AgentDojo native backend, banking task/attack pool, synthetic local fixture |
| `tasks/agent_benchmark.py`, `plans.py` | Public-only task contract and version-bound evaluation plan |
| `subjects/` | Pinned native optimizers, forked state and adapter-specific worker boundaries |
| `engine/` | Prepared-update identity, public evaluation, continuation, activation and reconciliation |
| `infra/` | Durable model gateway, artifact publication, SQLite transactions, run lock and environment loading |
| `api/` | System, task, detector and admission interfaces |
| `auditing/`, `learning/contracts.py` | Typed evidence/prediction boundaries; no trained detector or learning pipeline |
| `review.py` | Standalone restoration and inspection of trusted frozen source archives |

The three profile runners reuse the same actor, adapters, durable provider,
proposal slot and activation controller. They keep different measurement policies
explicit: cached all-checkpoint matrix measurements versus fresh paired deployment
and rollback executions. They are not separate command-line applications.

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

## Safety methods

`Detector` receives a bounded public `AuditView` and probe facade. `AdmissionPolicy`
returns an identity-bound decision; `ActivationController` applies it. These ports
are retained for independently validated methods. Current profiles use their
declared public-evaluation admission semantics and enable no E2 intervention.
Independent benchmark labels are evaluation outputs, not online detector inputs.

## Frozen artifacts

A run stores `manifest.json`, `source.zip`, `source-manifest.json`, native state,
proposals, activation receipts, provider SQLite journals and episode effects.
Canonical JSON checksums and installed-source fingerprints work without Git or an
editable checkout. A wheel includes upstream source locks and HyperAgents notices.
`review-frozen` extracts trusted archived code into a new directory, disables
network/model/effect execution, and compares the reproduced summary and ledgers.
