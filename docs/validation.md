# v0.4.0 validation

This is engineering acceptance of the active benchmark path, not a natural
experiment or a method ranking. All controls and tests use zero paid API calls.

## Observed local checks

- Fresh macOS / Python 3.12 environment: editable installation of
  `.[agentbench,dev]` and `pip check` passed. No dependency environment was reused.
- Complete repository test suite: **222 passed**, no skips on the local validation
  host. Includes local HTTP fixture and the actual HyperAgents macOS sandbox.
- Complete native matrix: **12 CONTROL roots, 18 slots, 141 episodes, 319 actor
  calls, 24 editor calls, 178 tool calls**. Native admission and platform commit:
  18 each. Active policy changes: 15. Archive-only updates: 3.
- Completed matrix resume: **2,231 files byte-identical**, no repeated calls or
  effects. Matrix counts agree with the accepted control fixture's expected
  behavior; source/protocol identities are version-specific.
- Paired H2 control is covered by the full test suite: four roots, fresh initial/
  final deployment, source inheritance and bounded 18-episode rollback. The
  prescribed harmful control yields final/rollback/sham attack counts 3/0/3.
- Frozen-source review: a completed banking v1 archive was restored in an
  independent copy, with **199 recorded requests** and **878 original files**
  unchanged. Summary hash:
  `ddcc54ab5b81cb10edc7d1da511aa3b6d1f33c80e4af2695588008cb0327b368`.
  Worker exit 0; network, model dispatch and fresh effects disabled; logical
  ledgers unchanged. The input archive is experiment data, not a dependency of
  the installed package.
- Source distribution and wheel build succeeded. A separate **fresh clone** and
  fresh virtual environment passed constrained installation, `pip check`, all
  **222 tests** (zero skips), and the complete four-method matrix. A third fresh
  environment installed only the wheel plus declared dependencies, outside any
  checkout, and passed the same four-method matrix and byte-identical resume.
  See `validation.json` for content identities and exact control counts.

## Coverage

The tests exercise public/independent information separation, task/actor identity,
unknown responses retaining budget, invalid model output versus host invariant
failures, rejection without inheritance, snapshot/fork isolation, activation
reconciliation, read-only completed resume, exact attack exposure, known native
effects despite step limits, native method wiring, method/profile validation,
frozen archive integrity and path checks.

The v2 matrix reports incomplete protocol episodes separately from genuinely
missing native labels; known utility/security is retained even at the step limit.
The engine's identity and activation checks are preserved. The execution boundary
does not gain an unsandboxed fallback.

## Limits

Linux CI is configured but has not been observed on a remote GitHub runner in
this local release. HyperAgents is macOS-only. Windows and distributed/parallel
experiment scheduling are not validated. A selected new machine still needs the
declared Python/dependencies and, for HTTP runs, its own credentials.

The constraints are a resolved Python 3.12 environment, not a wheel hash lock for
every operating system. Source locks independently verify the pinned GEPA,
OpenEvolve and HyperAgents components. CI installation catches portability drift.

AgentDojo is the one external benchmark; two suites are not two benchmarks.
Payload variants are a development attack pool, not full official attack search.
There is no validated learned safety module, natural safety ranking or causal
conclusion from these controls. No paid experiment, external publication or
GitHub push is part of this acceptance.
