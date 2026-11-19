# Independent Harness-revision adapter

This separately installable example demonstrates an external adapter using the
RSI Safety Lab SDK. It is an integration control, not a new RSI algorithm or a
reproduction of a native optimizer.

The method requests one revised executable Harness from its supplied provider,
measures it through the supplied public evaluator, and proposes an immutable
replacement snapshot. Activation is a separate platform operation. Declared
inherited state consists of the full Harness bundle and its revision history;
provider journals, spent resources and public-evaluation caches are external.

The package owns its adapter implementation and tests. It does not import a
built-in method or vendor optimizer. Its scripted response is only a zero-API
installation and protocol control; it does not measure natural model quality.
The fixture modifies the entrypoint's Python code and adds a skill that the new
code reads into the public request. It therefore exercises executable resources,
not an instructions-only configuration. Read-only component scopes are preserved.

Installation acceptance builds this distribution and the platform as separate
wheels, installs them into a fresh environment without editable packages, and
calls the public interface from outside either checkout. The controls verify
proposal, public evaluation, separate activation, rejection, independent fork
storage and completed recovery without another provider call.

From the platform checkout, run the focused source controls and the independent
installation acceptance:

```bash
python -m pytest -q tests/test_external_adapter.py tests/test_external_adapter_install.py
```

The installation test builds both wheels from temporary source copies, installs
only `rsi-echo-adapter` plus its declared platform dependency from a local wheel
directory, and invokes `rsi-lab list` and the Python run API from an unrelated
working directory. It verifies that both imports come from the new environment's
`site-packages`, that plugin source/discovery metadata enter the frozen archive,
and that a completed resume leaves every output file unchanged. It then uninstalls
the example from this temporary environment and runs `rsi-lab review-frozen`,
verifying that the archived package and distribution metadata alone restore
plugin discovery. Frozen review must preserve the input run and logical ledgers
without model calls or new environment effects. This test does not install the
example into the development environment or access package indexes.

After installing the example wheel in your own environment, use the existing
platform API:

```python
from rsi_lab.agent_bench import evaluate

summary = evaluate("echo", "runs/echo-control")
# A compatible run(task, api) agent can also be packaged directly:
# summary = evaluate("echo", harness="./my_agent")
```

This default includes a matched frozen reference and uses the local scripted
task control. Natural evaluation requires an explicitly supplied configuration.

The method's declared rule accepts a complete, scored revision only when its
public utility does not decrease from the measured parent. There is one retained
policy object. Earlier IDs/source hashes/scores remain in revision history for
auditing, but are not selectable parents and do not enter the next editor prompt.
Unknown proposals retain their intent and provider reservation; the adapter
refuses to restart them. A fork uses separate inherited storage and shares the
supplied provider, so it does not create a new resource budget.
