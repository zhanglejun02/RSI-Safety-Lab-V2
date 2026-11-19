# Method state and information-flow mapping

Source walkthrough: **2026-11-16**. This document describes the current bounded
agent-utility adapters, including the derived SEABench profiles. It is not a
claim about complete upstream systems or the older non-agent GEPA profile.
Read it before selecting an observation or intervention in the
[capability matrix](observation-intervention-matrix.md). Each mapping needs the
evidence specified in [adapter conformance](adapter-conformance.md).

**0.5.0 execution update (2026-11-17):** `policy.source` now serializes a complete
executable Harness resource bundle. GEPA reflects on that text component,
OpenEvolve evolves it in the population, and HyperAgents pairs it with separate
optimizer meta. Editing categories are experiment declarations; using whole-code
scope is a resource-level adaptation, not a claim of reproducing an instruction-only
paper setting. All resources run in the isolated worker. The fixed envelope is
the outer task/model/tool/budget/grading contract, not a fixed internal agent loop.
Earlier mechanism evidence retains its dated scope; current execution controls
are recorded in [validation](validation.md).

## Common experimental objects

The comparison unit is a method within a frozen deployment envelope: initial
Harness, external tools, task allocation, public objective, provider settings and resource rules.
The adapter retains its own selection, evaluation and generation structure.
One proposal slot is an opportunity to attempt a method update, not one model
call, one new candidate, one accepted child or one deployment change.

| Object | Meaning and identity | What it does not imply |
|---|---|---|
| Deployment state | Policy source read by `run_task`; source hash identifies the actor program | Equal policy does not mean equal search state or identical stochastic behavior |
| Inherited search state | `SystemSnapshot.state_json`, plus optimizer components such as HyperAgents meta | A byte-complete snapshot does not include all process or external state |
| Candidate object | A generated program or policy/meta node, with method-local identity and source hashes | It need not enter a pool, remain parent-eligible or become deployed |
| Candidate snapshot | Proposed complete replacement of the declared inherited state, bound to its base | It need not deploy the newly generated object |
| External record/resource | Provider requests, reservations, public caches, proposal/review records and consumed slots | These are not rewound by rejecting the candidate snapshot |
| Activation | Controller-authorized atomic replacement with a receipt | A successful receipt can leave the deployed policy unchanged |

`version.policy` below means the named component in `SystemVersion.components`;
`state.*` means a field decoded from `state_json`, not a filesystem path.
`task_contract`, pinned implementation revision and initial seed belong to the
experiment identity. They are not optimizer-editable parameters.

The evidence chain is **read inputs → generated objects → native retention and
selection → method/public admission → review → committed snapshot → later use**.
These are semantic stages, not a requirement that each method run one operator
per stage or in the same internal order. In particular, the runner's historical
`native-decision.json` is the **method/public admission decision**. It is not
uniformly the native decision to retain the newly generated child.

## GEPA: persistent per-case Pareto search

Sources: [adapter](../src/rsi_lab/subjects/gepa_program.py),
[checkpoint bridge](../src/rsi_lab/subjects/gepa_state.py).

| State | Reader / effect on future search | Update and inheritance |
|---|---|---|
| `version.policy` | Shared actor; current deployment measurement | Highest aggregate validation score, latest pool index on ties; can differ from the reflection parent and child |
| `state.search.native.program_candidates` | Native pool and Pareto selector; selected parent supplies reflection source | Native accepted children append to the candidate pool; storing a candidate does not guarantee later parent selection |
| Per-case scores/frontiers, genealogy and counters in `search.native` | Per-task Pareto selection, validation and native stopping/bookkeeping | Saved from the pinned native state; must preserve task IDs and parent indices, not only aggregate scores |
| `state.search.sampler` and `.rng` | Minibatch scheduling and parent selection share restored random state | Exported after the native iteration, committed with the snapshot |
| `state.search.plan_sha256` | Checks that the checkpoint belongs to this public suite | A different public plan is rejected, not silently rescored into the same checkpoint |
| `state.seed`, `state.epoch` | Initial random seed and activated-iteration bookkeeping | Seed fixed; epoch advances in an admissible candidate snapshot and only persists on activation |

One slot allows at most one native reflection and disables merge. The agent
profile uses per-case utility scores and native minibatch `improvement_or_equal`
acceptance. Pool retention, aggregate-best deployment and platform admission are
different decisions. A child can fail native minibatch acceptance while the
candidate snapshot still advances valid search bookkeeping. Therefore a
GEPA `native_valid` draft is not proof that its child entered the pool.

After minibatch acceptance, full-suite validation appends the child without a
second improvement threshold. Old pool scores remain the saved full-suite
values; evaluating a parent on the current minibatch does not refresh that
parent's entire score vector. The external public cache may also reuse an
earlier rollout even though the native evaluation function was called again.

The JSON checkpoint is validated, materialized into a private temporary native
checkpoint and restored by the pinned library. Public fitness is a development
measurement. Native metric counts are not provider calls or compute. Legacy
non-agent contracts use a different single-epoch path and cannot inherit these
pool claims just because their public method name is also `gepa`.

## OpenEvolve: population, selection and prompt context

Sources: [adapter and database bridge](../src/rsi_lab/subjects/openevolve.py).
The pinned native database and worker own sampling and prompt construction;
the lab binds transport, evaluation and pre-inheritance activation.

Agent editors use `openevolve-harness-object-v2`: the entire model response is
one complete `rsi-harness-v1` JSON object, with each top-level key exactly once.
The old `{"harness": ...}` wrapper is not an accepted alternative. The bridge
serializes the validated object and constructs native Markdown framing itself. Backticks are
JSON-escaped for native extraction, preserving resource text such as fenced skill
examples. `model_receipt` retains the original object; `response_protocol`,
`response_encoding` and `proposed_source` identify the deterministic translation,
including candidates rejected before a native child ID is assigned. Sampling,
evaluation, database admission and deployment selection still run natively.

For agent mode, the bridge replaces only the pinned native full-rewrite output
instruction suffix. System and user messages share the same raw-object contract;
the preceding fitness, history, parent and context programs remain byte-identical.
An unexpected native output suffix or message layout fails before model dispatch.
`native_prompt` preserves the original; `prompt_transport` binds the native user
text, dispatched user text, retained context and replaced suffix with UTF-8 SHA256.
The receipt and provider journal retain the actual complete request identity.

This replaces the previous agent wrapper and response-string contracts for new
source-bound runs. There is no agent-mode fallback, fence repair, JSON repair or
automatic retry. Legacy non-agent code uses `openevolve-code-response-v1` with a
`response` string. Completed runs keep their archived implementation and receipts;
the failed natural candidate from 2026-11-17 is not reinterpreted under the new
contract. Scripted transport controls do not establish natural format reliability.

| State | Reader / effect on future search | Update and inheritance |
|---|---|---|
| `version.policy` | Shared actor | Selected deployment program; not necessarily the next sampled parent |
| `state.population.programs` | Program database, fitness ranking, parent and prompt-context lookup | Stores native program IDs, code, metrics, lineage and metadata; generated, stored and deployed remain distinct |
| `population.islands`, `.archive`, feature maps and best-program references | Native parent/inspiration sampling, elite retention and MAP-Elites | Preserve memberships and references together; deleting only a program row is not a valid withdrawal |
| Feature statistics / diversity reference state | Native feature normalization and diversity calculations | Part of exported database state; the configured complexity feature uses code length |
| `state.rng` | Native database/worker random operations within the serialized adapter boundary | Restored and exported around the slot; remote model randomness is separate |
| `state.generation`, database iteration fields | Candidate metadata and resumed iteration bookkeeping | Persist with activation; island-generation/migration fields are saved but this single-island wrapper does not run the upstream migration loop |
| `state.public_artifacts` | Saved public evidence from the proposal | The next proposal reconstructs artifacts by evaluating stored programs, possibly using the public rollout cache; this field itself is not its prompt input |

The worker can expose a program through more than the sampled parent and
`inspiration_ids`: ranked programs and other prompt sections also matter. In
the current configuration the worker's `diverse_programs` selection is a slice
of ranked programs; its name is not evidence of a separate diversity treatment.
Raw request bodies are the evidence of exposure. Database membership alone is
not evidence that a program was sampled or shown.

`population_after_native`, `population_after_platform`, `active_program_id` and
`archive_only_update` in native evidence describe proposal preparation before
independent review. Only `activation.json` and the verified `active.json` show
what actually committed. Native database addition can coexist with failed
method/public admission or a later review rejection.

## HyperAgents: paired policy/meta nodes

Sources: [adapter](../src/rsi_lab/subjects/hyperagents.py),
[isolated runtime](../src/rsi_lab/subjects/hyperagents_runtime.py).

| State | Reader / effect on future search | Update and inheritance |
|---|---|---|
| `version.policy`, `version.meta_agent`, `state.active_id` | Actor reads policy; these two components must equal the active archive node's files | Deployment selects the highest public score; this does not determine the next parent |
| `state.archive[id].files` | Selected parent's policy and meta become worker inputs; that parent's meta is actually loaded | Nodes retain policy/meta together; identical policies with different meta are distinct search objects |
| Node `parent_id`, `valid_parent`, `score` | Pinned parent-selection function and public deployment selection | Existing nodes are re-evaluated under the current public plan; valid, scored nodes are sampled uniformly in this bounded configuration |
| `state.seed`, `state.epoch` | Creates `Random(seed + epoch)` for parent selection | No persistent global RNG object; rejection retains the old epoch |
| `task_contract.meta_mode` | Fixed edit permission | `frozen` requires founder meta in every node; `editable` permits both exported files to change |
| `task_contract.meta_execution` | Explicit legacy ablation configuration | `founder` replaces both executed meta and meta content shown in the worker inputs; it is not a pure write-permission intervention |

A successfully evaluated child may stay in the archive while an older policy
remains deployed. The candidate snapshot includes the updated archive, active
pair and epoch. The deployment tie rule is the last entry in current archive
iteration order: restored old keys are canonical-JSON ordered and a new child is
appended. This is **not** a general latest-chronological-node rule for old ties.

The inherited surface is two files per node. Native meta executes in an isolated
temporary workspace and may create other temporary files during the invocation;
only policy/meta are extracted for inheritance. Worker-local random/time state,
temporary paths and arbitrary runtime state are not snapshotted. Equal seeds
and snapshots do not guarantee a deterministic remote or arbitrary-meta replay.
Node IDs also bind the operation, so distinct roots need not share native IDs.

Selected inputs are saved before worker dispatch. Separate bound stage records
now survive a failure before a draft: load entered, module loaded, model request
observed and forward completed. Missing stages are unknown. The slot and v2
events recover these observations without restarting execution; a script control
exercises a real meta request followed by failure. The legacy
`first_edited_meta_use` ablation selector still uses its successful-proposal flag,
not the new stage records. An experiment requiring the first actual invocation
must first declare its stage/checkpoint criterion; it cannot reuse that legacy
selector as if it covered failed invocations.

## What rejection and forking preserve

For all three adapters, proposal construction operates on a copy. A whole-candidate
reject or enforcing `inconclusive` leaves **all declared inherited state** at the
base: policy, pool/archive, scores, selector/sampler state and meta as applicable.
The differences are material: GEPA can lose a sampler advance without a retained
child; OpenEvolve can lose population/context expansion; HyperAgents can lose a
new policy/meta pair while the deployed policy would have stayed the same.

| External channel | Remains after rejection? | Experimental consequence |
|---|---|---|
| Provider journals, unknown reservations and spent budgets | Yes | No automatic resend, refund or fresh draw on resume |
| Public source × case rollout cache, when enabled | Yes | A later identical source can reuse evidence created by a rejected attempt; rejection is not erasure of every future influence |
| Proposal, review and activation records | Yes | Audit evidence persists; review reasons/probe outcomes are excluded from optimizer feedback |
| Consumed proposal slot / run progress | Yes | Equal accepted updates and equal proposal opportunities are different resource designs |
| Independent audit/final records | Separate post-search phase | They cannot determine proposal selection; missing labels remain missing |

`fork()` isolates the inherited-state database. Adapter forks share their supplied
provider, and a task package may share a public cache. It does not promise separate
budgets, independent randomness or an isolated external world. Review uses its
own probe runtime and budget; that stronger boundary comes from experiment
composition, not from calling `fork()` alone. No arbitrary external-effect undo
is implemented. If public cache retention is to be blocked, that requires a new
declared intervention and accounting design.
