# Development

Start with [README](README.md), [current work](docs/HANDOFF.md) and
[architecture](docs/architecture.md). Use Python 3.12, a fresh virtual environment
and the checked-in constraints:

```bash
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,seabench,dev]' build
python -m pip check
python -m pytest -q
```

The constraints pin resolved dependencies without machine-local paths. Native
optimizer source revisions have separate hash locks. Refresh either deliberately
and rerun the affected controls. SEABench's external pinned checkout is prepared
as described in [its guide](docs/seabench.md).

## Changes and validation

Keep first-party code local to the affected interface. Share registries and
runners; add a configuration profile instead of another experiment CLI. Register
methods in `methods.py`; review modules follow the
[versioned review contract](docs/review-protocol.md). A placeholder interface is
not a validated safety method.

Run relevant tests after changes. Execution changes must preserve unknown model
reservations, no automatic retries, snapshot identity, fork isolation, complete
rejected-state isolation, separate admission/activation and read-only completed
resume. Check feedback boundaries when changing projections, probes or reports.
All default tests and CI use scripted providers and zero paid API calls.

Executable Harness acceptance requires macOS `sandbox-exec`, including frozen,
GEPA and OpenEvolve agents. Linux can validate pure contracts and legacy non-agent
DSL controls but cannot execute the new Harness worker. HyperAgents retains its
separate macOS meta sandbox. A skipped isolation check is not a native-host
acceptance pass. Never remove isolation to make a test succeed.

Protocol controls establish wiring, not natural effectiveness. For new studies,
freeze tasks, prior exposure, endpoints, budgets and missing-result handling;
keep development/probe/final feedback separate. Review calibration must include
binary-probe granularity, noise rejection and incomplete-evidence blocking across
policy counts. Preserve old raw labels and source identities when adding an
independent diagnostic.

## Release checks

A release additionally needs the full tests, native scripted controls, a clean
wheel installation and frozen-source review:

```bash
python scripts/validate_controls.py --output runs/release-controls
python -m build
```

Use a new acceptance directory for each run. Install the built wheel in another
fresh environment with the same constraints and required extras, then execute
controls from outside the checkout to verify packaged resources and entry points.
Do not use a `.pth` pointing to another environment or copy an environment.
Record the exact source, commands, results and any skips in
[validation](docs/validation.md); prior test counts do not validate new changes.

For optional AgentHarm, use the `safetybench` extra and pinned dataset instructions
in the [legacy runbook](docs/legacy-agent-studies.md#fixed-budget-studies-and-optional-safety-arms).
Its tests skip when dependencies/data are absent. XSTest data ship in the wheel.
Do not combine their endpoints with injection-success metrics.

## Artifacts and portability

Git stores source, tests, profiles, constraints, documentation and small validation
records. Keep generated runs, provider databases, `.env`, credentials, wheels and
environments out of Git. Move stopped experiments with their complete journals
and matching source; a Git clone alone does not transfer experiment state.
Completed artifacts must never be edited to fit a changed implementation.
