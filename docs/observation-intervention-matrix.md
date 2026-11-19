# Observation and intervention capabilities

Semantic inventory: **2026-11-16**. This supplements the implemented, coarse
`rsi-method-capabilities-v1` registry in [methods.py](../src/rsi_lab/methods.py).
It does not add new runtime capabilities or reinterpret old artifacts. The
[state mapping](method-state-mapping.md) defines the objects; the
[conformance specification](adapter-conformance.md) defines the evidence needed
to claim that a capability is faithful.

## Observation coverage

**Recorded** means an implementation records bound evidence, not that every
mechanism has a distinguishing control. **Partial** identifies an explicit
coverage gap. **Unsupported** means the current protocol cannot supply the
measurement; absence of an event cannot turn it into a negative result.

| Question | GEPA agent-utility | OpenEvolve bounded | HyperAgents bounded |
|---|---|---|---|
| Which policy executes tasks? | Recorded: active snapshot policy | Recorded: active snapshot policy | Recorded: active pair's policy |
| What state can affect future search? | Recorded checkpoint; specialist selection has a native control, other field effects need their own evidence | Recorded database; prompt context has a native-worker control, temporary caches and unordered-set replay limits remain | Recorded archive/seed/epoch; worker-local execution state excluded |
| Was a child generated and retained? | v2 binds an appended pool index when observed; rejected child can have no native index | Child ID and candidate/active population membership where observed | Node ID binds operation + policy/meta; candidate and active archive membership |
| Which objects were eligible as parents? | Derivable from per-case frontier and pinned selector; no explicit event-level eligibility set | Multiple sampling branches use different memberships; no explicit event-level eligibility set | Derivable from valid/scored archive plus pinned selector; no event-level eligibility set |
| Which parent was selected? | Native pool index in v2 selection, distinct from proposed deployment index | Native parent ID | Native parent ID, also bound before worker invocation |
| Which other candidates entered the prompt? | Source-presence scan; no complete semantic role classification | Real-worker control shows ranked top/diverse sources outside parent/inspiration; generic section/role coverage remains partial | Invocation files and durable requests support successful/failed paths; scope depends on observed stage/request evidence |
| Which meta actually ran? | Fixed optimizer implementation; no editable meta capability | Fixed optimizer implementation; no editable meta capability | Bound input identity plus separately observed load/request/completion stages; a selected file alone is not execution evidence |
| What did review decide, and what committed? | Separate bound decision and activation receipt | Separate bound decision and activation receipt | Separate bound decision and activation receipt |
| Did a previously retained object influence later risk? | Unsupported as an observational conclusion | Unsupported as an observational conclusion | Unsupported as an observational conclusion |

`retained_policy_sources()` lists distinct stored policy sources, not an eligibility
set. It deduplicates identical source text; audit/review of these sources cannot
distinguish two HyperAgents nodes that differ only in meta. That is intentional
for current-policy behavior measurement, but insufficient for search-state risk.

Identity has three distinct levels: native object ID scoped to method/root,
policy-source hash, and full snapshot hash. The same source can occupy multiple
native objects. v2 allows `native_id: null`; it does not invent an object ID from
a policy hash. Source-only labels in legacy artifacts must not be reinterpreted
as native identities. Source hashing is byte-sensitive; the existing
`source_changed_from_parent` diagnostic compares text after stripping outer
whitespace. That diagnostic cannot define native acceptance, no-op updates or
cache identity. Missing parent evidence yields `null`, never a guessed parent.

## Current event and object contract

[`rsi-process-events-v2`](../src/rsi_lab/studies/process_events.py) implements nine
**post-hoc slot projections**. They separate decisions but are not a complete
chronological trace of native internals. Their common bindings identify the
operation, base/candidate/active snapshots, source evidence and resource records.
Referenced costs are shared measurements, not nine additive charges.

| Event | Meaning and principal evidence | Must not be inferred |
|---|---|---|
| `proposal` | Prepared candidate and generated source/object observations, or explicit missing/unknown outcome | A completed proposal from an attempted call |
| `native_selection` | Selected parent/inspirations and proposed deployment object only | Child admission or authorization to commit |
| `native_retention` | `child_admitted` plus generated objects' `object_in_candidate_snapshot` | That native admission necessarily entered the committed archive |
| `snapshot_admission` | Method/public pre-review decision about the complete `CandidateDraft` | The GEPA child's minibatch verdict; a rejected child can still yield admissible search progress |
| `review` | Requested/executed status, module or control result, effective decision and bound record | Review happened because an arm was configured, or observe-only rejected activation |
| `commit` | Activation receipt, `inherited_state_changed`, search-state change and generated objects' retained/deployed status afterward | Object deployment merely because its policy text matches the deployed source |
| `deployment_change` | Before/after executable policy-source hashes; other component changes reported separately | A meta-only or search-state-only change is a policy change |
| `candidate_exposure` | Exact-source presence in saved requests, selected roles and provider status | Semantic use, successful consumption or causal effect on a later answer |
| `meta_execution` | Bound worker input identity and observed execution stages when available; explicit `not_observed`/`not_applicable` otherwise | An editable-meta risk guarantee, or execution from input identity alone |

Slots declare [`rsi-candidate-state-v2`](../src/rsi_lab/studies/candidate_state.py).
Each generated observation separates `native_id`, `identity_kind`,
`object_identity_coverage`, policy/meta hashes, `native_child_admitted`,
`object_in_candidate_snapshot`, `object_retained_after`,
`object_deployed_after`, and `policy_matches_deployment`. The last field is a
source-equality fact independent of the object's membership or activation. A
same-policy/different-meta HyperAgents node can match the current policy while
remaining uncommitted. A GEPA rejected child has no appended pool index even if
an old pool entry contains identical text. Unknown identity/membership stays
null; it is not an observed absence.

The ambiguous `active_after` and `platform_retained` candidate fields are removed
in v2. V1's six events and source-oriented fields retain their original meaning
inside completed artifacts. The v2 projector rejects legacy slot evidence;
inspect those runs with their frozen source rather than rewriting them.

HyperAgents' [`hyperagents-meta-execution-v1`](../src/rsi_lab/subjects/hyperagents_runtime.py)
records `load_entered`, `module_loaded`, `model_request_observed` and
`forward_completed` separately. The pre-worker invocation binds base snapshot,
selected parent and exact policy/meta inputs. Entering module loading does not
prove successful loading or forward completion. An observed request does not
prove a successful remote response; consult its provider receipt. Missing stage
markers remain null, including after a failure or in a legacy run. Intent-only
recovery preserves unknown status without restarting the worker or resending.
Real-worker controls now cover the non-deployed meta parent and failure after a
request. Integrated failed-slot v2 projections and independent recording-on/off
controls also pass; see the dated [validation record](validation.md). The latter
fixes incidental worker paths, actor timing and judge operation addresses before
execution and compares actual request bytes, archive state and costs. It does
not promise deterministic replay for arbitrary time-dependent meta code.

Implementation and conformance are separate. Named controls and remaining gaps
are listed in [adapter conformance](adapter-conformance.md); dated execution
results belong in [validation](validation.md). Neither an event kind nor a test
file establishes universal coverage.

## Intervention effects and availability

| Operation | Reads / timing | Blocked or replaced channel | Current availability |
|---|---|---|---|
| Whole candidate review | Public probes and bounded snapshot difference, after method/public admission and before activation | All declared inherited candidate state is withheld on enforcing reject/inconclusive | All three; reference module supports deployed/new-retained policy evidence |
| Observe-only review | Same evidence and timing | No selective block: native/public decision remains in force | All three; consumes review allocation and, when enabled, the shared optimization cap |
| Random rejection | Frozen probability and root/slot draw after method/public admission | Same whole-candidate commit channel, without behavior evidence | All three; probability must be calibrated for a matched-rejection study |
| Block deployment but retain search state | Candidate deployment decision | Deployment only; archive/meta may remain | Unsupported; current activation is whole-snapshot replacement |
| Withdraw an existing candidate | Declared existing object and all named future-use channels | Requires coherent pool/membership/context/lineage operation | Unsupported; removing one dictionary entry is not a module |
| Freeze meta edit permission | Frozen experiment configuration before search | Meta writes forbidden; archive policy search continues | HyperAgents `meta_mode=frozen` only |
| Substitute founder meta on continuation | Bound legacy ablation branch | Executed meta **and visible meta input** replaced on each edit | HyperAgents legacy study only; not a generic gate capability |
| Finite continuation review | Isolated future-search branch and explicit allocation | Would inform admission from later behavior | Unsupported; a snapshot fork alone is insufficient |

The last two meta conditions answer different questions. GEPA and OpenEvolve do
not receive artificial meta components to make this a three-method comparison.
An archive withdrawal must eventually specify parent, prompt-reference and
deployment channels independently; it must also preserve valid method state.

Whole-snapshot rejection is an operation with a shared meaning but different
consequences: lost sampler progress, lost population context or lost policy/meta
nodes. Report candidate count, pool delta, policy/meta changes, eligible and
rejected updates, missing blocks, calls/tokens and actual activated steps. Do not
infer equal search loss from equal rejection counts.

## Claim-scoped comparisons

Descriptive risk measurement does not wait for proof of every archive reader.
For the selected profile, first establish valid task/scoring semantics, bound
deployed checkpoints, isolated independent evaluation, correct missing/cost
accounting, and relevant recovery/noninterference controls. Then describe the
observed deployed-policy curve under that fixed allocation. Natural judge and
execution calibration remain necessary; a scripted curve is only a pipeline
control. The full upstream Session or every optimizer configuration is not a
prerequisite for this explicitly bounded result.

Explaining a particular native channel additionally requires its state/reader
mapping and distinguishing controls. Attributing a later risk change to that
channel additionally requires a valid intervention and a suitable counterfactual
design. Co-occurrence of archive exposure, meta execution and risk cannot supply
that attribution.

| Comparison | Required fixed conditions | Interpretation limit |
|---|---|---|
| Descriptive method trajectories under a common actor/task envelope | Task/public-objective version, actor/tools, resource unit, bound saved policies and independent evaluation allocation; claim-scoped conformance | Describes these bounded configurations; does not identify why one trajectory differs or rank official upstream systems |
| Deployed-policy vs new-retained-policy review | Same whole-candidate rejection rule; report policy count and missing evidence | More checked policies also create more noisy-rejection and budget-block opportunities |
| Behavior vs random rejection | Development-calibrated random probability, same rejection scope and declared budget design | Equal probability does not guarantee equal realized rejection or search loss |
| Meta editable vs frozen | HyperAgents-only paired initial policy and task conditions | Measures edit permission; useful meta changes or actual descendant use still need measurement |
| Equal deployed policy, different search state | Legitimate frozen checkpoints, identical continuation allocation and specified state operation | Current observations can describe the difference; targeted causal withdrawal remains unsupported and needs coherent state edits plus sham/matched-removal controls |

Search-opportunity matching and total-optimization-budget matching are separate
designs. Calls are not tokens or compute. Public cache reuse, rejected attempts
and review overhead remain in the accounting. Independent audit/final have a
common separate allocation and are included in experiment totals.

## Remaining coverage and attribution requirements

The v2 separation does not supply complete parent-eligibility sets, every native
substep/order, generic prompt-section roles, or a causal influence oracle.
Capabilities remain configuration-level declarations. Individual observations
must preserve the distinction between observed values, missing evidence, stages
not reached and mechanisms not applicable. `not_requested` does not mean
unsupported; `no_requests` establishes absence only in the inspected journal.

For a future archive intervention, declare affected parent, context-reference,
deployment and lineage channels, then rebuild and validate all related native
indexes/frontiers/memberships. Keep current deployment fixed when that is part
of the estimand, and declare resource and rejection matching. Manual JSON
deletion, source-presence scans and equal H cannot substitute for these controls.
No generic archive-withdrawal or continuation-review capability is enabled by
the new events.
