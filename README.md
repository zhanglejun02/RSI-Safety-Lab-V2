# RSI Safety Lab

Evaluate fixed agents and agent optimization methods through a shared actor,
native benchmark tools and independent safety scoring. The lab preserves proposals,
native selection, platform activation, checkpoints, model receipts and resource use.

The current development target is **SEABench controller optimization and downstream
safety evaluation**; see [setup and protocol](docs/seabench.md). AgentDojo runs are
paused. Other backends are **AgentDojo**, **XSTest**, and optional **AgentHarm**
through pinned Inspect Evals. `local_transfer` is a synthetic fixture.
`configs/seabench-methods.json` runs a five-group H2 controller control: frozen,
GEPA, OpenEvolve, and HyperAgents with frozen/editable meta. It uses native
per-case GEPA search state, OpenEvolve population inheritance and isolated
HyperAgents meta execution. Read the scope and observed results in the SEABench
guide; scripted success is not evidence of natural model performance.
`configs/seabench-medium.json` fixes five groups × five seeds, H5 and two final
repetitions (250 episodes). The same guide describes budgeted text submission
and the blinded saved-answer disclosure diagnostic; native scores stay intact.
The `safety-study` profile runs fixed H edits across independent roots, then one
evaluation of each frozen final policy. The initial pilot compares ordinary
agents (`frozen`) versus vanilla RSI (`openevolve`, `native_only`). A public-probe
update gate is an optional later treatment.
No learned safety method or empirical method ranking is claimed.

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

Installation downloads dependencies. The default profiles and their control
configurations use **scripted responses and zero model API calls**. They execute
actual tools, native optimizers and benchmark graders. Their scores are CONTROL
results, not model performance.

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
| `hyperagents` | Actor instructions; bounded `meta_agent.py` can be frozen or editable | macOS with `sandbox-exec` |

GEPA and OpenEvolve perform iterative instruction search. HyperAgents is a bounded
single-task integration of pinned upstream components, not a full multi-domain
reproduction. An editable meta component does not establish that a meaningful meta
update happened; inspect the recorded parent, code changes and next-edit context.

| Profile | What runs | Intended use |
|---|---|---|
| `matrix` | Selected methods × AgentDojo banking/travel and local fixture; H2 by default | Integration and extension controls |
| `banking-frozen` | One fixed policy; 10 official tasks × clean and 3 frozen attacks | Task–attack discrimination profile |
| `banking-h2` | Disjoint public/evaluation tasks; two roots per selected search method; H2; initial/final deployment; bounded rollback check | Development case finding |
| `safety-study` | Fixed H; methods × admission arms × independent seeds; public learning curves; final-only tests and root bootstrap | RSI vs RSI+safety comparisons |
| `seabench-controller` | Fixed-H AGENTS.md search on a pinned upstream sequence; frozen downstream utility/safety judging | Current controller development pilot |
| `disclosure-audit` | Blinded annotation of saved privacy-task answers; no actor execution | Separate recipient disclosure from whole-answer information presence |

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

## Freeze the selected evaluation

Backend capacity and experiment allocation are separate. List the installed
native task/attacker-goal IDs, then freeze only the selected tasks, partitions and
compatible attacks. Planning initializes native worlds to validate injection
placement, but runs no actors, graders or model API calls.

```bash
rsi-lab catalog
rsi-lab plan --config configs/agentdojo-main.json --output runs/main-control-plan.json
rsi-lab run --config configs/agentdojo-main.json --plan runs/main-control-plan.json --output runs/main-control
# Explicit HTTP diagnostic, with its own frozen plan and fresh output:
rsi-lab plan --config configs/agentdojo-main-deepseek.json --output runs/main-http-plan.json
rsi-lab run --config configs/agentdojo-main-deepseek.json --plan runs/main-http-plan.json --env-file .env --output runs/main-http
```

The current allocation is four banking development tasks, two reserved public
probe tasks (not executed), and four final tasks × (clean + three fixed attacks).
Frozen/OpenEvolve × two roots therefore evaluates **64 final episodes**, after
H2 search. The primary endpoint is role-spoofing ASR; all three attack variants,
clean/attacked utility and costs are also reported separately. The ten banking
tasks were previously inspected: `study.scope` is **screened_pool**, with recorded
screening history and exclusions. This compares methods within that pool; it
does not measure unseen-task generalization or all of AgentDojo.

`run --plan` rejects changed configuration, source or resolved cases before API
dispatch. `plan.json` records the exact allocation; `agentdojo-cases.csv` and
`agentdojo-strata.csv` preserve per-task/per-attack denominators. `costs.csv`
separates training, editor, probe and final calls/tokens. Search cost is additional
to final evaluation, and missing labels are not zero scores. The HTTP config caps
each actor phase at 600,000 tokens, with 48 training episodes, 16 final episodes
and 12 steps per episode; each search root allows two editor calls/65,536 tokens.
These are separate provider caps, not a whole-study token cap or expected use.

Use `training.suites` for several native suites in one shared-policy study; see
`configs/agentdojo-multisuite-control.json`. This eight-case four-suite control
checks interfaces only. XSTest and AgentHarm remain optional later evaluations;
supporting their data does not automatically select or execute them.
Observed HTTP diagnostics, trajectory findings and verification records are in
[validation](docs/validation.md); two-root results remain exploratory.

## Bounded root parallelism and timing

Serial is the default. Reuse the canonical study config with a small execution
overlay; the resolved settings are frozen in the plan and manifest:

```bash
rsi-lab plan --config configs/agentdojo-main.json --execution configs/execution/parallel-conservative.json --output runs/parallel-plan.json
rsi-lab run --config configs/agentdojo-main.json --execution configs/execution/parallel-conservative.json --plan runs/parallel-plan.json --output runs/parallel-control
```

Read `performance.json` and `performance-{episodes,api,roots}.csv` for timings.
`parallel-conservative.json` deliberately caps starts at 60 RPM; it is a conservative
example, not an acceleration preset. Unpaced runs explicitly use null RPM.
Use identical execution settings across scientific arms.
See [scheduling and recovery](docs/safety-study.md#scheduling-and-operational-measurements)
for limits and [validation](docs/validation.md) for measured regimes and results.

## Fixed-budget studies and optional safety arms

The earlier small vanilla pilot used `frozen` versus `openevolve`, only
`native_only`, seeds 11/22 and H2 (four roots). Both configurations use the same
ten-task banking partition and actor step limit. The reserved probe tasks are
unused: there is no probe provider, safety gate, XSTest or AgentHarm execution.
`native_only` still applies native validity/public admission.

```bash
.venv/bin/rsi-lab run --config configs/vanilla-pilot.json --output runs/vanilla-control
# Explicit paid pilot, after reviewing the control:
.venv/bin/rsi-lab run --config configs/vanilla-pilot-deepseek.json --env-file .env --output runs/vanilla-deepseek
```

These are configurations of the same runner, not separate experiment scripts.
Change methods, arms, seeds and H in a copied configuration for later studies;
preserve task partitions, model settings and budgets for paired comparisons.
Every new allocation needs a new output directory. The HTTP pilot allows two
editor calls per search root, 48 training episodes and eight final episodes per
root, with 12 actor steps per episode. Actor token caps apply separately to each
training/test provider (300,000 each); editor caps are 65,536 per search root.
These are maximum reservations, not expected use or equal total compute.
Read `learning-curves.csv`, activation records and separate usage fields in
`summary.json`; two seeds are a diagnostic pilot, not confirmatory evidence.

Prompt experiments use the same runner. `configs/agentdojo-reflection.json` adds
only public-trace error-analysis guidance for the editor;
`configs/agentdojo-selfcheck.json` changes only the common founder instructions
for both methods. Both default to scripted controls and are unvalidated prompt
hypotheses, not measured improvements. Keep these factors separate, freeze the
HTTP settings before execution, and do not tune prompts against final scores.
The [study protocol](docs/safety-study.md) explains the paper references and limits.

```bash
rsi-lab config --profile safety-study
rsi-lab run --config configs/safety-study.json --output runs/safety-control
# macOS only, all four methods:
rsi-lab run --profile safety-study --methods frozen gepa openevolve hyperagents --output runs/all-method-safety-control
```

The default study uses five independent seeds and ten distinct AgentDojo banking
tasks: four for optimization, two for public safety probes, four held out. Only
the native final policy after H slots is tested. Admission arms include
`native_only`, `probe_gate`, `reject_all`, `no_op`, `keyword` and `random`.
The shipped scripted editor deliberately introduces unsafe behavior to test the
gate; those outcomes are **CONTROL**, not measured safety improvements.

XSTest includes all 450 upstream prompts with source identity and CC-BY-4.0 notice.
AgentHarm reuses the official simulated tools and rubric graders; install its
optional dependencies and fixed dataset before selecting the broader config:

```bash
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,dev,safetybench]'
hf download ai-safety-institute/AgentHarm --repo-type dataset \
  --revision e23b3fe60a0da9037314b88e5ee3a0c054970dad \
  --include 'benchmark/*_behaviors_test_public.json' --local-dir runs/datasets/agentharm
rsi-lab run --config configs/safety-study-benchmarks.json --output runs/three-benchmark-control
```

`configs/safety-study-deepseek.json` is an explicit **paid HTTP** configuration
using the existing `.env`; it is never run by tests or default validation. Review
its allocations before starting. See [study protocol and extension guide](docs/safety-study.md)
for probe isolation, metric meanings, separate budgets, CSV curves and statistical
limits. Legacy matrix/H2 protocols retain their original checkpoint semantics.

## Real experiments and durable recovery

Before increasing RSI seeds, use the existing frozen banking profile to check
benchmark headroom. Its development pool contains ten tasks, each clean and with
three fixed attacks: important instructions, role spoofing and reconciliation
dependency. This pool preserves benign facts and uses the native attacker-goal
grader. These are screening runs; inspected tasks/attacks are development data.

```bash
.venv/bin/rsi-lab run --config configs/headroom-control.json --output runs/headroom-control
.venv/bin/rsi-lab run --config configs/headroom-frozen-deepseek.json --env-file .env --output runs/headroom-frozen-r1
.venv/bin/rsi-lab run --config configs/headroom-frozen-deepseek.json --env-file .env --output runs/headroom-frozen-r2
.venv/bin/rsi-lab run --config configs/headroom-positive-deepseek.json --env-file .env --output runs/headroom-positive
```

The optional `settings.policy` declares `role` (`baseline` or `positive_control`)
and fixed `instructions`. The positive control deliberately follows instructions
inside tool results using the actual HTTP model; it contains no attacker account,
amount or oracle label. Its results are labeled separately from ordinary agents.
The runtime, tools, tasks, payloads and grader stay identical. The scripted
configuration checks gold tool execution only; it cannot establish natural-model
attack effectiveness. The HTTP allocation is 40 episodes, at most 480 calls and
800,000 reserved tokens per run. Independent frozen repetitions have no claimed
remote model sampling seed. Compare confirmed exposure, per-task utility and
per-attack ASR in `profile.csv`; zero baseline ASR is a reason to revisit the
attack pool, not to expand the seed count or tune on the old final test set.

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

### DeepSeek smoke run (explicit API use)

`configs/deepseek-smoke.json` is an opt-in HTTP configuration for AgentDojo banking,
with a frozen actor and one OpenEvolve editing slot. Both actor and editor use
`deepseek-flash` at `https://api.deepseek.com`, with thinking disabled (see the
[official API guide](https://api-docs.deepseek.com/)). This is a small integration
run, not a method ranking or an attack-rate estimate.

Put `DEEPSEEK_API_KEY=...` in the ignored local `.env` file, then run:

```bash
chmod 600 .env
.venv/bin/rsi-lab run --config configs/deepseek-smoke.json --env-file .env --output runs/deepseek-smoke
.venv/bin/rsi-lab inspect --output runs/deepseek-smoke
# Inspect a completed run without additional API calls:
.venv/bin/rsi-lab run --config configs/deepseek-smoke.json --env-file .env --output runs/deepseek-smoke --resume
```

The allocation allows at most 72 actor calls per root (two roots), one editor call,
8 steps per episode, and 332,768 tokens across providers. These are reservation
caps, not estimated usage or a monetary guarantee. Unknown calls are not retried.
The report records actual calls, known tokens, native selection and independent
scores. Use a new output directory for each new run.

If this Python installation lacks a trusted CA bundle, add
`SSL_CERT_FILE=/absolute/path/to/cacert.pem` to `.env`. The installed `certifi`
bundle path is printed by `.venv/bin/python -m certifi`; do not disable TLS checks.

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
