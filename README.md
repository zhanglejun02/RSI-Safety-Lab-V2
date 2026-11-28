# RSI Safety Lab

A reusable safety experiment platform for agent self-improvement. GEPA,
OpenEvolve and bounded HyperAgents start from a common executable Harness and
retain their declared search mechanisms. The outer platform controls tasks,
model/tool access, budgets, review, activation and independent evaluation.

## Install and start

Use Python **3.12** and **macOS with `sandbox-exec`**, the currently supported
executable Harness host:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,seabench,dev]'
rsi-lab list
```

```python
import rsi_lab

result = rsi_lab.evaluate("gepa")
```

The default is a **zero-API scripted control**, not a natural model result.
`result.output` and `result.report_path` locate its artifacts. An existing full
experiment JSON uses the same entry point:

```python
result = rsi_lab.evaluate("gepa", config="my-experiment.json")
```

Ordinary comparisons include a separate Frozen root. Rating configurations
compare the founder and later snapshots within the selected evolving root.
`rsi_lab.preflight("gepa", config="my-experiment.json")` checks the allocation
without model calls. A single-method call selects that method; multi-method
campaigns use the same underlying runner through the Bash launchers below.

The project supports wheel installation; it is not a PyPI release.

## Use your own evolving agent

Package a compatible resource directory in one call, or pass it directly:

```python
agent = rsi_lab.adapt("./my_agent", editable=("prompt", "skill", "runtime"))
result = rsi_lab.evaluate("openevolve", harness=agent)
# Equivalent: rsi_lab.evaluate("openevolve", harness="./my_agent")
```

The directory implements `run(task, api)`; see the
[executable example](examples/harness_agent/agent.py). `api.model`, `api.tool`
and `api.read` expose brokered model calls, task tools and bundled resources.
The candidate may change its declared instructions, skills, tool wrappers,
context handling and execution loop. Every version runs as a complete Harness.

`adapt` packages resources; it does not infer an arbitrary repository's interface.
A new RSI method needs a one-time lifecycle adapter. After installing its
[SDK v2 package](docs/adapter-sdk.md), `evaluate("method_name")` uses the existing
runner and reports. The [external Echo example](examples/rsi_echo_adapter/README.md)
exercises this installation boundary.

## Methods and experimental scope

| Method | Preserved mechanism |
|---|---|
| GEPA | Native reflection, per-case candidate pool and selection |
| OpenEvolve | Native population, parent/context selection and retention |
| HyperAgents | Harness revisions and separately bounded optimizer meta |
| Frozen | Common founder without search, when the experiment calls for it |

See [state mapping](docs/method-state-mapping.md) and
[conformance](docs/adapter-conformance.md) for declared limits. Equal update
counts do not imply equal compute. Snapshot admission, archive retention and
actual deployment are different events.

| Evaluation resource | Current status |
|---|---|
| AgentDojo | Active pool: 24 native tasks in four suites; existing natural evidence is narrower |
| SEABench-derived tasks | Selected environments and derived task packs; exposed development material with calibration limits |
| XSTest | Separate text/refusal evaluation; not a tool-action risk measure |
| AgentHarm | Three paired behavior families as a baseline; native harm and separate native/corrected benign rubric scores |
| Agent-SafetyBench | Active pool: eight native scenarios; four ambiguous cases retired; derived grading, not ShieldAgent |

The [task-pool contract](docs/task-pools.md) fixes membership, sizes, exclusions
and fidelity limits before systematic experiments. `rsi-lab list` shows these
decisions. Load a selection with `rsi_lab.task_pool("agentdojo-core-v1")` or choose
its name in a Bash settings block. The shared builder freezes concrete IDs;
resume never substitutes the latest selection. Zero-risk tasks are retained as
valid baselines; failed or ambiguous measurement is recorded before retirement.

The [rating protocol v0.1](docs/safety-rating-v0.1.md) currently covers selected
AgentDojo effects. L1 checks a deployment, L2 adds its update history, and L3
adds prospectively locked continuation. Ratings bind the full configuration,
coverage and horizon; they are not certificates for method names. Risk packages
need explicit metric definitions and evidence before sharing a rating rule.

The [AgentHarm package](docs/agentharm-adaptation.md) keeps harmful completion
and benign utility as separate rubric scores with separate denominators.
`bash scripts/run_risk_suite.sh control runs/current/MY-HARM-CONTROL` validates
the current calibrated pool without paid calls. The explicit legacy native
control remains `rsi_lab.evaluate("gepa", config="configs/agentharm-native-control.json")`.
It does not inherit the AgentDojo rating thresholds.

The [Agent-SafetyBench screening contract](docs/agent-safetybench-screening.md)
uses the same fixed-version workflow. Run
`bash scripts/run_agent_safetybench_screen.sh run runs/current/MY-ASB-SCREEN`;
edit its top settings block for a new allocation. It performs no optimization.
Authored grading controls precede natural execution; all actor traces are frozen
before independent grading. It does not award safety levels.

## Launch a natural experiment

Edit models, methods, task allocation, repetitions and budgets in the top block
of [the rating launcher](scripts/run_rating_experiment.sh). Then prepare and run:

```bash
bash scripts/run_rating_experiment.sh prepare runs/current/MY-RATING
bash scripts/run_in_tmux.sh my-rating -- bash scripts/run_rating_experiment.sh run runs/current/MY-RATING
```

`prepare` makes zero API calls; `control` runs scripted validation. The natural
`run` loads credentials from the private `.env` and executes the saved plan.
Its default allocation is a small protocol pilot, **too small to award a level**.
See the [sample-size limits](docs/safety-rating-v0.1.md) before planning a grading study.

```bash
bash scripts/run_rating_experiment.sh status runs/current/MY-RATING
bash scripts/run_rating_experiment.sh resume runs/current/MY-RATING
```

Resume uses frozen settings and source, not newly edited parameters. Unknown
requests retain reservations and are never automatically retried. tmux preserves
the process and logs; API calls still need a connected, awake host. It does not
guarantee execution with the laptop lid closed.

## SEABench-derived safety experiments

The optional `privacy-process-v1` and `privacy-review-v1` presets use selected
SEABench assets with this platform's execution and measurement protocol. These
are not official SEABench scores. Source setup and task changes are documented in
[task adaptation](docs/seabench-adaptation.md) and the
[natural-experiment guide](docs/natural-experiment.md). Their older privacy
scores and uncalibrated judge results are not pooled into current AgentDojo evidence.

## Recovery, migration and validation

A completed GEPA experiment can be reopened through the same API:

```python
resumed = rsi_lab.evaluate("gepa", output=result.output, resume=True)
```

Use the method belonging to that result. Completed resume verifies saved artifacts
without constructing providers. Candidate code receives no credentials, independent
labels or activation authority. Unsupported hosts fail explicitly; isolation has
no unsandboxed fallback. Optimizer/reviewer plugins are trusted host Python.

Safety modules use the [review contract](docs/review-protocol.md). Enforced reject
or inconclusive decisions block the candidate snapshot; observe-only decisions
are recorded without blocking. Independent labels never enter search feedback.
No current result establishes a general method ranking or online safety benefit.

Version 0.5.0 uses executable resource bundles and SDK v2. Old completed runs keep
their original source and semantics. Keep credentials, environments, wheels and
generated runs out of Git; preserve vendor source locks and licenses.

| Read next | Purpose |
|---|---|
| [Architecture](docs/architecture.md) | Execution boundaries and extension contracts |
| [Current state](docs/HANDOFF.md) | Active direction and evidence status |
| [Protocol results](docs/safety-rating-verdict-20261126.md) | Current cards, metrics, missingness and limits |
| [Fixed-update confirmation](docs/agentdojo-confirmation-verdict-20261126.md) | Bounded natural update evidence, separate from ratings |
| [Validation](docs/validation.md) | Dated checks; default validation uses zero paid APIs |
| [Release criteria](docs/first-release.md) | Installation, controls and frozen-source acceptance |
| [History](docs/history.md) / [legacy runbook](docs/legacy-agent-studies.md) | Previous experiments and retained workflows |
| [Contributing](CONTRIBUTING.md) | Development, testing and source synchronization |
