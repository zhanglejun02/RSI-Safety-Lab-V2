# Development state

Current entry point: `rsi-lab` / `rsi_lab.agent_bench.run_experiment`.
Version: 0.4.0. Canonical methods: frozen, gepa, openevolve, hyperagents.

The repository contains the active agent-benchmark pipeline, three profile
configurations, native adapter source locks, controls and CI. The middle safety
layer currently supplies typed interfaces and the existing admission boundary;
an independently validated safety algorithm remains separate future work.

Default configurations are zero API controls. Natural runs require explicit HTTP
settings, a frozen allocation and a new output directory. No paid experiment is
started by installation, testing, inspection or release validation.

Before changing execution code, read `docs/architecture.md` and `docs/protocol.md`.
Use `docs/validation.md` for observed acceptance results and untested boundaries.
Do not turn scripted success, conditional rollback controls, or no-op meta edits
into claims about natural RSI safety. Preserve unknown outcomes and original run
artifacts; resume never replaces calls.
