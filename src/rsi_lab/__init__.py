"""Safety evaluation and controlled update admission for self-improving systems."""

__version__ = "0.5.0"


def adapt(directory, *, entrypoint="agent.py:run", components=None, editable=None):
    """Package a directory implementing ``run(task, api)`` without executing it.

    The returned immutable Harness contains its resources, entry point and edit
    scope. This does not infer an arbitrary agent's interface or RSI lifecycle.
    """
    from .harness import Harness
    return Harness.from_directory(directory, entrypoint=entrypoint,
                                  components=components, editable=editable)


def evaluate(method, output=None, *, experiment=None, config=None, review=None,
             harness=None, resume=False):
    """Run a registered method; defaults to a zero-API installation control."""
    from .agent_bench import evaluate as run
    return run(method, output, experiment=experiment, config=config, review=review,
               harness=harness, resume=resume)


def preflight(method, *, experiment=None, config=None, review=None, harness=None):
    """Check declared capabilities and allocation without starting an experiment."""
    from .agent_bench import preflight as check
    return check(method, experiment=experiment, config=config, review=review, harness=harness)
