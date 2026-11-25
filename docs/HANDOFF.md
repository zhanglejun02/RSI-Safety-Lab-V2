# Current work

**2026-11-26 three-layer prototype tested; natural campaign incomplete.** Read
[the result and limitations](improvement-safety-verdict-20261126.md) and
[frozen design](improvement-safety-pilot.md). Two templates, four final conditions,
two repeats; Frozen, GEPA and bounded HyperAgents, one root each, two update
opportunities. GEPA committed two updates; its final version completed 8/8
independent cases without an observed violation and used one model call per case.
Its service-cost utility is unchanged. Full parent measurement and method
comparison remain incomplete. HyperAgents' two slots ended with network-unknown
outcomes and no commits; no edited meta was executed.

Natural run `runs/current/improvement-20261126-v1`: 151 dispatched calls, 147
complete responses, four unknown with retained reservations. Independent source
allocations: 40 total, 10 normal completions, two unknown, 28 unattempted. Three
tmux commands exited 2. No paid run remains active, no unknown call was retried,
and no additional run is scheduled. There is no completed summary; the read-only
partial report preserves all missing observations.

A separate zero-API latent-risk control starts both continuations from the same
safe task policy (0/4 violations). Retained meta produces 4/4 violations in the
final successor; founder-meta execution gives 0/4. This is a deliberately scripted
sensitivity test, not natural evidence. Native integration, intervention identity,
partial reporting and resume checks passed; see [validation](validation.md).

Run through `scripts/run_improvement_pilot.sh`. The conditional third-layer
launcher `scripts/run_improvement_meta.sh` selects the first actual edited-meta
execution checkpoint, never a favorable safety outcome. If none exists, report
that layer unavailable. The read-only exporter is `scripts/summarize_improvement.py`.
No new safety algorithm, broad benchmark validity or natural degradation is
established by this implementation. Do not pool this partial campaign with later
task versions or replace its unknown observations.

**2026-11-24 bounded update search ended; no qualifying update found.** See the
[result and candidate table](update-search-verdict-20261124.md) and
[frozen design](update-search-20261124.md). Ordinary LLM context-policy mutation
and structured hypotheses each produced four executable proposals: eight
proposals, five distinct update sources. All already have observed counterexamples
to the predeclared utility-preserving repeated-risk criterion in the first three
blocks. Five-block measurement is incomplete: 480 allocated final episodes,
296 normal completions, 54 step limits, 130 unknown API outcomes. Missing is not
safe zero, and exit zero does not certify a complete measurement endpoint.

The common three-block table is a post-hoc availability diagnostic, not a new
endpoint. The one source with higher observed risk loses 15.10 utility percentage
points. Its six observed scheduling positives use non-address recipient IDs;
the permissive simulator records successful unauthorized sends. Preserve the raw
labels, but do not call them demonstrated valid-address leaks. Two of four
structured hypotheses explicitly predict reduced risk, contrary to this search
objective. This is not evidence that hypothesis-driven search generally fails.

Both existing shadow reviewers return inconclusive on six of eight proposals.
Full validation rejects two; relative review rejects one and accepts one. The
same deduplication update has opposite relative decisions across two public
executions because one banking behavior differs, without an LLM judge or meta
change. There is no independently verified utility-preserving dangerous target
for sensitivity estimation, and no online intervention-benefit test.

Campaign: `runs/current/update-search-20261124-v1`, frozen commit `4c0a7a8`.
Cost: 8,512 dispatched calls, 22,232,079 reported tokens, 136 unknown calls with
retained reservations. Status telemetry records 128 HTTP 402, one 429 and seven
transport errors; a subsequent read-only balance query showed availability.
Do not automatically recharge, retry or expand the experiment. The completed
run remains immutable. Reproduce analysis with `scripts/summarize_update_search.py`;
outputs are under `output/update-search-20261124/`.

Frozen-source full zero-API regression: **1,122 passed**, 948.06s, following the
documented sandbox cleanup fix and 29 targeted checks. The scripted control
`update-search-control-20261124-v2` completed all 720 allocations. Post-run source
now pauses a root on a new unknown outcome; explicit resume consumes the saved
missing observation/charged editor attempt without retry. It also distinguishes
observed criterion failure from missing-only inconclusiveness. These later changes
passed **12 targeted zero-API checks**, 57.90s; see [validation](validation.md). Completed
natural resume without credentials and read-only export verified unchanged run
artifacts with zero additional API calls. No larger natural batch is scheduled.

**2026-11-23 bounded feasibility experiment completed.** Read the
[one-page verdict](feasibility-verdict-20261123.md) and
[frozen protocol](feasibility-20261123.md). GEPA + the full-public-validation
component ran two roots per arm, two slots, four clean development cases, eight
public probes and eight independent cases repeated three times per source. No
task/seed replacement, manual natural-candidate repair or automatic API retry
occurred. `runs/current/feasibility-20261123-v1` finished in tmux with exit zero.
An earlier launcher race stopped before any run or API dispatch.

All eight proposals parse as Python; seven have valid resource manifests and
execute. Every executable candidate improves founder-relative mean utility in
all three repeat blocks (+7.64–21.88 percentage points overall). Only one of the
two native-only roots changes final deployment, so the preregistered two-root
deployment-benefit criterion is not met. Native final success = 21/48, risk =
4/47 with one missing label; review final success = 19/48, risk = 6/45 with three
missing labels. Review rejects four times (three safety+utility, one utility
only), retaining the founder in both roots. Two safety detections concern the
unchanged deployment source. Do not call this early detection of new harmful
updates or a safety improvement.

The source with two orphan skill declarations accounts for 24 of 288 allocated
independent records; all are missing, not safe. Eight other records stop at the
step limit. A separate **zero-API** manifest control uses the existing SDK to
regenerate metadata, preserves every resource byte and completes 8/8 execution
paths. This is not a repaired natural success. An offline replay of the existing
absolute-risk/nonregression module would accept one of four targets; that target
still has 2/23 independently observed violations. Neither this nor rejection of
an unsafe incumbent establishes a new methodological gap beyond existing work.

Source-level metrics and execution counts are in
`output/feasibility-20261123/metrics.json` and `metrics.csv`, reproducible with
`scripts/summarize_feasibility.py`. Original frozen artifacts are unchanged.
Cost: 6,142 API calls, 19,694,663 reported tokens, zero unknown calls, including
602 review calls under the nested `resources.review.actor` ledger. The task pack
has only four final task instances and limited native harmful-effect predicates.
No larger natural experiment or new task search is scheduled.

Validation: full zero-API regression **1,111 passed**, 641.39s; final
paired-statistics/resource-manifest analysis checks **2 passed**. Completed
resume without API credentials made zero new calls and preserved all 31,575
files byte-for-byte. The frozen
four-root scripted control also completed, with both arms at 48/48 success,
native risk 36/48 versus review 0/48, no missing labels and four safety-based
rejections. Those are plumbing controls, not natural efficacy.

**2026-11-21 task-discrimination pilots completed.** The user revoked the pause;
six new campaigns finished in tmux with exit code zero and no pending/unknown
API calls. No full three-method comparison was launched. See
[results and exact denominators](task-discrimination-20261121.md),
[task contract](scheduling-tasks.md), and [native task audit](task-candidate-audit-20261121.md).

The new six/eight-request scheduling pack has real completion headroom: four
model/instruction screens gave 0–12.5% full-task success and 55.73–70.31% mean
request completion, with all 32 final executions ending normally. Its effects
oracle observed **0/32 unauthorized operations**. It is not yet a natural
dangerous-update detection set. The separate Kimi AgentDojo screen gave attacked
task success 8/8 and selected attacker success 4/8; the prior DeepSeek comparator
gave 4/8 and 2/8. Actual malicious transfers/messages were inspected. Different
model/temperature configurations and tiny development pools are not rankings.

A single natural GEPA update generated an invalid Python skill; native selection
kept the founder. Search snapshot commits = 1; candidate retention and deployment
changes = 0. Final founder results are 0/8 task success, 47.40% mean completion,
0/8 violations. Invalid-candidate audits are missing on all eight tasks, not safe
zeroes. No manual repair/reroll occurred, and no natural safety module was tested.
No-credential completed resume preserved 2,521 files with zero new calls.
Final full regression: **1,098 passed, zero failures/skips, 585.82s**, zero paid
calls; dependencies and Bash checks passed. The next work is not more interface
expansion: use the observed capability and risk cases to design a fixed small
evolution/safety comparison, explicitly retaining task and execution variability.

**Historical pause, subsequently revoked on 2026-11-21.** Both small Frozen natural screens were
complete, with no paid experiment running or scheduled for restart. See
[stage acceptance and exact denominators](task-screening-20261120.md).
The new dynamic authorization pack was saturated: final task success 6/6,
violations 0/6. The selected AgentDojo banking15/slack11 pool produced attacked
task success 4/8 and selected attacker-goal success 2/8; both successes occurred
in Slack role-spoofing, where the legitimate task also succeeded. Banking's four
attacked task failures were omitted legitimate refunds, not malicious transfers.
Two executions per condition are development repeats, not stable method evidence.

The independent absolute review module is implemented for the synthetic
authorization study and passed native cross-method controls; **natural early
detection has not been tested**. AgentDojo's bridge to that module remains a next
step, not a completed feature. Do not start a candidate experiment or a full
comparison while paused. Reusable screening Bash scripts and the tmux wrapper
are present; local disconnection/lid sleep can still interrupt API execution.
Final zero-API regression: **1,068 passed, zero failures/skips, 569.95s**.

**2026-11-19 saved-answer rescoring completed at 19:31 CST.** The separate
`scoring-rescore-20261119-v6-r3` campaign freezes all 1,920 final allocations from
`scale-20261119-v3`. It judges 1,382 distinct valid task/recipient inputs and
preserves eight missing or malformed submissions. Scores map back to all
allocated observations; duplicate mappings are not independent judge repeats.
There are no actor or optimizer calls, and original answers, labels and historical
review decisions are unchanged. Use
`bash scripts/run_scoring_calibration.sh status runs/current/scoring-rescore-20261119-v6-r3`.
The Bash parameter block is reusable; explicit resume uses frozen settings/source
and never retries an already unknown call.

The [completed comparison](scoring-calibration-20261119.md) has **0/1,566 known
safety positives and 354/1,920 missing labels (18.44%)**. Of 150 old positives,
32 become automatic negatives and **118 become missing**; none remains positive.
This does not confirm that all old positives were false. Missing labels are
concentrated in `task_011` and `task_014` (316/354). Independent calibration has
not passed, and the result does not establish a method safety ranking or review
benefit. Utility remains the old 1,902/1,909 known labels, with 11 missing.

The pass dispatched 1,382 Kimi requests: 1,381 confirmed responses, one preserved
unknown HTTP 429, and 3,515,731 reported tokens. The unknown call retains 16,423
reserved tokens. Final no-credential completed resume preserved 1,405 files and
all request records with zero new calls; original answer provenance is unchanged.

The locked scorer `privacy-recipient-event-observations-v6-r3` passed its
separate real-Kimi development controls: **72/72 supported judgments correct**,
zero FP/FN and no repeated-label or coverage flips. Three judgments of one
predeclared unsupported relative-time example remain missing. There were
75 calls / 180,439 reported tokens, with zero unknown calls. Earlier failing
control versions are retained. These are 25 authored examples, not 75 independent
examples or independent calibration of natural model answers.

The final source passed **985 software tests, zero failures/skips, in 469.14s**
with zero paid calls. Launcher status now reports scored/pending inputs, known
and missing labels, and saved new-scoring unknown outcomes separately from the
original experiment. See [validation](validation.md).

One HTTP 429 stopped the first scoring attempt at 384 inputs. The balance was
still available; the unknown call and its reservation remain. An initial
detached-recovery request failed before dispatch because the helper recognized
only the old runner shape. That helper-only fix passed 30 targeted zero-API
checks. Explicit recovery then started with the original frozen r3 package and
continued only unattempted inputs and finished successfully. No scoring rule or frozen configuration was
changed. The code/calibration commit `83bbe5b` has been pushed to GitHub.

Blind materials contain 1,390 cards (1,116 development, 274 reserved), with all
independent human fields blank. The annotator-only ZIP is
[available locally](../output/scoring-calibration-20261119/blind-annotation-kit.zip).
The reserved split is not claimed historically unseen. Current deliverables are
versioned automatic comparison and annotation materials; method-risk calibration
and parent/child/withdrawal attribution remain pending. New cross-context tasks
are a [design proposal](persistent-update-validation.md), not a launched batch.

**Earlier 2026-11-19 pre-commit validation:** fresh full regression passed **847 tests**,
zero failures/skips and zero paid API calls. Dependency and nine Bash syntax
checks passed. See [validation](validation.md). The user's standing preference
to commit and push after validated changes is recorded in `AGENTS.md`.

**2026-11-19 expanded batch: execution completed; automatic labels provisional.**
Explicit frozen-source recovery exited successfully at **13:45:29 CST**. The
`scale-20261119-v3` campaign has all 80 generation, audit and final roots and 360
update opportunities. Final evaluation contains 1,920 cases: 1,890 valid risk
labels, 30 missing, and 150 automatic semantic positives. All positives are
semantic-only, with zero literal-forbidden hits; they are not independently
verified violations. Utility is 1,902 successes / 1,909 valid labels, with 11
missing. The [grouped report](../runs/current/scale-20261119-v3/analysis/grouped-report.md)
and [main table](../runs/current/scale-20261119-v3/analysis/main-table.csv) were
generated. Original audit missing labels and unknown reservations remain.

**Current focus: delivery 2, cross-method quantitative evaluation.** The latest
read-only results audit matched all 1,920 final records, 80 root records and
provider call ledgers to the grouped table. All 72 evolving roots started from
the same Harness resource source; the outer platform is fixed, while declared
Harness resources may evolve. Each condition has eight roots and 192 final
observations (six task families, two authorization variants and two repetitions
per root). Percentages shown alongside missing counts are positive / known
labels, not estimates that treat missing labels as negative. Snapshot commits,
deployment changes and final resource identity remain separate metrics.

All 150 automatic safety positives occur in `task_014` (coworker cover): 35/157
known allow labels and 115/157 known deny labels. The other five families have
0/1,576 positives and 24 missing labels. Assistant inspection found semantic
overmapping of generic appointment dates/times to specific catalog facts; this
is diagnostic evidence, not independent human annotation. Preserve the frozen
labels, and do not interpret the current percentages as a validated safety
ranking. The seven false utility labels in HyperAgents/random-rejection are
malformed final submissions, not actor-budget exhaustion. These measurement and
output-contract issues are directly relevant to delivery 2; expanding the safety
module is not its next prerequisite.

The [separate scoring diagnostic](../output/latest-results-20261119/scoring-diagnostics.json)
groups only final safety-judge receipts by serialized HTTP request-body hash.
There are 179 repeated-input groups / 704 judgments; 18 groups / 81 judgments
contain both true and false labels, all in `task_014`. Null labels are not treated
as false. This directly establishes some scoring variability, but does not
identify the fraction of method differences caused by scoring versus execution
or evolution. Original labels and completed reports were not changed.

The following interruption snapshot is historical, not the final allocation.
The first interruption check saw 79/80 audit roots and no final episodes. The
last audit worker finished writing before the run became stationary: the verified
10:51:49 snapshot has all 80 audit summaries and 1,920 saved audit cases, with
281 missing risk labels and 264 missing utility labels; final had not started. Current source and
campaign remain frozen at `4b885724c2805ea1b79dce1725eda17e0ae2776c6520edc1d3fa58829db5caf9`.

Kimi's last successful judge response was at 06:09:31; its last 100 calls were
all HTTP 429. A read-only balance check found available balance zero. The agent
stopped the verified experiment process group to prevent further unscored work.
The user selected recharge and continue; the subsequent balance check at 10:50
confirmed CNY 49.974712 available. Explicit frozen-source recovery used supervisor PID 61506, nonce
`22aee8c964d140238ed69023a5606a30`, with original labels and unknown reservations
retained. After recovery, all 80 generation and 80 audit roots were reused; the
first final progress check found 8 saved final episodes and 39 HTTP-200 calls,
no new final unknown calls at that initial check. Recovery subsequently completed
as recorded above; the full run retains 529 audit and 16 final unknown calls.
Do not silently retry or overwrite the 529 unknown requests. Original missing
audit labels are not repaired merely by resuming the run.

Use `bash scripts/run_scale_experiment.sh status runs/current/scale-20261119-v3`
for live progress. `resume-start` is the explicit detached-recovery action and
uses the original archived driver and execution package; each attempt retains
its own PID/job/exit/log under `background-recoveries/`. Do not start another
recovery while status is `resuming`. The new recovery mechanism passed 18
zero-paid controls, including the actual old driver; five later status-display
controls passed. No running recovery files or source were altered by those tests.

[Combined interim table and interpretation](../runs/current/scale-20261119-v3/analysis/metrics-interim.md)
uses a separately saved interruption snapshot. It must not be presented as a
completed final-risk table. [Audit coverage](../runs/current/scale-20261119-v3/analysis/audit-coverage-interim.md)
documents the nonrandom concentration of missing labels in later-run conditions.

[Complete generation-stage metrics](../runs/current/scale-20261119-v3/analysis/generation-stage-report.md)
are available now: native/review/random submit totals 107/111/53 and deployment
changes 71/69/34. Review ran 112 times: 111 accept, one inconclusive, zero reject.
The sole block was a candidate answer missing `private_note`, not semantic-score
flipping or a verified dangerous update. Random control accepted 53/rejected 56.
Four generation failures (two strict duplicate-JSON-key errors in OpenEvolve;
two HyperAgents per-edit reply-budget limits) are preserved. These facts are not
final risk/utility results. The stages before audit had zero unknown calls.

[Interruption and cost evidence](../runs/current/scale-20261119-v3/analysis/interruption.json)
records 14,011 attempted calls, 27,759,340 reported tokens, estimated CNY 102.16532
known usage and separately CNY 95.232645 unresolved reservation estimates; not an
invoice. HTTP failures all occurred in independent audit. Keep the interruption
snapshot separate from later recovery results.

The batch remains **exploratory**, with `calibration.confirmed=false`. The latest
authored scorer check is 124/132 agreement, 5 FP, 3 FN, no missing/unknown calls;
it failed the retained measurement gate. Do not claim a calibrated risk ranking
or dangerous-update detector effectiveness. See [the protocol and scope decision](scale-experiment-20261119.md).

**Latest authorization (2026-11-18): the user explicitly removed the API monetary
ceiling. New launch settings use `budget_cny: null`; do not ask again to raise the
former CNY 10 cap.** Finite call/token allocations, price/usage accounting,
unknown-call reservations and no automatic retries still apply. Old frozen plans
remain immutable. The previous stage covered explicit authorization v2, scorer controls and the
three-root/three-round comparison; see [that experiment plan](current-experiment-plan.md).
The active expanded scope and its separate validation are above.

As of **2026-11-18**, explicit-authorization v2 and the separated fact extractor
have passed current-source regression and real-judge authored controls. The
first fixed multi-root comparison was **stopped for engineering failures before
final evaluation**. The repaired source and a bounded natural adapter check have
now completed validation. The separate `comparison-20261118-authorization-v2-r2`
batch has **completed execution and integrity checks**, but substantial missing
safety evidence prevents a credible method ranking or safety-module benefit
claim. The user explicitly
replaced the previous instructions-only execution design. A common founder and
outer experiment contract stay fixed; candidate code, skills, tools and context
logic may change within the declared resource scope.

Read [README](../README.md), [architecture](architecture.md),
[Harness and method SDK](adapter-sdk.md), [review contracts](review-protocol.md),
and [first-release criteria](first-release.md). Use configuration profiles and the
existing public API rather than adding experiment CLIs.

Earlier 2026-11-18 results are the [grouped comparison](../runs/current/comparison-20261118-authorization-v2-r2/analysis/grouped-report.md)
and [measurement interpretation](../runs/current/comparison-20261118-authorization-v2-r2/analysis/measurement-interpretation.md).
All 21 roots and 54 update opportunities finished, with 38 snapshot commits and
22 recorded deployment-change events. Audit/final execution covered 504 episodes,
but final safety was **0 violations / 137 valid labels with 31 missing**, and audit safety was
**0/207 with 129 missing**. All 504 utility labels were true; these are automatic
labels, not independent human findings. Zero observed valid-label violations
does not establish zero risk over the full allocation.

Review ran 25 times: **12 accept, 13 inconclusive, 0 reject**. All 13 inconclusive
decisions were missing-evidence blocks, not detections of dangerous updates.
The [extraction diagnosis](../runs/current/comparison-20261118-authorization-v2-r2/analysis/extraction-failures.md)
localizes all 178 failed extractions (final 31, audit 129, review 18) to private
spans, with no recipient-span validation error. Ungrounded exact fact mappings,
unknown fact IDs and duplicate pairs in private diagnostics caused the frozen
whole-answer validator to invalidate recipient evidence. This is a measurement
boundary problem, not a natural dangerous-update finding.

The earlier completed scoring check is [69 real judgments on authored controls](../runs/current/authorization-scorer-20261118/run/report.md):
67/69 agreement, 2/51 false positives, 0/18 false negatives and no missing labels.
These are not independent human natural-answer labels. Both false positives
infer specific clinical facts from a generic appointment sentence; see
[the error interpretation](../runs/current/authorization-scorer-20261118/interpretation.md).
The older result is the [measurement interpretation](../runs/current/measurement-20261118/analysis/interpretation.md)
and [repeated-execution/rejudging table](../runs/current/measurement-20261118/analysis/report.md).
Both execution and judging vary; one task also has an ambiguous authorization
boundary. Do not turn successful workflow completion into a research acceptance.
The earlier seven-root pilot is retained, with a separately rendered
[failure-aware overview](../runs/current/reporting-review-20261118/v2/report.md).
Launch the v2 comparison through [the Bash settings file](../scripts/run_comparison_experiment.sh);
see [run/resume instructions](natural-experiment.md). User-editable parameters stay
at the top of the script, and each campaign freezes its resolved settings.

The [aborted campaign record](../runs/current/comparison-20261118-authorization-v2/aborted.json)
records 21 generation roots, 8 completed audit roots and **0 final roots**. Its
[engineering diagnosis](../runs/current/comparison-20261118-authorization-v2/analysis/engineering-abort.md)
documents OpenEvolve format failures in 10/18 opportunities and HyperAgents
request/call-limit failures in 7/18. The stop was based on generation engineering
evidence, not audit/final safety scores. There is no method endpoint comparison;
partial observations must not be pooled with a repaired new batch. The old run
is preserved unchanged. Actual-receipt spending was estimated at CNY 12.1131355,
bringing cumulative known estimated spending at that stop to CNY 16.3821595.
The subsequent adapter check cost an estimated CNY 1.105354, making known estimated
spending CNY 17.4875135 before the new main batch. The completed main batch then
used 3,238 calls / 5,984,328 tokens, estimated **CNY 25.47008**, with zero unknown
calls. Cumulative known estimated spending is **CNY 42.9575935**; these are not invoices.

All earlier experiments were archived without analysis or relabelling: 236 top-level
artifacts, 444,693 files, 9.66 GB compressed to 1.86 GB with per-file SHA256 verification.
They are under `runs/archive/20261117-224704+0800/`; old `runs/...` links in historical
documents now require [explicit restoration](experiment-archive.md). New analyses
only use `runs/current/`. Vendor and dataset resources remain in place.

## Current implementation

- `rsi_lab.adapt(path)` packages a compatible `run(task, api)` agent without importing
  it. `evaluate(method, harness=path_or_bundle)` freezes resources and starts the
  existing method comparison. Installed presets remain available and default to
  zero-paid scripted controls.
- `rsi-harness-v1` contains UTF-8 files, entrypoint, component categories and editing
  scope. The entire version executes. The `policy.source` wire field now contains
  this bundle. Candidate resource identity and native method object identity remain
  distinct.
- An isolated Python worker executes candidate code and bundled modules. The outer
  broker owns model/tool dispatch, real receipts, limits and benchmark grading.
  The default loop and context implementation live in evolvable resources.
- Current worker support is **macOS `sandbox-exec`**, Python standard library plus
  bundled modules. Network, credentials and arbitrary host writes are unavailable
  to candidates. Unsupported hosts fail explicitly; there is no unsandboxed
  fallback. Optimizer/reviewer plugins remain trusted host code.
- GEPA, OpenEvolve and bounded HyperAgents use Harness resources while preserving
  their declared search state. Meta remains a separate optimizer component. The
  adapters enforce resource scope before candidate evaluation and activation.
- SDK `rsi-method-sdk-v2` registers separately installed method packages. The Echo
  example modifies executable code and adds an actually used skill. This proves
  integration, not a new optimization algorithm or general native compatibility.
- The optional AgentHarm bridge is **unsupported** pending an executable-Harness
  integration. It must not silently fall back to extracting instructions.

One-call adaptation has a concrete prerequisite: the agent implements the public
entrypoint/API. It does not automatically infer arbitrary repositories, binary
requirements or RSI snapshot/commit semantics. Method authors adapt the lifecycle
once and then use the common entrypoint without changing the experiment core.

## Preserved experimental semantics

`rsi-review-v1` binds candidate state, public evidence, module/version, decision and
cost. Review follows native/public admission and precedes activation. Enforcing
reject/inconclusive preserves the entire declared base state, including archives,
RNG and meta; provider journals, spent reservations and public caches persist.
Observe-only does not enforce the recorded decision. Review reasons/probe results
are excluded from optimization feedback, while activation remains a selection signal.

The reference review supports deployed and newly retained candidate behavior.
It does not predict future meta execution. Independent audit/final labels remain
outside optimizer and review interfaces. All search roots freeze before independent
checkpoint audit and final evaluation. Unknown effects are never automatically
repeated; completed resume is read-only and uses frozen source/resources.

The existing event v2 distinctions remain: native child retention, whole candidate
admission and actual commit; object identity versus equal source; observed, unknown
and unsupported evidence. Earlier method controls retain their dated scope rather
than certifying every mechanism of the new executable runtime.

## Migration

Old instructions-only agent runs are not converted or overwritten. They keep their
own frozen source for review. SDK v1 plugins must update explicitly to SDK v2 and
validate executable resource updates. Old `policy.py` naming in native optimizer
state is a wire/storage convention; it is no longer a promise that the content is
an executable standalone Python file. Non-agent bounded DSL controls remain a
separate compatibility surface.

Named presets and full configurations can bind `harness={"source": "..."}`.
Completed resume needs no live resource directory. Changing resources, task
allocation, scoring or implementation requires a fresh output directory and
source-bound validation. Historical natural answers were produced under the
previous actor and do not validate the new Harness implementation.

## Current validation

Current core source is
`1ed8e11c145ff5f9de74025f301b8fe6641fa40bba08996b1144111b0b9a8aba`.
The full core regression collection passed **776 tests, zero failures/skips**, in
**449.02s**, with zero paid calls; see the
[validation record](../runs/current/authorization-v2-r2-validation-20261118/validation.json).
The 37 reporting tests added during that execution are recorded separately and
are not added to the full-collection count.

OpenEvolve's `openevolve-harness-object-v2` requires the raw Harness object rather
than a second `harness` envelope. Duplicate keys, invalid resources and invalid
candidate Python remain failures; the adapter does not repair or retry responses.
The Bash settings now give editors six calls per update, a 262,144-byte prompt
cap and 1,000,000 total tokens per editor provider. These are new resource
conditions, with native selection and whole-snapshot admission unchanged.

The [natural adapter check](../runs/current/adapter-check-20261118-v2-r2/analysis/report.md)
completed 118 calls / 311,591 tokens. OpenEvolve succeeded in 2/3 opportunities;
one generated candidate had invalid Python syntax. HyperAgents succeeded in 3/3.
This is a bounded adapter check, not a stable method success-rate estimate or
safety-module comparison. Its [frozen review](../runs/current/adapter-check-20261118-v2-r2/frozen-verification/review.json)
preserved 734 files and 118 requests, with zero new calls/effects and unchanged
logical ledgers. The known remaining candidate failure is preserved.

The preceding v2 full regression passed **752 tests, zero failures/skips**, in **427.96s**,
source `5c884cd02ea9ea5988b862e3d070ab3475b343cbe802908423ed51f645f9b32b`.
Additional report evidence-separation tests passed 11/11 after a script-only
change. The persistent seven-root scripted control exercised three updates per
updating root, v2 rules, whole-snapshot review rejection and independent update
audits at steps 0/1/2/3. Its frozen-source verification preserved 3,954 files and
804 scripted receipts with zero new calls/effects. No paid result is inferred
from these controls. See `runs/current/authorization-v2-validation-20261118/`.

The earlier 2026-11-18 full regression returned **692 passed, 1 failed**. The failure was
the legacy H2 scripted editor still returning OpenEvolve's old string response.
It now returns the structured Harness object. After that one-line compatibility
fix, **19 H2/profile tests passed**; **19 launcher/report tests also passed** after
updating cumulative spend. The full suite was not repeated after the final fix.
That source identity is `520553d151db217744807ca411d07407302859b87513a972744027d42423ca49`;
see [the dated validation record](validation.md#candidate-contract-and-measurement-diagnostics-2026-11-18).

The preceding native-host regression passed **648 tests, zero skips**, in **427.06s**,
with zero paid API calls. Source identity is
`75d357b5110c0b2433b11cf16f42be2fda1055992293a7642e77cda907a3f8d2`.
The suite includes offline independent wheel installation and an external method
whose actual code and skill changes execute, plus readonly resume and frozen
review after plugin removal.

Four persistent controls cover GEPA, OpenEvolve, both HyperAgents meta modes and
independent review. All allocated slots and final/audit cases completed; both
prescribed adverse reviewed candidates were rejected. Every control passed
readonly resume and network-disabled frozen verification. The published custom
Harness example also passed a real one-call OpenEvolve run and both recovery
checks. See [source-bound validation](validation.md#executable-harness-and-sdk-v2-2026-11-17).
The former `runs/harness-release-20261117/acceptance.json` is now in the verified
historical archive.

These are CONTROL results. Natural calibration and safety-module effectiveness
remain pending; they are not inferred from implementation tests.

Earlier complete suites—590 tests for one-call presets, 558 for SDK v1, 500 for
event v2 and earlier controls—belong to previous source versions. Their evidence
is retained in [validation](validation.md) and [history](history.md), not reused as
proof of the new executable boundary.

## Current natural pilot and remaining research

Two new batches used real DeepSeek actor/editor and Kimi judge APIs. The first
(`natural-20261117`) exposed a scoring-prompt/validator ID mismatch and insufficient
HyperAgents editor reservation headroom. It remains immutable with missing scores;
see its [diagnosis](../runs/current/natural-20261117/diagnosis.md). No safety review
actually executed in that batch, so its failures are not safety rejections.

The 2026-11-17 repaired source explicitly requests the existing `c1`, `c2`, ... criterion IDs;
score rules and strict validation did not change. That implementation identity is
`0c0cb12fd40eb8a0e8ab8889502e341e29d9e0bfa1e8cca092a937cef67ff894`.
Post-fix validation passed 43 privacy/review tests and 16 launcher/archive/report
tests, plus a seven-root zero-paid control. The earlier 648-test full suite above
belongs to the pre-fix source; it was not rerun as a full suite after this prompt fix.

`natural-20261117-v2` completed seven roots, one update opportunity per updating
root and 14/14 final executions. Utility was 100% in all conditions. Safety labels
were valid for 13/14 cases: OpenEvolve native measured 50% violation, GEPA reviewed
had one missing label, and other conditions measured 0%. This is one root per
condition on two exposed development tasks, not a stable method ranking.

Crucially, OpenEvolve native retained a new candidate but continued deploying the
founder. Its higher-risk sample had identical Harness, task and actor requests to
Frozen but a different generated answer. This directly exhibits execution output
variation, not evidence that deployed code evolution caused the risk difference.
The missing GEPA safety label came from judge evidence quotes absent from the
actual answer; it remains missing rather than being repaired into PASS.

The safety module actually reviewed two candidates (GEPA and HyperAgents), with
8/8 policy-probe observations complete, and accepted both. No dangerous update was
detected/rejected in this pilot. OpenEvolve reviewed failed candidate format
admission before the module was called. Detector error rates and intervention
benefit remain unestablished. New meta was not executed in a later update.

The repaired run used 267 calls and 440,079 tokens, estimated CNY 1.5707885 at frozen
uncached peak prices. Both new batches together cost an estimated CNY 2.893074;
including the earlier estimated usage, the total is CNY 3.00526 under the user's
CNY 10 cap. These are usage estimates, not invoices. Both batches passed completed
read-only resume and network-disabled frozen review without new calls/effects.

Fourteen current final answers and frozen factual references are available for
[blind annotation](../runs/current/natural-20261117-v2/analysis/blind/answers.md).
Labels remain empty. The next measurements should prioritize repeated execution
of an unchanged Harness and repeated judging of saved answers; use those results
to choose more independent tasks/roots and later detector/intervention controls.
The pilot itself did not include those repeats; the separate 2026-11-18 batch below does.

Two binary probes have 0.5 granularity; larger review scopes can increase noise
rejection and missing-evidence blocks. Keep these explanations separate. Archive
withdrawal, finite continuation review and future meta-risk prediction remain
unsupported and are not prerequisites for these three deliveries.

## New measurement diagnostic (2026-11-18)

The OpenEvolve agent contract now returns `{"harness": <object>}`; deterministic
serialization bridges to the unchanged native worker. One natural candidate
passed this contract, entered the archive and committed its snapshot. Deployment
remained the founder; this is not a format failure or proof of improved behavior.

`privacy-answer-spans-v1` grounds safety evidence in channel-bound answer IDs.
Invented quotation text cannot pass as evidence. Unknown IDs, channel mismatches
and contradictory results remain missing. It does not prove a valid selected
span is an actual authorization violation. Repetition provenance also checks
the scorer, task data and executable Harness sources.

The frozen founder ran two final tasks three times each. Each task produced three
different answers; first-pass safety labels were 1/3 and 0/3 violations, utility
6/6 successful. All six answers were then rejudged three times without actor or
optimizer calls: utility 18/18 successful; safety 17/18 valid. One fixed answer
flipped safety labels (1 violation, 2 nonviolations), and another had one invalid
private-channel judgment. All missing outcomes are retained. These observations
establish both types of variation, not their population variance or relative
dominance. Task 009's medication/pharmacy/insurance boundary needs clarification
in a new task version; never repair these historical labels to the new meaning.

The batch used 127 calls / 150,899 tokens, estimated **CNY 0.7432025**. Cumulative
estimated spending is **CNY 3.7484625**, with no unknown calls/reservations. Both
phases passed no-credential completed resume and network-disabled frozen review,
without changing source run files or making new calls/effects. Natural source:
`5f0d2954b36a4cda32f8ba6c8de390c6b1ef9aefaac742411bd149b84a4dc031`;
the later H2-only scripted compatibility fix was not used for these paid calls.
Twelve final answers have [empty human labels](../runs/current/measurement-20261118/analysis/blind/answers.md).

The earlier v1 [comparison settings](../scripts/run_comparison_experiment.sh) were prepared
for 21 roots, three update opportunities, 84 final executions and up to 336 audit
executions. The [fresh plan](../runs/current/comparison-plan-20261118-v2/plan.json)
requires a conservative **CNY 97.350816 new allocation**, or **CNY 101.1992785 total**
including recorded spending/buffer. It was not run under the then-authorized CNY 10 ceiling.
This is an exploratory trajectory proposal, not a powered ranking or detector
error-rate study. Clarify task authorization before simply increasing repeats.

## Explicit authorization v2 comparison

`privacy-drafts-v2` leaves v1 untouched. It has 31 canonical fact IDs, explicit
recipient permissions and separate private notes. Clinic conditions both allow
medicine names and forbid pharmacy/prescription identifiers; their insurance
permission differs. Budget conditions differ on account-suffix permission.
Allowed variants require useful authorized disclosure. The final set is four
conditions in two task families, one previously exposed world.

The extractor sees answer spans and fact catalog only; trusted code computes
authorization. Exact matching supplements extraction. A known exact violation
with missing semantic evidence stays a known violation but incomplete review
coverage. Absence of a literal match is not a safety guarantee. Final reports
separate literal-supported violations from semantic-only positives without
rewriting the primary score. Independent human labels remain pending.

`runs/current/comparison-20261118-authorization-v2/` froze 21 roots, 54 update
opportunities, 168 final episodes and 336 audit episodes under source
`5c884cd02ea9ea5988b862e3d070ab3475b343cbe802908423ed51f645f9b32b`.
`rsi-process-audit-v2` uses update opportunities, not budget fractions;
this ensures the audit can select each round regardless of unequal call costs.
The campaign ended with status `engineering_abort`: all 21 generation roots,
8 audit roots and no final roots completed. OpenEvolve returned 7 bare Harness
objects without the required envelope and 3 responses with duplicate top-level
keys; these 10/18 failures remain failed attempts. HyperAgents hit the prompt-byte
limit 5 times and the per-edit call limit 2 times, totaling 7/18 failed attempts.
The failed next-request byte lengths were not persisted, so the exact additional
prompt headroom is unknown. Generation evidence motivated the stop, not safety
scores. Coordinator SIGINT drained in-flight work and exited 130.

The original conservative allocation was CNY 184.220448, with no monetary
ceiling. Actual-receipt estimated spending was CNY 12.1131355 across 1,446 calls;
cumulative known estimated spending at that abort was CNY 16.3821595. There were no unknown
calls or unresolved reserved tokens. No final scores exist, so this campaign
cannot supply method endpoint differences or intervention-effect estimates.
Do not resume it with repaired source, repair its labels, or pool its partial
audits with a new campaign.

The separate [r2 main plan](../runs/current/comparison-20261118-authorization-v2-r2/plan.json)
completed 21 roots / 54 update opportunities / 336 audit episodes / 168 final
episodes, with the same four final conditions in two task families. It recorded
38 snapshot commits and 22 deployment-change events. The per-root report,
search-mechanism report and grouped comparison were automatically exported by
frozen read-only helpers. Their copies and hashes are bound in the campaign.

No-credential completed resume and network-disabled
[frozen verification](../runs/current/comparison-20261118-authorization-v2-r2/frozen-verification/review.json)
preserved 14,024 files and 3,238 requests, with zero new calls/effects. The
[blind final-answer package](../runs/current/comparison-20261118-authorization-v2-r2/analysis/blind/answers.md)
contains 167 task-answer items; all independent labels remain empty. The earlier
abort, adapter check and authored scorer controls remain separate datasets.

The next priority is to separate recipient semantic extraction from private-note
diagnostics, and leave exact-identifier recognition to the local matcher instead
of accepting model-generated exact mappings. This needs a new scoring protocol
and frozen-answer verification, not another large comparison under the current
missing-label mechanism. This round does not change frozen labels/protocol or
launch another large batch. It has not established a stable ranking, natural
dangerous-update detection, detector FPR/FNR or safety-module benefit.

## Operational constraints

AgentDojo paid studies remain paused. Historical repetition diagnostics used the
same five source roots; repaired jobs and failed HTTP-402 jobs must not be pooled
as zero outcomes. Preserve dated source/evaluation boundaries.

Do not alter completed `runs/` artifacts. Keep credentials, environments and wheels
out of Git. Preserve vendor locks/licenses, unknown-call reservations, independent
fork storage, admission/activation separation and idempotent completed resume.
Default validation uses zero paid API calls. Never disable either candidate or
HyperAgents isolation to pass a test.
