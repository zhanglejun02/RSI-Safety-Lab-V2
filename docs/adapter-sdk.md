# Harness and method SDK

The platform separates the evolving agent from the experiment that measures it.
A candidate is a versioned, executable Harness resource bundle. The external
platform owns tasks, model and tool access, resource accounting, independent
scoring, review and activation. Each RSI method owns its search and inheritance
mechanisms.

## One call to start, one call to package an agent

```python
import rsi_lab

result = rsi_lab.evaluate("gepa")
```

This uses the installed `local-control-v1` experiment, the default executable
Harness and scripted providers. It incurs zero paid model calls. The result is a
summary dictionary with `.output` and `.report_path` absolute paths.

Package a compatible agent directory once:

```python
agent = rsi_lab.adapt("./my_agent")
result = rsi_lab.evaluate("openevolve", harness=agent)
```

Or pass the directory directly:

```python
result = rsi_lab.evaluate("openevolve", harness="./my_agent")
```

`adapt` reads and validates resources without importing or executing candidate
code. It returns an immutable `Harness`; a run freezes its contents into the
configuration, so later directory edits do not change that run. Completed resume
uses the saved version and does not require the original resource directory:

```python
assert rsi_lab.evaluate("openevolve", output=result.output, resume=True) == result
```

This is a one-call packaging interface for agents that implement the contract
below. It does not infer arbitrary repositories' entrypoints, dependencies,
external services or optimizer state. RSI authors implement the method lifecycle
once; installing their package makes subsequent usage a one-call operation.

## Executable agent contract

See [the editable example](../examples/harness_agent/agent.py). By default a
resource directory contains `agent.py` with a public `run(task, api)` function:

```python
def run(task, api):
    response = api.model([
        {"role": "system", "content": api.read("AGENTS.md")},
        {"role": "user", "content": task["request"]},
    ], response_format="text")
    return response["text"]
```

The task contains only public request information, tool descriptions and declared
execution limits. The API exposes model calls, authorized tool calls and bundled
resource reads. Candidate code controls its loop, context and tool wrappers.
It returns a final answer; the platform computes metrics from the real execution
and benchmark evidence. A candidate cannot supply trusted grades or receipts.
Models, credentials, hidden labels and activation authority remain outside the
candidate process.

The default entrypoint is `agent.py:run`. Explicit resource categories and editing
permissions are supported:

```python
agent = rsi_lab.adapt(
    "./my_agent",
    entrypoint="agent.py:run",
    editable=("prompt", "skill", "runtime"),
)
```

Categories are `prompt`, `skill`, `tool`, `context`, `runtime`, and `config`.
`AGENTS.md`/`prompts/` map to prompt; `skills/`, `tools/`, `context/`, and `config/`
map to their corresponding categories; other resources default to runtime.
`components={path: category}` overrides inference and must cover every file.
Candidate updates must preserve the founding entrypoint and editing permissions;
changing a category cannot make a read-only resource writable. Methods may further
restrict their editable scope. The full candidate executes, including unchanged
resources. Scope changes are experimental conditions and must be reported.

Resources are UTF-8 text with bounded count, size, path length and depth. Symlinks,
case/Unicode path aliases and invalid paths are rejected before materialization.
Use a dedicated resource directory; hidden files and
`__pycache__` are excluded. Third-party Python dependencies are not automatically
vendored. The current isolated worker requires macOS `sandbox-exec` and supports the Python
standard library plus bundled modules. Linux and Windows executable-Harness
execution are unsupported. Unsupported isolation hosts fail explicitly rather
than running candidate code in the platform process.

The installed `policy` component retains its wire name but its `source` now
contains the complete serialized `rsi-harness-v1` bundle. It is not an
instructions-only Python configuration. `rsi_lab.sdk` exports `Harness`, `loads`,
`validate_candidate` and `validate_update` for adapter authors. A bundle can be
changed with `bundle.replace({"skills/check.md": "..."})`; compare it against the
parent with `validate_update(parent.dumps(), child.dumps())` before evaluation.

## Register an installed RSI method

The public extension surface is [rsi_lab.sdk](../src/rsi_lab/sdk.py), version
`rsi-method-sdk-v2`. Version 2 makes the executable Harness contract explicit;
plugins declaring the previous SDK version fail discovery rather than silently
receiving a different execution interface.

Expose a `MethodPlugin` instance through package metadata:

```toml
[project.entry-points."rsi_lab.methods"]
echo = "rsi_echo_adapter:PLUGIN"
```

After installation, start a fresh Python process and use:

```python
result = rsi_lab.evaluate("echo", harness="./my_agent")
```

The [separate Echo package](../examples/rsi_echo_adapter/README.md) imports only
the public SDK. It requests one complete Harness revision, compares public parent
and candidate utility, and retains a complete nondecreasing revision. Its scripted
control edits runtime code and adds a skill used by that code. It is an integration
example, not a new RSI method or evidence of natural safety effectiveness.

| Plugin field | Contract |
|---|---|
| `name`, `system_id`, `revision`, `scope` | Public name, implementation identity and declared method scope |
| `adapter` | Class constructed as `(directory, provider, initial_snapshot)` |
| `initial_snapshot` | `(seed, source, tool_protocol, contract, *, evaluation)` returning `SystemSnapshot` |
| `state_view` | Pure `StateView` projection; no model calls or mutations |
| `capabilities` | Lists named `mutable_state`, `observations`, `interventions`, `limits` |
| `scripted_reply` | `(operation, program)` fixture for zero-API controls |
| `platforms`, `editor_response_format` | Supported hosts and editor response format |
| `sdk_version` | Exact current SDK version |

Names must be unique, match `[a-z][a-z0-9_]*`, and not override built-ins. Snapshot
system IDs are also unique. Discovery accepts explicitly installed regular Python
packages with distribution entry-point metadata. Namespace packages, arbitrary
native extensions and configuration-file imports are outside this contract.

Installed method plugins are **trusted host Python**. Their metadata and SDK
checks are not a sandbox. The isolated candidate execution boundary does not
apply to a method's host-side optimizer implementation.

## Lifecycle, scope and state

Implement `SystemAdapter`: `describe`, `snapshot`, `fork`, `propose`, `run_task`,
`activate`, and `activation_status`. `LocalSystemAdapter` supplies durable storage
and activation receipts; the method still implements search, native selection,
snapshot validation and uncertain-proposal recovery.

`SystemSnapshot` combines a version with serializable inherited search state.
It may include archives, scores, RNG and meta state. A Harness resource snapshot
alone does not cover these optimizer objects. Declare all supported inherited
state and preserve its identity in forks, proposals and admission decisions.

`propose(operation_id, evaluator)` leaves the base unchanged and returns a bound
`CandidateDraft`. Use the supplied provider and public evaluator. Validate each
candidate's resource scope before public evaluation and again before activation.
Native child retention, native/public admission, independent review and actual
activation are separate decisions. Reject/inconclusive preserve the base's full
declared inherited state; provider journals, spent budgets and external effects
remain recorded.

Persist request identity before dispatch. An unknown result is not permission to
retry. Completed recovery returns saved evidence. Forks use independent inherited
storage and may share the supplied provider or public cache without resetting
spent budget.

`StateView(objects=(PolicyObject(native_id, source, meta_source), ...), deployed_id=...)`
records object identity separately from resource equality. IDs are unique within a
snapshot. The deployment ID identifies a retained object matching the deployed
bundle, or remains `None` if unavailable. Two objects may share resources while
having different IDs or meta. Audit history is not automatically selectable state.

Candidate evidence records `proposed_source`, `child_id`, `parent_id`,
`inspiration_ids`, `selected_id`, `native_admitted`, `platform_accepted`, and
`extra_gate` where observed. Omit unknown object IDs rather than manufacturing
identity from matching source. The platform projects retention and deployment
from the resulting snapshots; source exposure alone does not prove causal influence.

## Experiments and reports

```text
adapt(directory, *, entrypoint="agent.py:run", components=None, editable=None)
evaluate(method, output=None, *, experiment=None, config=None, review=None, harness=None, resume=False)
preflight(method, *, experiment=None, config=None, review=None, harness=None)
```

Each evaluation selects the requested method and a matched frozen reference.
Named presets are installed package data:

| Experiment | Default allocation |
|---|---|
| `local-control-v1` | Local scripted tasks and two update slots |
| `privacy-process-v1` | Derived privacy tasks, independent checkpoint audits |
| `privacy-review-v1` | Native and review arms, with separate public review probes |

The privacy presets require pinned external SEABench assets. Use `config` for
runtime settings and `harness` for the initial agent:

```python
result = rsi_lab.evaluate(
    "echo", experiment="privacy-review-v1", harness="./my_agent",
    config={"source": "/absolute/path/to/SEABench"},
)
```

`preflight` checks declarations and allocation without constructing providers or
executing the candidate. Execution, mechanism controls and natural calibration
remain marked `not_run`; capability declarations do not create absent behavior.
Supported observations are `process_events`, `deployed_policy`, `retained_policies`;
interventions are `candidate_review`, `random_reject`, `observe_only`.

Named configurations permit budget/execution/model overrides, their documented
allocation fields and a frozen `harness={"source": "..."}` binding. Task partitions,
review thresholds and report semantics remain fixed. HTTP runs require explicit
models, episode budgets and positive total call/token caps. No entrypoint infers
a paid configuration. A full configuration remains available without `experiment`.

Completed resume with no overrides reads the saved configuration and skips
preflight, directory loading and preset resolution. An explicitly supplied Harness
must match the saved bundle. Use a new output directory for a changed allocation.
The report's calibration remains unconfirmed until independent natural validation;
a generated report alone is not evidence of safety effectiveness.

## Installation and frozen review

Build the platform and example as separate wheels and install from a local wheel
directory. `tests/test_external_adapter_install.py` exercises the installed API
outside both source checkouts, read-only completed resume, and frozen review after
uninstalling the example. All default validation uses zero paid calls.

Selected plugins bind SDK/system/revision, entrypoint, distribution version and
source hashes. The frozen source archive includes supported package resources and
discovery metadata; the run's configuration contains the initial Harness resources.
Candidate snapshots contain later versions. Frozen review restores trusted archived
code and verifies completed records with fresh model/tool execution disabled.
It does not archive every binary, transitive dependency or remote service.
