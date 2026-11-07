# Development

Use Python 3.12, a new virtual environment and the checked-in constraints:

```bash
python -m pip install -c requirements/constraints-py312.txt -e '.[agentbench,dev]' build
python -m pip check
python -m pytest -q
python scripts/validate_controls.py --output runs/release-controls
python -m build
```

The constraints contain resolved package versions without machine-local paths.
Native optimizer revisions additionally have packaged source hash locks. Refresh
constraints deliberately and rerun controls; an unconstrained install may resolve
different transitive dependencies. Linux is a CI target for frozen/GEPA/OpenEvolve;
HyperAgents needs macOS `sandbox-exec`. Tests requiring that boundary are marked.

For a wheel acceptance test, create another environment and install
`dist/rsi_safety_lab-0.4.0-py3-none-any.whl[agentbench]` with the same constraints.
Run from outside the checkout to verify packaged resources and CLI entry points.
Do not use a `.pth` pointing to another environment or copy a virtual environment.

Keep changes local to the relevant interface. Share durable runners and registries;
avoid independent CLI routes for each experiment. Test host invariant failures,
unknown model outcomes, rejected inheritance, snapshot isolation, and read-only
completed resume when altering execution code. Control fixtures must remain
clearly labeled. Never add a model API call to the default test suite or CI.

Run directories, provider databases, `.env`, wheels and environments are ignored
by Git. Keep them in external experiment storage when moving machines. Git stores
the source, tests, profiles, constraints, docs and small validation records.

## Connect your own GitHub remote

This repository has its own `main` branch and release tag. Create an empty GitHub
repository, then replace `YOUR_GITHUB_REPOSITORY_URL`:

```bash
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
git push origin v0.4.0
```

From another computer, clone that repository and follow the README installation
steps. No other checkout is needed. Credentials and experiment artifacts travel
separately; do not add them to Git to make a run portable.
