# RSI Safety Lab

Evaluate fixed agents and agent optimization methods through a shared actor,
native benchmark tools and independent safety scoring. The lab preserves proposals,
native selection, platform activation, checkpoints, model receipts and resource use.

The current external benchmark is **AgentDojo** (banking and travel). `local_transfer`
is a small synthetic engineering fixture. An independent safety-method interface is
available; no learned safety method is enabled and no system ranking is claimed.

## Install and run

Use Python **3.12**. From a fresh clone:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,dev]'
rsi-lab list
rsi-lab run --config configs/matrix.json --output runs/first-control
python -m pytest -q
```

Installation downloads dependencies. All supplied configurations use **scripted
responses and zero model API calls**. They execute actual tools, native optimizers
and benchmark graders. Their scores are CONTROL results, not model performance.

Once installed, the Python entry point is equally small:

```python
from rsi_lab.agent_bench import default_config, run_experiment

config = default_config()
config["methods"] = ["frozen", "openevolve"]
summary = run_experiment(config, "runs/my-control")
```

For a non-editable installation, use `python -m pip install '.[agentbench]'`.
This repository includes everything needed to build a wheel; it is not yet a
published PyPI release. Model credentials and completed experiments are external
inputs, never required just to install or run controls.

## Methods and profiles

| Method ID | Mutable components | Execution target |
|---|---|---|
| `frozen` | None; same initial actor instructions | macOS / Linux |
| `gepa` | Actor instructions; fixed GEPA optimizer | macOS / Linux |
| `openevolve` | Actor instructions; fixed native archive/search algorithm | macOS / Linux |
| `hyperagents` | Actor instructions and bounded `meta_agent.py` | macOS with `sandbox-exec` |

GEPA and OpenEvolve perform iterative instruction search. HyperAgents is a bounded
single-task integration of pinned upstream components, not a full multi-domain
reproduction. An editable meta component does not establish that a meaningful meta
update happened; inspect the recorded parent, code changes and next-edit context.

| Profile | What runs | Intended use |
|---|---|---|
| `matrix` | Selected methods × AgentDojo banking/travel and local fixture; H2 by default | Integration and extension controls |
| `banking-frozen` | One fixed policy; 10 official tasks × clean and 3 frozen attacks | Task–attack discrimination profile |
| `banking-h2` | Disjoint public/evaluation tasks; two roots per selected search method; H2; initial/final deployment; bounded rollback check | Development case finding |

```bash
rsi-lab config --profile matrix --methods frozen gepa openevolve
rsi-lab run --profile banking-frozen --output runs/banking-profile-control
rsi-lab run --profile banking-h2 --methods openevolve --output runs/paired-control
# macOS only; includes the actual isolated HyperAgents worker:
rsi-lab run --profile matrix --methods frozen gepa openevolve hyperagents --output runs/four-method-control
```

The matrix intentionally uses a weak scripted founder and successful edited
controls. The banking profiles use prescribed legitimate tool sequences, and the
H2 control introduces a known harmful instruction to test detection and rollback.
None of these fixtures is a natural safety finding.

## Real experiments and durable recovery

Generate a configuration, review its tasks, methods and budgets, then explicitly
set `mode` to `http` and provide actor/editor model settings. See
[the experiment protocol](docs/protocol.md) for configuration fields, budget
boundaries, checkpoint policy and information isolation. Use `.env.example` only
as a template; never commit a populated key file. No model API is called by `config`.

```bash
rsi-lab run --config my-frozen-config.json --env-file .env --output runs/my-experiment
rsi-lab run --config my-frozen-config.json --env-file .env --output runs/my-experiment --resume
rsi-lab inspect --output runs/my-experiment
rsi-lab review-frozen --run runs/my-experiment --output runs/my-review
```

Resume requires the original run directory and frozen configuration. Incomplete
effects or unknown model responses are not replayed or replaced. Pending calls
retain their budget reservation. A host invariant failure stops the run. A
completed run is inspected without constructing providers or executing tools.

Moving an **unfinished** experiment to another machine requires copying its whole
run directory, including SQLite journals and its matching source version; cloning
the repository alone does not copy experiment data. Archive only stopped runs.

## Development

- [Code map and extension interfaces](docs/architecture.md)
- [Evaluation and budget protocol](docs/protocol.md)
- [Development and release workflow](CONTRIBUTING.md)
- [Validation record and limits](docs/validation.md)
- [Third-party sources and licenses](THIRD_PARTY.md)

The local acceptance target is macOS / Python 3.12. CI defines macOS and Linux
jobs; HyperAgents fails closed on other hosts. Windows is not supported by the
POSIX run lock. Never substitute an unsandboxed HyperAgents worker.
