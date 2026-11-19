# Adapter conformance specification

Specification and source walkthrough: **2026-11-16**. Acceptance concerns the
mechanisms declared in [the mapping](method-state-mapping.md), not a complete
reproduction of upstream SEABench or each optimizer's original runtime. The
[capability matrix](observation-intervention-matrix.md) limits the experiments
that can be claimed. A runnable adapter or a total test count is insufficient.

## Evidence and acceptance rules

Acceptance follows the claim being made. Freeze the implementation/configuration
and declare the state, readers and measurement scope needed by that claim. A
mechanism claim additionally needs a counterexample and a distinguishing control
with bound inputs/outputs. Keep these evidence levels separate:

- **Source-inspected**: the code has the stated path, without a distinguishing
  execution control. This is a design claim with a test obligation.
- **Controlled**: a named zero-API control exercises that mechanism and would
  fail under a plausible incorrect mapping. A stubbed worker does not validate
  native worker isolation.
- **Natural measurement**: repeated real executions estimate the behavior and
  uncertainty under the frozen experiment. Scripted controls cannot establish
  safety benefit, scorer accuracy or a causal meta disadvantage.

Run controls against pinned native components when the claim concerns native
selection. Use small synthetic state fixtures only where their role is explicit.
Freeze all configuration differences and compare requests, state and resources,
not only final scores. Declare any normalization of root-local addresses or
explicitly controlled incidental timing; preserve request content, execution
order and multiplicity. Never normalize away selection order or RNG differences.

## Acceptance depends on the intended result

| Intended result | Required acceptance | What it does not establish |
|---|---|---|
| Descriptive deployed-policy risk curves | Valid versioned task/scoring semantics; bound saved checkpoints and actual deployed source; independent audit allocation and feedback separation; relevant activation, restoration, recovery/accounting and observation-noninterference controls for the selected profile | The risk contribution of a particular archive entry, sampling branch or meta edit |
| Description of a native mechanism used along a trajectory | The preceding boundaries plus a reader/state mapping and distinguishing native controls for the named parent, retention, context or execution channel; stage/identity coverage must support the reported observation | That the observed mechanism caused a later risk change |
| Causal attribution to a state or mechanism intervention | The preceding evidence for the affected channel plus a valid state transformation, declared affected readers, paired allocation, sham or matched controls as appropriate, and independent follow-up measurement | Safety of untested descendants or every possible optimizer configuration |

The first row is a bounded acceptance target. It does not require proving the
effect of every database field or reproducing the full upstream runtime before
recording a curve. Name the implemented profiles and their restrictions instead
of presenting them as unrestricted native systems. If an unverified channel is
not used by the descriptive claim, list that limitation; do not turn it into an
open-ended gate. If a defect can change the deployed state, checkpoint identity,
measurement or resource position, resolve it before relying on the curve.

Natural curves still require scorer calibration on saved answers, repeated
judgments and independent executions, with missing labels and uncertainty kept
explicit. Scripted curves validate the pipeline only. Shared tasks and equal H
do not establish equal compute; report calls, tokens, cache reuse, review costs
and actual admitted/activated updates under the declared budget design.
The current privacy pack remains previously exposed development material; its
disjoint task roles do not create an unseen confirmatory sample.

## Four categories of conformance obligations

| ID | Property and distinguishing control | Failure example |
|---|---|---|
| M1 | Mechanism preservation: native decisions on a known state match the declared parent, retention and deployment rules | Parent always chosen from deployed policy; archive entries silently dropped |
| M2 | State restoration: restore a mature pool/archive and compare the next parent, request, minibatch and resulting state with the declared randomness controls | Snapshot saves source but loses sampler, feature state or meta pairing |
| O1 | Observation noninterference: event recording on/off, same controlled replies, identical native requests, RNG and resulting snapshots | Recorder consumes random draws, evaluates extra tasks or changes prompt order |
| O2 | Evidence completeness: distinguish observed absence, incomplete evidence, stage not reached and unsupported capability | Missing parent defaults to deployed policy; missing labels become safe |
| I1 | Rejection scope: enforce reject/inconclusive on an admissible snapshot; compare all inherited bytes and next-step readers | Policy rolled back while a rejected parent, meta or RNG update survives |
| I2 | Fork boundary: commit in one storage branch and compare sibling state; separately declare provider/cache/resource sharing | Isolated database advertised as independent budget or full environment rollback |
| I3 | Information boundary: review/probe/audit/final sentinels never enter native optimizer feedback | Independent risk score becomes public fitness or prompt context |
| R1 | Recovery/accounting: unknown dispatch retains reservation; completed resume causes no new dispatch or activation | Retry turns an unknown observation into a new sample; rejection refunds work |

Select obligations and counterexamples against the intended result above. Core
state/commit and measurement boundaries apply to descriptive curves; M1/M2 need
the additional channel-specific cases when a mechanism interpretation depends
on them. I1 applies when rejection is used, rather than requiring an unused
review treatment for a native-only curve. A module that withdraws an archive
object needs its own state-validity/read-channel controls beyond whole-candidate
I1. An implemented protocol is not evidence that the new intervention works.

## Current evidence inventory

The table identifies the scope of existing controls, including the targeted
repairs from this walkthrough. Test execution results belong in
[validation](validation.md); a listed test is not a claim it was rerun here.

| Evidence | What it establishes | Remaining limit |
|---|---|---|
| [Activation controls](../tests/core/test_activation.py) | Identity/base/capability checks, reject, idempotent receipts and query-only recovery | Does not certify method-specific field readers |
| [Three-adapter semantics](../tests/core/test_review_adapter_semantics.py): snapshot/fork and reject/inconclusive | Separate inherited storage, whole-snapshot preservation, no rejected-source/review sentinel in the next controlled request | Shared providers/cache remain external; not every possible native context path is exercised |
| Same file: `test_read_only_process_projection_preserves_native_requests_and_state` | Re-projecting completed evidence leaves state, requests and usage unchanged | Post-hoc purity is narrower than a separate on/off execution comparison |
| [OpenEvolve event control](../tests/agentbench/test_process_audit.py): `test_pure_events_do_not_change_search_requests` | Separate recording-on/off executions compare controlled editor requests and final snapshot | This test alone does not compare every resource field or certify every prompt branch |
| [GEPA event control](../tests/agentbench/test_gepa_events.py) | Separate recording-on/off executions compare actor/editor/judge payloads and responses, each active snapshot, final search/sampler/RNG and resource/reservation accounting | Judge request IDs hash the absolute episode path and are explicitly matched by dispatch order; content/order/response evidence is preserved |
| [GEPA state-only control](../tests/core/test_gepa_semantics.py): `test_rejected_child_can_commit_search_state_but_review_blocks_inheritance` | A real native child rejected on minibatch utility can still yield an admissible search-state update; reject/inconclusive preserve the mature base, and the next controlled attempt reproduces the blocked state | Does not cover arbitrary frontier changes or unknown native failures |
| Same file: `test_native_pareto_parent_is_a_specialist_while_adapter_deploys_mean_best` | Real actor/task/native-adapter evaluations build A=(1,.5), C=(.5,1), B=(.8,.8); next parent is A/C in the actual reflection request while deployment remains B | A distinguishing selector control, not an estimate of all sampling probabilities or natural specialist usefulness |
| [SEABench controls](../tests/agentbench/test_seabench.py): per-case pool and cache tests | GEPA retains per-case scores across slots; public cache is charged once and unknowns are not replaced | A configuration flag is not evidence of Pareto specialist selection; cache reuse is not fresh execution |
| [OpenEvolve parent controls](../tests/core/test_review_adapter_semantics.py) | Non-deployed parent comparisons distinguish child equal to parent from child equal to deployment; missing parent is unknown | Does not cover every native parent/inspiration/prompt branch |
| [OpenEvolve ranked-context control](../tests/core/test_openevolve_semantics.py) | A mature population built through real worker/evaluation/admission exposes additional top/diverse programs in the actual request, including native inspiration/top deduplication and bound source/request IDs | The last parent/inspiration choice is fixed to isolate prompt construction; it does not test the parent sampling distribution or causal effect of exposure |
| [HyperAgents identity controls](../tests/core/test_hyperagents_identity.py) | Same-policy/different-meta nodes retain native identity; old tied nodes follow restored archive order | Worker is stubbed; this is adapter identity/selection evidence, not native meta execution |
| [HyperAgents transport controls](../tests/core/test_hyperagents_transport.py) | Real isolated-worker tool boundary, edited-meta execution, frozen write restrictions and completed-result replay without redispatch on a supported host | Interrupted/failed invocations use the separate stage controls below; arbitrary worker-local randomness is not validated by transport replay |
| [HyperAgents execution-stage controls](../tests/core/test_hyperagents_execution.py) | Native-host controls distinguish non-deployed parent meta B from deployed meta A, an observed model request followed by failure without a draft, unknown resume without restart/resend, and cross-meta marker rebinding | Observed load/request stages do not imply forward completion or remote response success |
| [Failed-slot integration](../tests/core/test_proposal_evidence.py) | A real failed invocation remains observed in the durable slot and v2 event; base/parent/input binding is checked and completed resume is read-only | Covers the declared worker path, not every arbitrary meta failure |
| [HyperAgents event control](../tests/agentbench/test_hyperagents_observations.py) | Independent on/off runs compare complete provider requests, response identities, final archive and costs with the real native worker | Incidental temporary paths, actor elapsed time and judge operation addresses are held fixed before execution; not uncontrolled stochastic replay |
| [Candidate-object controls](../tests/core/test_candidate_state.py) | v2 cases distinguish same-policy meta nodes, actual object membership/deployment and unknown native identity | Current revision's integrated execution status belongs in validation; policy equality alone never proves object activation |
| [Meta ablation controls](../tests/agentbench/test_meta_ablation.py) | Shared inherited prefix, founder substitution and completed resume | Legacy checkpoint flags can miss earlier failed meta invocations; substitution also changes visible meta input |
| [Event projection controls](../tests/core/test_process_events.py) | v2 separates selection, child retention, whole-snapshot admission/commit, policy change, source exposure and meta execution; rejects legacy slots instead of relabelling them | These projections remain bounded by saved evidence; integrated v2/worker checks are tracked separately from earlier completed validation |

## Method-specific counterexamples still needed

These are explicit follow-up acceptance cases, not implied successes of the
historical full suite. Implement them before making the associated claim or
running an intervention that relies on that channel.

| Method | Control inputs and expected distinction | Claim it would support |
|---|---|---|
| GEPA | Child improves selected minibatch but has lower full-suite aggregate | Native retention need not improve deployment; full validation is not a second improvement gate |
| GEPA | Mature checkpoint restored/forked under fixed replies; compare parent index, batch IDs, requests, frontier and RNG | Continuation fidelity beyond origin-snapshot isolation |
| OpenEvolve | Hold program text fixed, vary valid island/archive/map memberships and feature statistics; compare native branches and retention | Database fields preserve distinct selection channels; stored program does not mean eligible through every channel |
| OpenEvolve | Lower-scoring retained child, unchanged deployment, later native parent or reference use | Archive-only changes can affect future search through a demonstrated channel |
| OpenEvolve | Fresh-process restore of a mature pool; explicitly control/check hash/set iteration as well as RNG | A seed and serialized RNG alone may not provide portable deterministic continuation |
| HyperAgents | Native worker creates an extra temporary file, then new invocation checks absence; separate denied outside-read/network canaries | Two-file inheritance and OS isolation claims have direct evidence rather than only implementation inspection |

For GEPA's selector, “Pareto” here means the pinned instance-frontier procedure:
per-case winners, redundancy removal using aggregate scores, then sampling
weighted by remaining case wins. It is not simply uniform sampling from all
non-dominated score vectors. For OpenEvolve, current `_restore` checks only part
of database referential integrity; a future withdrawal must rebuild and validate
feature maps, best references and other affected structures. GEPA likewise needs
frontier/index reconstruction. Manual JSON deletion is not a validated operation.

## Walkthrough decisions and implementation order

The walkthrough found two concrete observation defects: OpenEvolve's generated
source was compared to deployment instead of its non-deployed parent; HyperAgents
generated nodes lacked their actual child ID, collapsing same-policy meta variants
to source labels. Both are repaired with targeted controls. HyperAgents' tie
description now names archive order; the underlying selection algorithm is
unchanged. Completed run artifacts retain their original source and meanings.

The current revision implements nine `rsi-process-events-v2` projections and
`rsi-candidate-state-v2` object fields; see the
[event contract](observation-intervention-matrix.md#current-event-and-object-contract).
Child retention, whole-snapshot admission and activation are distinct. Native IDs
can be unknown, and source equality is separately recorded. HyperAgents now has
bound invocation/stage records, including partial observations without a draft.
The integrated controls cover an observed meta request followed by failure
without a draft. Do not infer execution from an input-file hash or a missing
stage marker. The recording toggle controls event projection; durable invocation
and stage capture are always on. It does not compare arbitrary time-sensitive
meta code with a worker whose stage instrumentation has been removed.

Natural scorer calibration can proceed independently on frozen answers. Once the
bounded descriptive requirements are met, risk curves may use a frozen independent
allocation without waiting for every mechanism counterexample in this document.
Keep their interpretation descriptive. Mechanism-specific attribution waits for
the relevant controls and, for causal effects on risk, a legal intervention and
its controls. A fourth adapter supplies the same claim-scoped mapping and limits;
it need not invent components that its method does not have.
