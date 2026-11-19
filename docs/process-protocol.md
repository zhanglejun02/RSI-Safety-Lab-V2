# Cross-method process safety experiments

Implemented development protocol, 2026-11-16. The lab preserves method-specific
search while owning state identities, observations, admission and independent
evaluation. Its first three questions are method validity, information omitted
by endpoint scores, and how intervention changes subsequent risk and utility.
Neither platform acceptance nor scripted outcomes establish a novel finding.

Start with the [method state mapping](method-state-mapping.md),
[observation/intervention matrix](observation-intervention-matrix.md) and
[conformance specification](adapter-conformance.md). They record the actual
adapters' semantics, current evidence and remaining limits. Define a comparison
from these objects and channels before choosing its metrics or intervention.

We borrow the separation of lifecycle, method configuration and trusted evaluation
from [RSIHub's design](https://github.com/simple-agent-lab/RSIHub/blob/main/docs/concepts/design.md).
We retain the lab's native adapters instead of rewriting every optimizer into a
common sequence of operators. No RSIHub implementation code is vendored here.
The [GEPA recipe](https://github.com/simple-agent-lab/RSIHub/blob/main/recipes/gepa/README.md)
is also a useful example of explicitly documenting omitted mechanisms.

## Composition and public entry points

An experiment is a method configuration, task pack, observation plan, intervention
configuration and resource allocation. Both new configurations use the existing
`seabench-controller` profile and public `rsi-lab` / `rsi_lab.agent_bench` API:

```bash
rsi-lab plan --config configs/seabench-process.json --output runs/process-plan.json
rsi-lab run --config configs/seabench-process.json --plan runs/process-plan.json --output runs/process-control
rsi-lab plan --config configs/seabench-interventions.json --output runs/interventions-plan.json
rsi-lab run --config configs/seabench-interventions.json --plan runs/interventions-plan.json --output runs/interventions-control
```

Both are scripted zero-API controls. The first has frozen, GEPA, OpenEvolve and
HyperAgents frozen/editable meta configurations. The second demonstrates four
intervention arms on OpenEvolve plus the frozen reference. Their one-seed results
are fixtures, not natural estimates. HyperAgents requires the supported isolated
macOS host; planning rejects an unsupported host without a silent fallback.

`methods.py` declares mutable state, observable objects, supported interventions,
external state and limitations. The plan binds those declarations and rejects
unsupported combinations. GEPA retains persistent per-case Pareto search and
reflection without merge; OpenEvolve retains its single-island population and
native sampling; bounded HyperAgents retains its policy/meta archive and native
meta execution. The actor, tools and task interface are shared experimental
conditions. These are bounded adaptations, not full original-system scores.

## Versioned tasks and measurement

`task_pack: privacy-drafts-v1` selects ten rewritten drafting tasks from the
previously exposed SEABench personal-admin/privacy resources. Source revision,
file hashes, factual references, normalized world and transformations are in
`data/privacy_drafts_v1.json` and the frozen plan. Legacy configurations without
`task_pack` retain their existing bridge.

The pack resolves recipient identities and conflicting factual joins explicitly.
The public task supplies recipient, purpose and authorization. Each episode has
a reset, read-only workspace and one consistent executor prompt; it does not
depend on the original Session or ask for unavailable memory/checkpoint tools.
Only the declared instruction policy persists between executions.

| Partition | IDs | Visibility |
|---|---|---|
| Development | 001–004 | Optimizer; public utility feedback |
| Public probes | 005–006 | Review capability only |
| Process audit | 007–008 | Independent evaluation after all search roots freeze |
| Final | 009–010 | Independent final evaluation after freezing |

All four partitions come from an already exposed shared world. The separation
prevents runtime feedback leakage; it does not create unseen tasks or new-world
generalization. A formal study needs an independently frozen allocation with
environment/family grouping and exposure records.

The answer is JSON text containing `recipient_id`, `message` and `private_note`.
Utility concerns the usable recipient message. Privacy concerns information
outside the recipient's current authorization; private notes are evaluated as a
separate whole-answer diagnostic. No message is actually sent. Missing artifacts,
malformed submissions, wrong recipients and incomplete judging are explicit;
they cannot silently receive a clean safety label. Known violations survive
missing utility measurements.

The new `privacy-drafts-scoring-v1` judge receives a complete bounded evidence
object. Oversized evidence produces a missing observation before dispatch, not
a truncated safe prefix. Claims of disclosure require exact channel-bound
evidence. These checks validate the scoring contract, not model accuracy:
natural scorer calibration and independent human annotation remain outstanding.
Native source rubrics and this derived scorer must not be pooled as one measure.

## Events and candidate identity

`record_events: true` publishes nine `rsi-process-events-v2` post-hoc summaries
per recorded proposal slot: proposal, native selection, native child retention,
snapshot admission, review, commit, policy deployment change, candidate exposure
and meta execution. The frozen plan names the event protocol. Events bind root,
operation, base/candidate/active snapshot, evidence and cost records. They are
not a complete native chronological event stream. GEPA can reject a child yet
submit a valid search-state update; these now appear in separate event kinds.
Unknown stages remain unknown. Per-event costs reference existing measurements
and must not be summed as independent charges.

`rsi-candidate-state-v2` separates `policy_matches_deployment` from native-object
membership and selection: `object_in_candidate_snapshot`, `object_retained_after`
and `object_deployed_after`. Native identity may be unknown; source equality
cannot fill it in. A rejected meta-only child can match the deployed policy while
its new archive node is neither retained nor deployed. The commit event separately
records full inherited snapshot change and search-state JSON change.
Legacy `active_after` / `platform_retained` fields are absent from new records.
The projector verifies source and status against native evidence and the actual
active snapshot, not only against other derived fields.

Version 1 files and completed runs keep their frozen source semantics. The v2
projector rejects a legacy slot rather than relabeling its source-level flags as
object-level evidence. New source and plans require new output directories.

Recording derives from immutable evidence after generation. `context_sources`
retains the old selected-parent/reference meaning; `candidate_exposures` covers
all retained sources checked against actual editor requests. Selection roles and
exact request matches are separate. This covers OpenEvolve's extra prompt inputs
without treating a parent/inspiration list as complete exposure evidence.
Exact source presence is not semantic influence, and a request with an unknown
response is not evidence of a successful generation.

HyperAgents saves its selected inputs before worker dispatch. Bound host records
then distinguish entering meta loading, module loading completing, a model RPC
being observed, and `forward` returning. A failed invocation can therefore have
observed execution without a draft, admission or commit. Missing markers stay
`null`; entering loading does not prove it succeeded, and observing a model RPC
does not prove provider dispatch or a successful response. Founder-meta replacement
is labeled as a separate execution input, not as another file of the archive node.
The isolated worker and unknown-intent no-restart rule remain in force.

Each root keeps `step-*/process-events.json`; the report provides
`process-events.jsonl`. Their fields are documented by the versioned declarations
and the small projection module `studies/process_events.py`.

## Independent process audit

`observations` freezes task IDs, fractions, resource coordinate/limit, policy
scope, repeats, coverage cap, risk-change tolerance and separate budgets.
The all-root generation barrier precedes audit and final phases. Audit reads
saved snapshots and never feeds labels, evidence or checkpoint selection back
into search or review.

At each configured budget fraction, select the last completed slot at or before
that position. The initial snapshot is always available at zero. A successful
commit remains available if its later public measurement failed. Costs are
measured at the saved end-of-slot boundary, not an invented exact commit time.
If the fixed proposal horizon ends before the resource cap, its last valid state
carries forward; report actual spending and missing slots alongside this grid.

Coordinates are calls or tokens. Token progress charges actual usage plus
unsettled reservations; it is an accounting coordinate, not exact compute.
Scripted controls require calls because they have no measured model tokens.
Scope is `deployed_policy` or `retained_policies`; the latter selects the deployed
source first, then retained sources by hash up to `max_policies`. Coverage
truncation is explicit. It does not claim to audit every rejected historical
candidate or future meta execution. A frozen reference has no retained-pool
capability; omit it for that scope or run its deployed-policy allocation separately.

Every scheduled coordinate/policy/task/repeat executes freshly, even if the same
policy appears at several coordinates. Completed resume only reuses the same
bound observation. Audit results bind source, case, operation, snapshot and plan;
an observation from another measurement cannot be silently relabeled.

`risk-curves.csv` contains deployed-policy points and coverage. The root-level
process risk AUC uses trapezoidal integration on this declared grid; missing
labels yield an unknown estimate plus missing-label bounds. It measures risk of
standardized policy executions, not actual accumulated harm. First observed
degradation/recovery uses the fixed tolerance and is descriptive, not proof of
an exact change time or statistical significance. `candidate-audits.csv` retains
candidate scores and later deployment/exact-request reuse indicators.

## Interventions and resource comparisons

| Arm | Decision after method/public admission accepts the candidate snapshot |
|---|---|
| `native_only` | Native/public admission controls activation |
| `behavior_review` (`review` legacy name) | Public behavior check; reject/inconclusive blocks the entire candidate snapshot |
| `observe_only` | Same behavior evidence and original module result; native decision still controls activation |
| `random_reject` | Explicit probability and seed, no behavior evidence; fixed slot-hash decision |

Review scope and rejection scope remain separate. Random rejection and enforcing
review use the same candidate-not-committed semantics. Observe-only is not a
safety gate. Review CSV shows module disposition separately from enforcement and
the actual admission decision. Random decisions and their probability are in
`interventions.csv`; skipped native-rejected updates remain recorded.

The control configuration's probability 0.5 is a wiring fixture, not an estimate
of a matched rejection rate. Formal E3 freezes probability from development
calibration and reports actual eligible/rejected counts. No new random draw is
made on resume, and changing candidate content cannot choose a different draw
for the same root/slot. Shared seeds do not guarantee common remote randomness.

Without `optimization_budget`, search and review have separate caps: extra
review means extra resources. With it, train actor, editor, train judge, review
actor and review judge share root-level call/token limits in addition to local
provider caps. The durable pre-dispatch check reads existing journals under a
root-local lock; unknown calls retain reservations. It does not reset or refund
spent resources on rejection. Independent audit and final use separate common
allocations and are counted in experiment totals, not in the optimization cap.

The new profiles demonstrate fixed-total optimization caps. Formal selective
benefit needs improvement over native-only and calibrated random rejection,
acceptable utility loss, and evidence that missing blocks or budget exhaustion
do not dominate. Reports include both native-only and random-reference contrasts.
Identical call caps are not identical tokens, money or model compute; report
actual resources and the comparison unit explicitly.
Observe-only can shift the resource-coordinate curve simply by spending review
budget before the next commit. Compare update indices and snapshot identities
as well; that shift alone is not evidence of safer selection.

## Validation and research sequence

E0 uses the mapping and claim-specific controls in
[adapter conformance](adapter-conformance.md). Descriptive risk curves require
valid deployed checkpoints, independent measurements, resource/missing rules and
relevant recovery/noninterference controls. Explaining a named mechanism also
requires its reader/selection control; causal attribution additionally needs a
valid state intervention and counterfactual controls. These are separate acceptance
requirements, not a demand for exhaustive upstream fidelity before any experiment.
E1 scoring/execution calibration can proceed on frozen answers in parallel.
E2 observes natural trajectories; E3 compares interventions under their relevant
acceptance criteria. No E1–E3 result is created by the scripted
controls. Root is the statistical unit; tasks, checkpoints and repeats are nested
measurements. Formal effect sizes, utility tolerances, allocation, sample size and
missing rules must be frozen before confirmatory runs.

The earlier [archive withdrawal study](archive-intervention-study.md) remains a
possible later module. Archive withdrawal and finite continuation review are
explicitly unsupported in the current capability registry.
