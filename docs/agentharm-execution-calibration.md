# AgentHarm execution calibration

This prospective diagnostic compares the Lab's saved founder with the pinned
upstream **default solver**, on identical selected tasks and a common actor
budget. It does not reproduce the paper's models, full task distribution or
jailbreak results, and does not change any completed experiment.

## Differences identified before execution

| Component | Lab founder | Locked upstream default / paper |
|---|---|---|
| Model interface | JSON action in assistant text; tool results in user messages | Native function calls and tool messages |
| System instructions | Candidate AGENTS.md plus transport/trust guidance | Upstream general task-completion prompt |
| User input | JSON envelope with public case ID, request and tool schemas | Native task prompt; tools supplied separately |
| Action loop | One action per model response | Inspect tool loop; one response may contain multiple calls |
| Termination | Explicit done/answer or exhausted 24-step budget | Plain assistant answer; upstream Task normally limits 20 messages |
| Output cap | Prior saved configuration: 2,048 | Paper/default Task: 4,096 |
| Tool order | Dataset target-function order | Native task setup shuffles tools |
| Task/scoring scope | Three native model-free families | Full benchmark, including semantic and refusal judges |
| Attack condition | Direct harmful requests | Direct requests, forced first tool call, or template attack are separate conditions |

The official prompt, tool loop and native rubric are meaningful distinctions.
Their presence alone does not establish that an observed score difference is
caused by the adapter. The paper's aggregate is not a target this diagnostic
must reproduce. Primary sources: [paper §4.1 and Appendix B](https://arxiv.org/html/2410.09024v3),
[upstream solver](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/src/inspect_evals/agentharm/agents/default_agent.py),
[official options](https://ukgovernmentbeis.github.io/inspect_evals/evals/agentharm/).
Executable provenance is the existing source lock, not the moving links.

## Frozen comparison

The launcher imports only the founder from the completed AgentDojo confirmation.
It allocates three arms: executable founder, independently executed same-source
sham, and `agentharm-inspect-default-v1`. The last arm executes the installed
`default_agent()` through Inspect; it is a trusted reference, **not a candidate
Harness**, and has no candidate source hash. No RSI search or review runs.

- Fixed behaviors: `9-1`, `28-1`, `50-1`, both benign and harmful.
- Three independently executed temporal blocks: 54 episodes, three task families.
- Same DeepSeek actor and original settings: temperature zero, thinking disabled,
  2,048 output tokens, 131,072 request bytes, 120-second timeout.
- Shared ceiling: 24 actor calls and 24 dispatched simulated tool effects per
  episode. The reference supports multiple tool calls per response; execution is
  serial and follows the returned call order. It uses a 24-turn cap rather than
  the upstream Task's 20-message cap. Actual calls and effects are reported.
- Both arms use the dataset tool order. This intentionally removes upstream tool
  shuffling as a confound. Reference prompts and tool-role context remain native.
- Direct requests, automatic tool choice, no jailbreak, no forced first call,
  no distractors. The publicly released code does not include the paper's attack
  template; this test does not invent a replacement and call it reproduction.
- Same native deterministic rubric per task. Refusal/semantic model judging is
  not run; no calibrated refusal rate is inferred from tool counts.

Reference and candidate calls share the durable provider implementation's
reservation, unknown-response and replay semantics. Per-block call and token
caps are partitioned between providers, not doubled. Inspect API and sample
retries and response caching are disabled. Unknown dispatch stops its block;
explicit resume consumes the saved missing observation without retrying it.
Truncated/error executions are missing, never harmless zeros. Raw Inspect logs,
native messages, receipts and rubric components are saved outside Git.

This is a bundled execution-mode comparison: prompt, message representation and
loop differ together. A difference would justify a second controlled ablation;
it would not identify which one of those components caused it. Agreement would
only bound the diagnosis on these tasks/model/conditions, not establish full
benchmark fidelity or general safety.

## Reuse

Edit the top settings block in [the Bash launcher](../scripts/run_agentharm_calibration.sh).
It uses the existing `update-confirmation` profile and shared campaign machinery:

```bash
bash scripts/run_agentharm_calibration.sh control runs/current/harm-calibration-control
bash scripts/run_agentharm_calibration.sh prepare runs/current/harm-calibration
bash scripts/run_in_tmux.sh harm-calibration -- bash scripts/run_agentharm_calibration.sh run runs/current/harm-calibration
bash scripts/run_agentharm_calibration.sh resume runs/current/harm-calibration
```

Prepare/control make zero paid calls. Each campaign freezes its launcher, config,
plan and source. Resume uses those saved inputs. Reports keep benign rubric means,
harmful rubric means, coverage, matched differences and same-source variation
separate. Blocks are repeat measurements, not new tasks or independent search roots.
Natural results and their analysis belong in ignored `runs/current/` and `output/`.
