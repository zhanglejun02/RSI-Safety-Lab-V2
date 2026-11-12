# SEABench controller integration

SEABench is the current development environment for controller optimization and
safety evaluation. AgentDojo experiments are paused; its integration and immutable
results remain available for later injection validation.

The [official repository](https://github.com/SEABench-Endogenous-Misalignment/SEABench)
is pinned at `21828194aa709da6c18cddaeb718b309db71d22f`. The source lock checks
151 files, including native tools/judges/session helpers, controller seeds, 89 environment JSON
files and 16 controller sequences. The external checkout is not redistributed;
planning rejects modified, missing or added files in the locked trees.

## Run through the existing CLI

```bash
git clone https://github.com/SEABench-Endogenous-Misalignment/SEABench.git runs/vendor/SEABench
git -C runs/vendor/SEABench checkout 21828194aa709da6c18cddaeb718b309db71d22f
.venv/bin/python -m pip install -e '.[agentbench,seabench,dev]'
.venv/bin/rsi-lab catalog --benchmark seabench --source runs/vendor/SEABench
.venv/bin/rsi-lab plan --config configs/seabench-controller.json --output runs/sea-plan.json
.venv/bin/rsi-lab run --config configs/seabench-controller.json --plan runs/sea-plan.json --output runs/sea-control
.venv/bin/rsi-lab review-frozen --run runs/sea-control --output runs/sea-control-review
```

The canonical config is a **zero-paid-call scripted control**: frozen/OpenEvolve,
seed 11, H1, all five upstream and five downstream tasks from
`controller_update/personal_admin/privacy`, with a 30-step cap following the
upstream runtime's 30-round default. A lab step emits one JSON action; it is not
compute-equivalent to an upstream round with possible multiple tool calls.
Prescribed control differences are
not model performance. For HTTP, save a new config with `mode: http` and explicit
actor/editor/judge `ChatConfig` settings in `models`. Use environment-variable
credential names and `--env-file .env`, then freeze a new plan. All providers,
including separate upstream/downstream judges, count toward allocation ceilings.
The existing execution overlay supports process-per-root scheduling; pilots are
serial. All methods in a comparison must share execution settings.

For execution calibration, use `configs/seabench-runtime-calibration.json` with
the same plan/run commands. Its `calibration` list selects official **upstream**
task IDs; only frozen is allowed. Each task runs once per repetition through the
usual baseline evaluator. Reporting reuses those observations without another
actor call. There is no editor, downstream actor or safety judge, and no bootstrap
method comparison. Nonempty answers and valid utility judgments are execution
checks; utility PASS is not required. This remains the current priority before
resuming optimizer experiments.

## Context and execution adaptation

The shared actor accepts benchmark-owned request/observation projections; other
backends retain their existing behavior. SEABench bridge v3 uses these fixed
settings for every method, declared in `plan.actor_context` and the backend identity:

| Setting | Default | Behavior |
|---|---:|---|
| `tool_page_chars` | 6,000 | Native tool output is retained in full; the actor receives a page with hash, total length and `next_offset` |
| `keep_recent_messages` | 3 | Calls the pinned `Session._prune_old_tool_results`; its rule retains the recent six non-system messages |
| `max_bytes` | 65,536 | Local serialized message allowance before dispatch; the model's context-window size is not inferred from this |
| `final_response_steps` | 2 | Last two calls receive a finalization notice within the original step cap; no answer is fabricated or extra call granted |

All three read-only tools accept an optional Unicode-character `offset`. Repeat
the same arguments with `next_offset` to read later pages. Pruning never promotes
tool content into the system prompt, and preserves the controller, trusted task
and latest observation. Older payloads may be pruned further to fit the byte
allowance. If protected content still cannot fit, the episode stops as budget
exhaustion. HTTP preflight reserves another 1,024 bytes for request framing.

`trace[].tool_result` retains the native result; `observed_tool_result` records
the page. Each request stores the actual outbound messages and a `context` receipt
with input/output hashes, byte counts, pruning indices and finalization status.
These receipts are audit data, not independent safety feedback.

This reuses **native deterministic pruning**, not the entire native Session.
Upstream also has LLM compaction via a subprocess, persistent session memory,
native parallel tool-call messages and checkpoint submission. The bridge uses
explicit pagination/pruning, fresh per-task history and one JSON action per step;
it makes no hidden summarizer calls. A pruning notice is not a semantic summary
and cannot preserve every earlier fact. The agent can reread evidence and must
state uncertainty when it cannot finish. If it ignores the finalization notice,
the original step-limit/missing-answer result remains. No equivalence to the full
native agent loop is claimed.

## Exact scope and measurement

The mutable policy is **AGENTS.md**. Each rollout installs the candidate into a
fresh official workspace; native controller bundling supplies the remaining fixed
instructions. Memory, tools, conversations and other workspace changes do not
persist. The founder is the sequence's official AGENTS.md setup override.

Existing method adapters perform fixed-H search over the ordered upstream suite,
using utility, observed traces and bounded public judge feedback. All roots finish
search before any frozen final policy receives the downstream list once. Hidden
prompts, rubrics and safety judgments never enter editor feedback. The actor has
no editing tool; persistent changes happen only through proposal/admission/activation.

This is a **fixed-H AGENTS.md/read-only-tool adaptation**, not reproduction of the
paper's sequential reflect-and-promote loop. Native `read_file`, `list_files`,
`find_files`, workspace seeding, task setup/loading and direct LLM-judge code are
reused. No shell, generated-code execution, file writing, memory or skill editing
is exposed. The upstream Linux/Apptainer launcher is not used. This scope fits the
selected retrieval/drafting pilot; tasks needing other tools need an explicit
adapter extension. A guard rejects option-like grep patterns; native path checks
keep access inside a fresh temporary workspace.

The actor uses the lab's JSON action protocol. Judge prompts and evidence bundling
are upstream code; the SDK transport is replaced by the durable provider with
one attempt. Incomplete criterion IDs, invalid scores and PASS/FAIL inconsistent
with “all scores >=4” are rejected as **missing**, never fabricated failed/safe
labels. No final answer means unscored utility/safety, with no judge call: an
exhausted rollout must not become a rubric-based safety violation merely because
the deliverable is absent. `task_completion` and `safety_violation` form the separate
`endogenous_safety` metric family, without injection ASR. Protocol completion,
task success, missing judgments and failed search slots remain distinct.
Exceeding the configured request-byte limit stops the episode as budget exhaustion
before dispatch. It does not raise a host failure or authorize a larger request.
The four hallucination sequences require a separate multi-call evidence
investigator; catalog marks them unsupported and planning rejects them.

No adaptive task rewriting, outcome-selected replacements or unknown-call retries
run here. Public sequences are constructed stress tests, not random deployment
samples or unseen-task evidence. Each run retains source/input hashes, phase
barrier, proposals/activations, learning curves, actor traces, raw rubric receipts,
`cases.csv`, `costs.csv` and performance files. Completed resume and frozen review
are read-only and need no external checkout. Natural judge scores require manual
rubric/trace spot checks.

The first real development pilot completed orchestration but had incomplete
downstream coverage. A longer calibration then exposed unbounded retrieval and
hit the request-byte cap before finishing generation. See
[`validation.md`](validation.md#seabench-controller-integration-2026-11-12) for
the retained failures and costs, followed by the bounded-runtime calibration.
Upstream execution calibration does not establish complete evolution/downstream
evaluation or method fidelity.

## Remaining mechanism work

Benchmark integration does not establish method fidelity or the L1/L2 hypothesis.
GEPA persistent candidate-pool/per-task selection, OpenEvolve population
inheritance and HyperAgents meta updates affecting descendants remain separate
audits. HyperAgents frozen-meta versus editable-meta is not implemented here.
Do not interpret cross-algorithm differences as an L1/L2 causal effect. Keep
failed and unchanged-policy roots; freeze methods, sequences, budgets and
repetitions before a larger comparison or independent safety gate.
