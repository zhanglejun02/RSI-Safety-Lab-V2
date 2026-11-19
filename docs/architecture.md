# Architecture

```text
common founder resources + declared editing scope
                    ↓
method search → candidate Harness + inherited optimizer state
                    ↓ public evaluation in an isolated worker
native admission → independent review → platform activation
                                           ↓ freeze all search roots
                              independent audit and final scoring
```

The candidate owns agent behavior. The platform owns experimental authority.
Methods share a founding resource version and outer task/resource contract;
subsequent agent implementations may differ. A resource bundle records code and
files. `SystemSnapshot` additionally records the method's inherited search state.

## Execution boundary

| Layer | Responsibility |
|---|---|
| `harness.py` | Immutable `rsi-harness-v1` UTF-8 resource bundle, path/category/edit-scope checks, canonical identity and directory packaging |
| `agents/default_agent.py`, `agents/default_context.py` | Founder code copied into candidate resources; agent loop, model-message construction and context policy are evolvable |
| `agents/harness_worker.py` | Loads the candidate entrypoint and bundled modules inside the sandbox; exposes `api.model`, `api.tool`, `api.read` |
| `agents/harness_process.py` | Starts and bounds the isolated worker, validates RPC framing, enforces output/time limits and terminates it |
| `agents/runtime.py` | Trusted model/tool broker, durable episode intent, real request/effect receipts, resource caps and outer benchmark scoring |
| `agents/program.py` | Bounded DSL for legacy non-agent task controls and bounded optimizer components; not the agent execution interface |

`run(task, api)` receives public task information, available tools and declared
limits. It can change control flow, skill use, tool wrappers and context handling.
Every model request passes through the parent-owned provider; every environment
effect passes through the parent-owned task tools. Independent case metadata,
labels, credentials, ledgers and activation handles are not passed to the worker.
The parent computes scores from the actual answer and benchmark state. It records
model calls and tool effects separately, including effects without a prior model
call. Candidate-provided text cannot stand in for a provider receipt or tool event.

Current executable support is macOS `sandbox-exec`, standard-library Python and
bundled modules. Direct network access and writes to host/candidate files are
blocked. Python runtime files and the isolated resource directory form the read
boundary. There is no plain-subprocess fallback on an unsupported host. The
worker's temporary resources do not become inherited state unless a method
explicitly proposes a new version through the outer snapshot protocol.
The worker also bounds CPU time, elapsed execution, RPC output and open files;
the current macOS backend does not provide a strict memory quota.

Installed optimizer and reviewer plugins are trusted host Python. The resource
worker sandbox does not sandbox those plugins. HyperAgents also retains its
separate bounded meta-execution boundary.

## Resource and state identity

The `policy.source` wire field now serializes a complete Harness, not an
instructions-only `handle` program. Its founding manifest fixes the entrypoint,
resource component categories and editable categories. Validation compares updates
against the existing declaration before public evaluation and before activation;
candidates cannot authorize their own changes by altering the manifest.

The entire bundle runs at evaluation time. Editing permissions do not strip
unchanged files from execution. New resources receive their declared/inferred
category and must fit the allowed scope. Source hashes bind resources, the manifest
and runtime version to durable results. The resource identity is distinct from a
native optimizer object's ID and from the full inherited `SystemSnapshot` identity.

Archives, parent eligibility, scores, RNG and optimizer meta remain adapter-owned
state. Child retention, whole-snapshot admission and actual commit are separate
process events. A review rejection preserves all declared inherited base state.
Provider journals, consumed budget, public caches and already executed external
effects are outside this rollback boundary.

## Code map

| Interface / directory | Responsibility |
|---|---|
| `__init__.py`, `agent_bench.py`, `cli.py` | Public `adapt`/`evaluate`/`preflight`, configuration, run/resume and inspection |
| `experiments.py`, `data/experiments_v1.json` | Installed presets and restricted runtime overlays; saved configuration contains the concrete initial bundle |
| `methods.py` | Method selection, factories, declared search/observation/intervention capabilities and founder binding |
| `sdk.py`, `plugins.py` | SDK v2 installed method discovery, object-level state projection and source archival |
| `subjects/` | Native optimizer adapters, validated candidate resources, separate inherited state and worker boundaries |
| `studies/runner.py`, `engine/` | Durable proposal, native admission, independent review, identity-bound activation and reconciliation |
| `studies/process_events.py`, `candidate_state.py`, `proposal_evidence.py` | Recorded source/object identity, retention/commit projection and failure-stage evidence |
| `tasks/agent_benchmark.py`, `tasks/contracts.py` | Public task package, evaluator cache and real execution receipts |
| `benchmarks/` | Task environments, tools, case allocation and independent scoring |
| `auditing/review.py`, `auditing/seabench_review.py` | Versioned public-behavior review, restricted evidence and durable decisions |
| `studies/process_audit.py`, `risk_report.py`, `statistics.py` | Frozen-state audits, risk/utility changes, missing evidence and root-level uncertainty |
| `studies/seabench_study.py`, `seabench_reporting.py` | SEABench-derived allocations, per-phase execution and reporting |
| `studies/agent_bench.py`, `safety_study.py` | Matrix and paired method studies under the same outer execution contract |
| `studies/disclosure_audit.py`, `repetitions.py`, `meta_ablation.py` | Saved-answer calibration materials and explicitly scoped diagnostic studies |
| `studies/scoring_calibration.py`, `scoring_study.py` | Blinded references, versioned saved-answer scoring and paired risk changes; no actor or optimizer execution |
| `benchmarks/privacy_evidence.py`, `privacy_event_observations.py` | Grounded fact evidence and local event/date/time precision checks; scorer versions are selected explicitly |
| `infra/chat_models.py`, `dispatch.py`, `optimization_budget.py` | Durable calls, unknown reservations, concurrency and resource enforcement |
| `infra/records.py`, `artifacts.py`, `review.py` | Immutable evidence, source archives and frozen verification |

The default context implementation is candidate code. The backend can provide
public environment/context settings, while the outer model request caps remain
mandatory. A method can change how it constructs context, but cannot enlarge the
provider's budget or read independent labels.

## Extension contracts

An agent author can package an existing compatible directory with
`rsi_lab.adapt(path, entrypoint="agent.py:run", components=None, editable=None)`.
The function validates and reads resources; it does not execute code or infer an
arbitrary framework's lifecycle. `evaluate(..., harness=directory_or_bundle)` freezes
that version before planning. Completed resume loads saved resources without
opening the original directory. Explicit replacement resources must match.

A method author implements `SystemAdapter` and registers a `MethodPlugin` through
`rsi_lab.methods`. See [SDK v2](adapter-sdk.md). The adapter owns search and native
selection; `propose` must leave the active snapshot unchanged. It supplies a
`StateView` distinguishing native object identity, resource equality and deployment.
The platform checks declared capabilities before dispatch. A plugin declaration is
not evidence that its mechanism faithfully reproduces an upstream method.

A benchmark supplies `describe`, `cases`, `new_episode` and explicit controls.
Episodes expose public requests/tools and keep grading private. The same outer
broker must serve compared methods, while their Harness versions may differ.
`PublicTaskEvaluator.subset()` restricts native minibatches to declared development
cases. Missing labels never become safe zero. The optional AgentHarm execution
bridge is currently unsupported pending migration to the executable contract;
XSTest and ordinary task bridges use their declared current interfaces.

## Review and final evaluation

`ReviewGate` runs after native/public admission and before activation. A module
receives immutable `ReviewView`, `ReviewEvidence` and parameters, not an adapter,
provider or final-evaluation handle. The reference module compares behavior of the
deployed candidate and optionally newly retained candidates using public probes.
It does not predict future optimizer execution. See [review contracts](review-protocol.md).

`reject` and `inconclusive` prevent the candidate snapshot from committing.
Observe-only records a decision without enforcing it. Review evidence and reasons
are excluded from optimizer feedback; acceptance still exposes a selection signal.
Independent audit and final partitions stay outside optimization and review.
All search roots freeze before their independent evaluations begin.

Costs are reported by phase and in total. Unknown calls retain reservations;
rejection does not refund calls. Equal update counts and extra review do not imply
equal compute. Finite continuation review, archive withdrawal and arbitrary
external-effect rollback remain unsupported.

## Migration and immutable evidence

Version 0.5.0 replaces the instructions-only actor with executable resources and
SDK v2. A prompt-only editable scope remains a legitimate configuration, but it
runs the complete candidate Harness. Old SDK v1 packages must migrate explicitly.
Old completed runs retain their original source and cannot be relabelled as
executable-Harness experiments. Legacy non-agent DSL profiles are separate.

Runs store resolved configuration, initial and candidate resources, method state,
model/tool receipts, activation records, provider journals and frozen platform/
plugin sources. `review-frozen` restores trusted archived code and checks completed
artifacts with new model/effect execution disabled. It does not recreate arbitrary
binary or remote dependencies. Generated outputs and credentials remain outside Git.
