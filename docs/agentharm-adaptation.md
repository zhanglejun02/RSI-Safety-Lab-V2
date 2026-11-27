# AgentHarm native risk package v1

This is a selected AgentHarm integration under RSI Safety Lab's executable
Harness protocol, not an official AgentHarm aggregate, natural result or safety
rating. The same method SDK, proposal/activation flow, public review gate,
independent-evaluation barrier and completed-run inspector serve this package
and the existing AgentDojo effect package.

## Locked scope

`agentharm-native-v1` loads the existing source/data lock in
[`agentharm_source_lock.json`](../src/rsi_lab/data/agentharm_source_lock.json):
Inspect Evals 0.27.0, Inspect AI 0.3.288, dataset revision
`e23b3fe60a0da9037314b88e5ee3a0c054970dad`. It verifies installed source and local
dataset byte hashes before dispatch. Preflight does not download data or call
models. Dependencies and the dataset must remain available and unchanged for
an unfinished run; a frozen-source inspection of a completed run reads artifacts.

The three supported native rubric families are meeting arrangements (`9-*`),
financial transfers (`28-*`) and database access/audit (`50-*`). These families
have audited simulated tools and deterministic native graders. Other families,
semantic/refusal model judging, jailbreak/forced-first settings, irrelevant
tools and chat-only samples are unsupported in v1. Tool schemas, tool responses,
requests and rubric functions come from the locked package/data, without source
patches. Candidate Harness code actually runs; it is not projected into an
Inspect solver prompt. Tool invocations and final text form the private native
grading transcript. Rejected argument calls carry native tool errors and are
excluded by the locked grader. Simulation calls have no real bank, email or
external database effect.

The supplied allocation uses one benign development case (`9-1`), the benign
and harmful counterparts of `28-1` for public review, and both counterparts of
`50-1` for independent evaluation. Variants of a behavior family cannot cross
partitions. Additional variants remain dependent measurements of that family,
not new independent tasks. Native public-test material used as development is
explicitly exposed; this local partition does not inherit official test status.
No outcome-based task filtering was performed. This is an integration allocation,
not enough risk coverage for general claims.

For a frozen-version transfer without optimization or review, dev/probe may be
empty; heldout remains nonempty. The existing `update-confirmation` profile can
then use `review: null` and named-score measurement only. See the
[locked cross-risk allocation](cross-risk-transfer-20261127.md). Ordinary evolving
studies still require their development and review allocations at preflight.

## Metrics and review

| Measurement | Direction | Denominator | Interpretation |
|---|---|---|---|
| `agent_harm/benign_task_completion` | Higher | Allocated benign episodes | Mean native rubric fraction; optimization uses this only on development cases |
| `agent_harm/harmful_task_completion` | Lower | Allocated harmful episodes | Mean native rubric fraction; never an optimization reward or binary violation rate |

Native rubric subcriteria and their mean are retained, including partial credit.
Means report known labels and their separate allocated/missing counts. Missing
labels are not zero. Partial executions retain their raw rubric, but their score
is unknown for aggregate comparison and review. Root estimands are unknown if
any allocated measurement is missing. Refusal and over-refusal are **unmeasured**;
zero tool calls do not automatically imply a calibrated refusal label. A rubric
can award credit for preparatory actions; its score is not a count of successful
harmful external effects. Native rubric validity remains a separate research
question even when implementation matches the source.

The reference `public-metric-regression-v1` module is a named-score extension of
the existing relative public check. Configuration names an increasing utility
metric and a decreasing risk metric and declares regression tolerances. Evidence
contains immutable case/source hashes, applicable metric names and fractions.
Parent and candidate must have the same case-to-metric allocation. Means use
separate denominators for each metric, so benign cases cannot dilute risk.
Missing or incomplete public evidence returns `inconclusive`; enforced review
prevents the entire candidate snapshot from committing. Observe-only records
decisions without blocking. No public probe outcomes or reasons enter optimizer
feedback; all roots freeze before independent scoring. Existing binary review
records retain their original serialization and rules.

This is a finite-probe reference implementation, not a new detection algorithm
or verified natural detector. Independent candidate rubric scores are reported
without inventing binary danger labels, recall or false-positive rates. Current
AgentDojo rating v0.1 is unchanged and rejects this package for grading.
JSON metrics also omit inapplicable binary success/violation aggregates; groups
use benign/harmful strata, and binary detector accuracy is marked not applicable.

## Use

Install the existing optional dependencies, and fetch the two locked data files
outside Git if they are not already present:

```bash
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,safetybench,dev]'
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="ai-safety-institute/AgentHarm", repo_type="dataset",
    revision="e23b3fe60a0da9037314b88e5ee3a0c054970dad",
    allow_patterns=["benchmark/benign_behaviors_test_public.json",
                    "benchmark/harmful_behaviors_test_public.json"],
    local_dir="runs/datasets/agentharm",
)
PY
```

One-call zero-API control after importing `rsi_lab`:

```python
result = rsi_lab.evaluate("gepa", config="configs/agentharm-native-control.json")
```

The configuration includes the three native RSI methods and Frozen; the
single-method API selects GEPA plus its Frozen reference. To run the complete
control matrix, use the shared Bash launcher:

```bash
bash scripts/run_risk_suite.sh control runs/current/MY-AGENTHARM-CONTROL
```

For a future natural pilot, edit models, methods, task allocation, repeats and
budgets together at the top of [`run_risk_suite.sh`](../scripts/run_risk_suite.sh):

```bash
bash scripts/run_risk_suite.sh prepare runs/current/MY-AGENTHARM
bash scripts/run_in_tmux.sh agentharm -- bash scripts/run_risk_suite.sh run runs/current/MY-AGENTHARM
bash scripts/run_risk_suite.sh resume runs/current/MY-AGENTHARM
```

`prepare` makes zero API calls. `run` is the explicit paid execution step; no
natural AgentHarm run is part of this integration acceptance. The script shares
[`experiment_campaign.sh`](../scripts/experiment_campaign.sh) with the AgentDojo,
rating and feasibility launchers. New allocations do not require another driver.
The builder freezes the caller, resolved config, plan, package and shared helper;
the helper retains the historical artifact name `screen-runtime.sh`. Resume uses
those saved inputs. Older campaigns without a helper retain their saved builder,
config and source. Unknown actor calls keep reservations and are never retried.

## Provenance and limitations

Source: [AgentHarm official documentation](https://ukgovernmentbeis.github.io/inspect_evals/evals/agentharm/),
[paper](https://arxiv.org/abs/2410.09024). The upstream MIT license with its safety
research clause remains in the installed package and existing source lock.
Datasets, generated outputs, logs and credentials stay outside Git. Reference
control actions are prescribed fixtures against native simulations; they do not
show that natural optimization improves utility or increases harm.

A separate [execution calibration](agentharm-execution-calibration.md) can compare
the saved Lab founder with the pinned upstream default solver under common
direct-request conditions and budgets. This trusted reference does not replace
candidate execution or extend v1 to the paper's full attack/scoring conditions.

The previous `safety-study.evaluation.agentharm` instruction-projection route
remains rejected. Migrate explicitly to this task package; do not reinterpret
completed historical runs. Broad AgentHarm coverage, model-grader calibration,
natural cross-method results and package-specific rating thresholds are separate
work, not claims of this acceptance.
