# Three risk pools before systematic experiments

The current priority is **Safety Lab + multi-risk requirements**: first freeze
usable task pools and measurement semantics, then run systematic comparisons.
Do not keep adding tasks, launchers or rating levels while their environments or
graders remain unresolved. Pool v1 is a bounded development allocation, not a
claim that these counts suffice for general safety ratings.

## Frozen size and role

| Pool | Fixed membership | Allocation | Role |
|---|---|---|---|
| `agentdojo-core-v1` | 24 native tasks, six in each of Banking, Slack, Travel, Workspace | 4 clean development tasks; 4 probe and 16 heldout tasks each with clean + two attack conditions: 4/12/48 episodes before repeats | Main injection/effect coverage |
| `agentharm-core-v1` | Three base behaviors (`9-1`, `28-1`, `50-1`), six benign/harmful requests | Study: 1 benign dev, 2 probes, 2 heldout; screen: all six heldout | Direct harmful-request baseline |
| `agent-safetybench-core-v1` | Eight native scenarios: 16, 24, 48, 56, 77, 89, 100, 101 | Heldout frozen-version screen only; eight safety and five applicable utility measurements/version/repeat | Operational scope/identity/parameter risks |

The exact task IDs, roles, retirement reasons and re-entry requirements live in
one installed [manifest](../src/rsi_lab/data/task_pools_v1.json). Native datasets
stay in pinned dependencies or ignored `runs/datasets/`, not copied into each
experiment. More variants, attacks or repeated executions are not more independent
tasks or search roots. The Dojo tasks have overlapping native templates and shared
environment state; these development partitions do not establish independent
family holdouts or reproduce the original benchmark's full test distribution.

The three Harm families deliberately remain a baseline. Their earlier zero harm
does not justify deleting them or calling them a representative harmfulness test.
The ASB eight are the retained part of an exposed 12-task exploratory screen;
they are not a new unseen confirmation set. All original screen outcomes remain
in their original batch, including the four removed tasks.

## Keep, retire and freeze

Accept a task into the active pool only when native tools/reset work, required
information and safety boundaries are interpretable, and prescribed safe/unsafe
behaviors receive the expected measurements. Natural discrimination and grader
reliability are recorded separately. **Zero observed violations is not a removal
criterion.** Keep stable safe tasks as coverage/baseline; do not select tasks by
whether a particular RSI update becomes worse.

| Retired ASB ID | Specific problem | What would permit a new version |
|---|---|---|
| 4 | Explicit share request but unspecified additional consent; repeat judgments disagree about authorization | Explicit consent and disclosure rules, then independent calibration |
| 54 | `period` versus `permanent` precedence is not defined by the acknowledgment-only tool | Verified permission effects, or an explicitly derived stateful environment |
| 65 | Maximize energy savings conflicts with preserving essential devices; utility judgment flips | Explicit utility priorities |
| 69 | Emergency inaction risk conflicts with this screen's refusal-safe convention | Separate omission-risk definition and validated controls |

These four are removed from the default launcher and rejected by the core pack,
including manually supplied IDs. The small original source lock, controls and
legacy `agent-safetybench-subset-v1` remain for explicit historical compatibility.
This is not permission to silently replace their completed scores. Unselected
upstream tasks stay outside the active pool; they need no local implementation.
Delete redundant launch configurations and unused new code, not the evidence
needed to audit a completed study. A new membership or scoring rule requires a
new version; a frozen campaign never re-resolves the current pool on resume.

## Fidelity and known repairs

| Layer | AgentDojo | AgentHarm | Agent-SafetyBench |
|---|---|---|---|
| Tasks/tools | Pinned original tasks, state, tool behavior and predicates | Pinned original requests, tools, rubric functions | Locked original instructions, environment classes and schemas |
| Native check | Selected safe/unsafe action controls and visible attack placement | Native invocation conversion; positive/negative rubric controls | Original tool results and reset; authored behavioral controls |
| Deliberate difference | Two frozen attacks; clean harmful-effect metric is derived | Common executable Harness; direct requests only | Common executable Harness; derived Kimi grader |
| Scoring limit | Selected attacker goals, not all unauthorized behavior | Rubric fractions, not binary harm; no refusal/semantic judges | Not the official ShieldAgent score; independent human calibration pending |
| Full paper reproduction | No: models, attack search and allocation differ | No: paper models, jailbreaks/forced first calls and full distribution differ | No: paper models, 10-round solver and ShieldAgent differ |

Original references: [AgentDojo](https://github.com/ethz-spylab/agentdojo),
[AgentHarm](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main/src/inspect_evals/agentharm),
[Agent-SafetyBench](https://github.com/thu-coai/Agent-SafetyBench/tree/74feea8de601b3a1449a93fcf70017fe61556f73).
Executable provenance is the existing source locks, not a moving branch.
Reproducing the measurement conditions is the goal; reproducing a paper's numeric
score with a different model is not a pass criterion. A task cannot be made valid
by adding harmful results. Different risk fractions retain separate denominators
and rating requirements; no pooled cross-benchmark safety percentage is defined.

`agentharm-calibrated-v2` fixes two observed differences without editing vendor
code or old runs. Tool arguments use the pinned Inspect `tool_params` conversion
(including integer amounts to float) after schema checking. Database audit text
is casefolded only in a grading copy. The actual transcript is unchanged.
Reports retain both `benign_task_completion` (explicitly derived correction) and
`benign_task_completion_native` (unmodified native rubric); harmful completion
remains native. Correct URLs, functions, successful tool events and all other
rubric checks are still required. Missing grading never becomes a zero.

ASB's transport/evidence fixes remain under its frozen v3 derived-grader protocol.
Ambiguous tasks are retired instead of adding ad hoc favorable labels. Controls
used during development are not independent validation; future ShieldAgent or
human comparisons must use separate provenance, not overwrite these labels.

## One selection, existing entry points

```python
import rsi_lab
config["training"] = rsi_lab.task_pool("agentdojo-core-v1")
# Frozen cross-risk measurement:
config["training"] = rsi_lab.task_pool("agentharm-core-v1", allocation="screen")
```

`rsi-lab list` reports sizes, capabilities and exclusions without downloading data
or calling models. In each existing Bash settings block, choose a pool:

```json
"training": {"pool": "agent-safetybench-core-v1", "allocation": "screen"}
```

The shared builder expands it to concrete IDs **before** config/plan/source
freezing. Keep model, roots, repetitions and resource settings in the Bash block.
For a custom allocation, use explicit ordinary training settings and give it a
new experiment identity; do not combine a pool reference with replacement IDs.

- Dojo: `scripts/run_agentdojo_rsi.sh` (native effect study).
- Harm: `scripts/run_risk_suite.sh` (shared evolution/review) or
  `scripts/run_frozen_risk_suite.sh` (saved versions).
- ASB: `scripts/run_agent_safetybench_screen.sh` (saved versions).
- Original Harm solver diagnosis stays separately available through
  `scripts/run_agentharm_calibration.sh`, explicitly using the old native metric.

`prepare` and `control` use zero paid calls; `run` is an explicit natural launch.
This pool-freezing change starts no paid experiment. Task counts are now bounded;
remaining prerequisites for formal ratings are natural calibration, independent
label checks where needed, per-risk thresholds, and a prospectively locked
sample-size/allocation decision. Do not present scripted controls as those results.
