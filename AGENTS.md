# Working in this repository

- Start with `README.md`, `docs/HANDOFF.md` and `docs/architecture.md`.
- The public entry points are `rsi-lab` and `rsi_lab.agent_bench`; method selection
  belongs in `methods.py`. Add configuration profiles instead of experiment CLIs.
- Preserve unknown-call reservations, no automatic retries, snapshot identity,
  fork isolation, admission/activation separation and idempotent completed resume.
- Never expose independent benchmark labels or attack metadata to optimization
  feedback. Missing labels are not zero. Scripted controls are not natural results.
- Do not disable isolation to make HyperAgents work on an unsupported host.
- Run relevant tests after changes. For a release, run the full tests, native
  scripted controls, clean installation and frozen-source review. All default
  validation must use zero paid API calls.
- Keep generated runs, `.env`, credentials, environments and wheels out of Git.
  Never alter completed run artifacts to match changed source.
- Keep first-party code clear and local to the affected interface. Preserve vendor
  source locks and licenses. An independent safety method requires its own protocol
  and validation; it is not enabled by a placeholder interface.
