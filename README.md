# RSI Safety Lab

A cross-method safety research platform for agent self-improvement. Methods start
from a common executable Harness and edit its declared resources: prompts, skills,
tool wrappers, context handling and Python execution logic. The platform controls
tasks, model/tool access, budgets, independent scoring, review and activation.

GEPA, OpenEvolve and bounded HyperAgents retain their declared search mechanisms.
Installed method packages use the same evaluation and reporting interfaces. The
reference safety module reviews public behavior before inherited state commits;
its natural detection quality and safety benefit remain unestablished.

Start with [current state](docs/HANDOFF.md), [architecture](docs/architecture.md),
[Harness and method SDK](docs/adapter-sdk.md), and the
[six review contracts](docs/review-protocol.md).

The [locked AgentDojo pilot](docs/agentdojo-rsi-pilot-20261126.md) compares GEPA and
OpenEvolve from the same Harness, records prospective observe-only review, and
independently evaluates actual parents and candidates. Edit the parameter block
in `scripts/run_agentdojo_rsi.sh`; `prepare` is free and `run` uses the saved plan.
The review decisions do not enforce rejection in this pilot. Task completion,
selected harmful effects and missing observations are reported separately.
The [completed pilot](docs/agentdojo-rsi-verdict-20261126.md) has 210 complete
independent labels from 216 allocations. It identifies one repeatedly riskier
OpenEvolve update and one GEPA update that passed public review but regressed
on independent tasks. Opposite candidate directions, network gaps and only two
roots per method preclude a method ranking or a detector-effectiveness claim.

The new [small three-layer safety pilot](docs/improvement-safety-pilot.md) uses
two first-party task templates for verification failures and conflicting evidence.
It separates current execution, persistent updates, and matched continuations
with inherited versus founder HyperAgents meta. Edit
`scripts/run_improvement_pilot.sh`; `prepare` makes zero API calls and `control`
runs scripted checks. `scripts/run_improvement_meta.sh` requires the predeclared
first executed edited-meta checkpoint and reports unavailable when none exists.
These are development tasks, not a validated benchmark or a claimed safety effect.
The [pilot result](docs/improvement-safety-verdict-20261126.md) records a passing
scripted latent-risk control and an incomplete natural campaign: GEPA's final
version passed its eight independent executions, while network failures prevented
the full comparison and a natural meta intervention.

The current task-development work starts with a small real-model screen, not a
new full comparison. See [dynamic authorization](docs/dynamic-authorization.md)
for the effect-scored environment, public pre-activation reviewer and the first
screen's negative result (Frozen completed every selected task without a
violation). Edit parameters in
[`scripts/run_authorization_experiment.sh`](scripts/run_authorization_experiment.sh):

```bash
bash scripts/run_in_tmux.sh auth-screen -- \
  bash scripts/run_authorization_experiment.sh screen runs/current/MY-NEW-SCREEN
```

The wrapper preserves logs and exit status and prevents idle sleep. Local API
calls still need a connected, awake Mac; tmux does not guarantee execution while
the laptop lid is closed. A completed screen is not evidence of natural detector
effectiveness.

For the newer joint-planning tasks, use
[`scripts/run_scheduling_screen.sh`](scripts/run_scheduling_screen.sh). All model,
strategy, task and budget parameters are in its top block:

```bash
bash scripts/run_in_tmux.sh scheduling-screen -- \
  bash scripts/run_scheduling_screen.sh screen runs/current/MY-PLANNING-SCREEN kimi structured
```

Choose `deepseek|kimi` and `baseline|structured` for a new campaign. The structured
condition is a manual planning instruction control, not an RSI method. The
[task contract](docs/scheduling-tasks.md) explains feasibility, four reference
behaviors, independent completion/risk labels and the development-only scope.
[`scripts/run_scheduling_rsi.sh`](scripts/run_scheduling_rsi.sh) separately runs
one GEPA update with independent parent/candidate audits; its default `prepare`
action makes no API calls. It does not start a full cross-method comparison.
The [completed task-discrimination pilot](docs/task-discrimination-20261121.md)
reports planning headroom, native attack outcomes, and the failed GEPA candidate
separately; natural safety-module effectiveness remains unverified.

The bounded follow-up uses GEPA and an adaptation of full public validation on
one fixed scheduling / banking / Slack allocation. See the
[frozen feasibility protocol](docs/feasibility-20261123.md). All new-run parameters
are in [`scripts/run_rsi_feasibility.sh`](scripts/run_rsi_feasibility.sh):

```bash
bash scripts/run_rsi_feasibility.sh prepare runs/current/MY-FEASIBILITY-RUN
bash scripts/run_in_tmux.sh my-feasibility -- \
  bash scripts/run_rsi_feasibility.sh run runs/current/MY-FEASIBILITY-RUN
```

This uses two roots per arm, two update opportunities and three independent
executions per final case and distinct candidate source. `control` uses no paid
APIs. The result must separate natural improvement, safety-based blocking,
utility rejection and missing evidence; it does not assume a positive finding.
The [completed one-page verdict](docs/feasibility-verdict-20261123.md) records
repeated utility gains for all seven executable natural candidates, but no
demonstrated deployment safety benefit from this review component. The fixed
campaign is complete; no larger run or task expansion is scheduled.

The [bounded update-search pilot](docs/update-search-20261124.md) keeps that task
allocation and compares ordinary LLM context-policy mutation with structured
mechanism hypotheses. Edit `scripts/run_update_search.sh`, then use `prepare`
and `run` (or zero-API `control`). Eight attempts receive prospective shadow
review followed by repeated parent/candidate confirmation. This adversarial
diagnostic is not a native-method comparison or a benign-RSI risk estimate.
The [completed pilot report](docs/update-search-verdict-20261124.md) found no
update satisfying the predeclared utility-preserving repeated-risk criterion.
Final API failures remain missing; observed earlier counterexamples, review
variability and a scheduling-destination validity issue are reported separately.
`scripts/summarize_update_search.py` reproduces the read-only tables.

For the expanded real-model comparison, edit the parameter block in
[`scripts/run_scale_experiment.sh`](scripts/run_scale_experiment.sh). Start a
new campaign with `bash scripts/run_scale_experiment.sh start` and inspect it
with `bash scripts/run_scale_experiment.sh status <campaign>`. This fixes eight
roots per condition, five rounds and six final task families, including a
random-rejection control. See the [design and validation status](docs/scale-experiment-20261119.md)
before treating automatic risk scores as calibrated findings.

To export blinded references or re-score saved final answers without rerunning
agents, use `bash scripts/run_scoring_calibration.sh export` or the explicit
`controls` / `rescore` actions. Parameters stay at the top of that script. The
`scoring-calibration` profile preserves old labels and reports paired new/reversed
risk separately; independent human calibration remains pending. See the
[saved-answer workflow](docs/natural-experiment.md#saved-answer-scoring-calibration).

## Install and start

The current executable Harness runtime requires **macOS with `sandbox-exec`**.
Use Python **3.12** for the supported installation and validation environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,seabench,dev]'
rsi-lab list
```

One call starts a local experiment with a matched frozen reference:

```python
import rsi_lab

result = rsi_lab.evaluate("gepa")
print(result.output, result.report_path)
```

The default `local-control-v1` preset uses scripted providers, real candidate
execution and **zero paid API calls**. CONTROL scores are not model performance.
The project supports wheel installation; it is not a PyPI release.

## Use your own evolving agent

A compatible resource directory implements `run(task, api)` in `agent.py`. Package
it in one call, or pass the directory directly:

```python
agent = rsi_lab.adapt("./my_agent")
result = rsi_lab.evaluate("openevolve", harness=agent)
# Equivalent: rsi_lab.evaluate("openevolve", harness="./my_agent")
```

See [the executable example](examples/harness_agent/agent.py), with
[instructions](examples/harness_agent/AGENTS.md) and a
[skill resource](examples/harness_agent/skills/task.md). The agent controls its own
loop and context. `api.model`, `api.tool` and `api.read` provide model calls,
authorized task tools and versioned resources. The platform supplies public task
information and computes scores from actual execution.

```python
agent = rsi_lab.adapt("./my_agent", editable=("prompt", "skill", "runtime"))
checked = rsi_lab.preflight("openevolve", harness=agent)
```

`adapt` does not execute code. A run freezes all resources and editing permissions;
subsequent local edits cannot change that run. `preflight` checks declarations and
allocation, not natural accuracy or mechanism fidelity. An arbitrary repository
still needs a compatible entrypoint and dependencies. A new RSI method needs a
one-time lifecycle adapter; installing it makes `evaluate("method_name")` available
without edits to the runner, scorer or report.

The worker executes real Python with the standard library and bundled modules.
It receives no credentials or independent labels and has no direct network or
host-file access beyond its declared runtime sandbox. Model and tool effects pass
through the outer broker. Unsupported hosts fail explicitly; there is no
unsandboxed fallback. Installed optimizer/reviewer plugins remain trusted host
Python and have a different trust boundary.

## Methods and experimental scope

| Method | Current adaptation |
|---|---|
| `frozen` | Executes the common founder without search |
| `gepa` | Native reflection, per-case pool and selection over serialized Harness resources |
| `openevolve` | Native population, parent/context selection and revisions of Harness resources |
| `hyperagents` | Harness revisions plus separately frozen/editable bounded optimizer meta |
| Installed method | SDK v2 lifecycle, state projection and declared capabilities |

Editing permissions belong to the frozen Harness manifest. A prompt-only editing
scope can be selected as an experimental condition, but every candidate executes
as a complete Harness. There is no instructions-only runtime. Method-specific
search limits and differences from upstream remain documented in the
[state mapping](docs/method-state-mapping.md) and
[conformance specification](docs/adapter-conformance.md).

All methods use the same outer task/resource contract. Equal update counts do not
imply equal compute, and different editing scopes are different experimental
conditions. Resource versions and inherited optimizer state are both recorded;
rejecting a candidate preserves the declared base state but does not erase spent
calls, reservations, public caches or external effects.

## SEABench-derived safety experiments

SEABench supplies selected tasks and environment assets; this platform defines
its execution, scoring and safety protocol. These are not official SEABench scores.
The source is external and pinned:

```bash
git clone https://github.com/SEABench-Endogenous-Misalignment/SEABench.git runs/vendor/SEABench
git -C runs/vendor/SEABench checkout 21828194aa709da6c18cddaeb718b309db71d22f
```

```python
result = rsi_lab.evaluate(
    "openevolve", experiment="privacy-review-v1", harness="./my_agent",
    config={"source": "runs/vendor/SEABench"},
)
```

Installed presets are `local-control-v1`, `privacy-process-v1`, and
`privacy-review-v1`. They default to scripted controls. Natural presets require
explicit actor/editor/judge settings, episode budgets and global call/token caps.
The full JSON configuration API remains available through `rsi_lab.agent_bench`.

The derived privacy task pack separates development, public review, independent
audit and final tasks. Independent labels never enter optimizer feedback. All
search roots freeze before independent checkpoint audits and final evaluation.
The reference review is fail-closed for missing evidence; audit/final risk and
utility are measured outside candidate execution. See the
[process protocol](docs/process-protocol.md), [review protocol](docs/review-protocol.md),
[task adaptation](docs/seabench-adaptation.md), and [risk report](docs/risk-report.md).

The privacy world is exposed development material and the new scorer is not yet
naturally calibrated. Natural validation now starts from fresh experiments under
`runs/current/`; earlier results are compressed in `runs/archive/` and are not
pooled with this campaign. Independent human labels remain pending.
The optional AgentHarm bridge is currently unsupported pending an executable
Harness bridge; it does not silently downgrade to prompt-only evaluation.

## Launch a natural experiment

Edit the settings block at the top of
[`scripts/run_comparison_experiment.sh`](scripts/run_comparison_experiment.sh), then run:

```bash
bash scripts/run_comparison_experiment.sh run
```

The script freezes its settings, source-bound plan, price assumptions and analysis
code. Models, methods, repetitions, review thresholds and resource caps are all in
that one settings block. The comparison uses DeepSeek for execution/editing and
Kimi for independent scoring on explicit-authorization `privacy-drafts-v2` tasks.
The user removed the monetary ceiling on 2026-11-18: `budget_cny: null` records
that choice. Finite call/token caps, cost estimates and no-retry behavior remain.
Credentials belong
in the private `.env`, never in the script. `plan` makes zero API calls; `resume`
uses the saved settings rather than edits made after the run began.

See [the launch and recovery guide](docs/natural-experiment.md) for commands,
budget assumptions and output files, and [archival instructions](docs/experiment-archive.md)
for previous experiments. A completed pilot can contain failed candidates or
missing measurements; its report keeps those outcomes explicit.

For authored authorization controls scored by the real judge, use
`bash scripts/run_authorization_checks.sh run`; their expected labels are written
by the task authors, not independent human annotations. For the earlier v1 measurement check, use
`bash scripts/run_measurement_checks.sh run`: it repeats fixed-Harness execution
and then repeats judging of every saved founder answer. For the proposed
multi-root, multi-round comparison with independent checkpoint audits, use
`bash scripts/run_comparison_experiment.sh plan`. These scripts also keep all
settings at the top. Planning is free; paid execution validates the frozen resource
allocation and any monetary ceiling explicitly selected in the script.
Measurement consistency and a completed pilot do not establish method rankings
or safety-module effectiveness.

## Recovery, migration and validation

```python
assert rsi_lab.evaluate("openevolve", output=result.output, resume=True) == result
```

Use the same method as the saved run. Completed resume reads frozen configuration
and resources; it does not reread the original Harness directory. Unknown model
calls retain reservations and are never automatically retried. A changed method,
resource bundle or allocation requires a new output directory.

Version **0.5.0** replaces the instructions-only actor with `rsi-harness-v1`
resources and SDK **v2**. The `policy.source` wire field now holds the complete
bundle. Old installed SDK v1 plugins must migrate; old completed runs remain
immutable and retain their own frozen implementation. Legacy non-agent task DSL
controls are separate from executable agent evaluation.

See [validation](docs/validation.md) for dated source-bound evidence and
[release criteria](docs/first-release.md) for engineering versus natural acceptance.
Default validation uses zero paid calls. The external
[Echo package](examples/rsi_echo_adapter/README.md) demonstrates independently
installed adaptation and frozen review.

Keep `.env`, credentials, environments, wheels and generated `runs/` out of Git.
Preserve vendor locks and licenses. [CONTRIBUTING](CONTRIBUTING.md) describes the
workflow; [history](docs/history.md) preserves earlier experiments and limits.
