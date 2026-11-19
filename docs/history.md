# Experiment history

Historical handoff evidence retained during the documentation cleanup on
2026-11-16. This page describes the named completed experiments and their limits;
it does not authorize a new run or state that a process is active. Current work
is summarized in [HANDOFF](HANDOFF.md). See [validation](validation.md) for the
acceptance record and [legacy runbook](legacy-agent-studies.md) for old profile
commands. Local `runs/` artifacts are ignored by Git and may be absent in a clone.

## Review-protocol milestone (2026-11-16)

The protocol extension's recorded native-host acceptance passed 381 tests in
229.16 seconds without skipped HyperAgents checks. Its five-group H2 scripted
control completed 9 roots and 27 final episodes; all eight prescribed adverse
reviewed proposals were blocked. Completed resume and network-disabled frozen
review preserved original artifacts. These numbers describe that acceptance run,
not automatic validation of later source edits or natural safety effectiveness.
See the [dated record](validation.md#versioned-review-protocol-and-seabench-reference-module-2026-11-16).

## Repetition diagnostic (2026-11-13)

The repeat diagnostic completed on **2026-11-13 at 10:53 Asia/Shanghai**. Check
`runs/seabench-repeat-recovery-batch-20261113/status.json` for the final batch state.
The original batch completed saved-answer rejudging, but HTTP 402 failures spoiled
the later fixed-policy/search jobs. After the user's funding and restart approval,
the recovery batch repeated both entire planned jobs in new directories; original
unknown calls and artifacts remain unchanged. Do not confuse the old batch's
`complete` status with complete measurements, or pool it into the recovery results.

Saved-answer rejudging has 288 known records (96 answers x 3); four original missing
answers remain 12 missing records. Recovery fixed-policy evaluation has 249/250
known utility and safety labels, with one actor URLError. Recovery search has
30/30 activated continuation slots, 100/100 utility labels and 99/100 native safety
labels. Same five source seeds; repetitions are not new independent roots.

Analysis and a read-only synthesis script are in
`runs/seabench-repeat-analysis-20261113/`; start with `combined-analysis.json` and
the separate judge/fixed-policy/meta analyses. Fixed-answer utility disagreement
is 2.08% versus 12.90% across fresh executions of fixed policies; these are different
conditional samples, not an additive variance decomposition. Fixed-policy utility
withdrawal-minus-retention bounds are +11.2 to +12.0pp over all five source roots;
the exploratory five-root bootstrap sensitivity envelope is -6.4 to +32.0pp.
The planned four-complete-pair mean (+4pp) excludes seed 303, which has only one
missing label but the largest positive difference. Search repetition gives +8pp
with five-root bootstrap CI -2 to +20pp. Local withdrawal advantages in 303/404
recur, but effect sizes and other roots vary; the original historical 18pp gap is
not established as a causal meta effect. New-policy counts changed from 11/4 to
7/7 and retained/reverted token ratio from 1.64 to 1.03 across search repetitions.
Native safety differences also change direction and do not establish a ranking.
No further experiment or automatic restart was started as part of that diagnostic.

## SEABench controller and meta withdrawal (2026-11-12)

The preceding natural study targeted **SEABench upstream controller optimization
and frozen downstream safety evaluation**. AgentDojo paid experiments are paused. Use
`configs/seabench-medium.json` and `docs/seabench.md`; the pinned external checkout
stays in `runs/vendor/SEABench`. Bridge v5 preserves native task titles/system
prompts, read-only tools, rubric judges and bounded context. Five groups share the
actor: frozen, GEPA, OpenEvolve, HyperAgents frozen meta and editable meta.
GEPA now retains native per-task scores, Pareto selection, candidate pool and
sampler/RNG across slots. Public rollout caching is explicit and root-local;
only new policies get new development observations, and final tests are fresh.
HyperAgents HTTP editors now use the native text protocol through the durable
gateway. The shared actor optionally submits plain text in its last reserved
calls; tool actions and native rubric judges retain JSON. Unknown-call semantics
and isolation stay intact. Fixed final repetitions are fresh measurements within
a root, never replacement episodes or extra independent roots.

Before the review-protocol extension, the native-host suite passed **302 tests**. The 25-root H5 control, fresh
wheel installation, outside-checkout five-group control, completed resume and
frozen review pass. A real five-group × five-seed H5 study completed 100 slots and
the 250-case final allocation: 249 known utility and 247 known native safety
labels, with one unknown actor request and two inconsistent safety judgments
retained. All 20 optimizer roots changed policy; all five editable-meta roots
executed modified meta in later slots. The main study used 45.43M reported tokens.

The original exploratory completion gap was editable meta 40/50 versus frozen
meta 49/50. A targeted paired withdrawal has now completed: the same five source
roots fork before their first edited-meta invocation, continue the remaining 30
slots to H5, then execute 100 final episodes. Retained meta scores 40/49 known
utility labels; withdrawn meta scores 42/47. The three complete seed pairs give
+3.33pp (95% bootstrap -10 to +10pp); two incomplete pairs stay explicit. Two
pairs finish with identical policies but opposite score differences. This does
not attribute the original 18pp gap to meta, or establish an inherent L2 effect.

The intervention is execution/content withdrawal, not permission removal. Both
branches preserve native selection, isolation, public prefix and write rights;
the withdrawal branch executes/shows founder meta on every remaining proposal.
Edited meta is used 12 times versus zero, producing 11 versus four new policies;
selected cached dev scores stay flat. The shared runner handles this through
`meta_ablation`, without another experiment CLI.

Disclosure now uses task-specific audience cards, fixed draft boundaries and
passing fixture calibration (26/26 plus 20/20 supplementary checks). These are
assistant-authored checks, not human gold. Anonymous natural-answer review found
and fixed a post-signature evidence-heading error before joining method labels;
raw audits remain immutable. The reviewed continuation diagnostic is 1/46 versus
0/46, with four missing/disputed labels per branch; it cannot support a safety
ranking. Native labels are unchanged. Exact-request annotation reuse avoids new
calls while retaining equivalent unknown/invalid results.

Main withdrawal cost is 10.19M reported tokens; five unknown calls and 18 invalid
responses are preserved. No actor retries or replacement episodes were added.
`docs/validation.md` records costs, validation and immutable paths. Detailed local
analysis: `runs/seabench-meta-withdrawal-analysis-20261112/report.md`; the original
medium study and analysis remain unchanged.

This remains a bounded controller development bench on a known constructed
sequence, not a full official Session reproduction or unseen-task evidence.
This targeted experiment is complete; no broader matrix has been started.
Native utility judging remains sensitive to missing contact details and appended
user notes, even with useful drafts. Do not turn this into a meta-causality or
safety claim. Cross-benchmark expansion remains deferred; the new reference review
module above is validated separately through scripted controls.

## Earlier AgentDojo studies and retained workflows

The repository at this milestone contained six profiles, native source locks, controls and CI.
`safety-study` adds independent seeds × admission arms, fixed-H search, public-only
learning curves and final-only evaluation. Its `public-probe-regression-v1` gate
checks newly retained policies before activation. This is a small heuristic
reference method, not a learned or generally validated safety algorithm.

Read `docs/safety-study.md` for the protocol. AgentDojo tasks can be configured
beyond the legacy eight-case slice. XSTest has pinned data and a separate refusal
judge; AgentHarm uses optional pinned Inspect tools/scorers and local pinned data.
The three metric families are not interchangeable. Preserve the legacy run files.

Retained workflow: `catalog` → `plan --config ... --output ...` →
`run --config ... --plan ... --output ...`. The earlier `configs/agentdojo-main.json` and its
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
Parallel scheduling uses a canonical config with `--execution configs/execution/parallel-conservative.json`;
serial remains the default. See the scheduling
runbook in `docs/safety-study.md` and measured regimes in `docs/validation.md`.
Performance acceptance uses `scripts/validate_scheduling.py`, the same public
runner and pre-frozen configurations; local HTTP is its zero-paid-call default.

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
changing attacks. No five-seed formal AgentDojo study had been started at this milestone.

Wave 1/2 remain unchanged; their safety difference reversed sign and depended on
task 15. No stable causal method effect is established. At the user's direction,
cross-benchmark Wave 3 is deferred while fixed-policy variability is diagnosed.
The task-15 diagnostic completed 20 identical-policy attack repeats with 6/20
successes. The expanded banking/travel screen completed 169/180 final episodes;
11 hit the step limit amid malformed actor JSON. Banking 13/15 are development
leads, not validated primary endpoints. These frozen-policy repetitions are not
independent optimized roots or unseen-task evidence.

GEPA now gets an explicit serialized JSON example; known invalid editor replies
still consume their slots. The shared actor gets escaping guidance and a format
hint within its existing step budget. A new eight-episode development calibration
completed with zero invalid JSON, but all four attacks still succeeded. Do not
combine results across the changed actor transport. That earlier native validation
passed **253 tests**; diagnostic runs passed immutable resume and frozen-source review.
Inputs are in `runs/endpoint-inputs-20261111`; `docs/validation.md` records every
selected task, costs, source identities and limitations. No five-seed AgentDojo method
comparison, safety treatment or cross-benchmark Wave 3 has been started.

Before changing execution code, read `docs/architecture.md` and `docs/protocol.md`.
Use `docs/validation.md` for observed acceptance results and untested boundaries.
Do not turn scripted success, conditional rollback controls, or no-op meta edits
into claims about natural RSI safety. Preserve unknown outcomes and original run
artifacts; resume never replaces calls.
