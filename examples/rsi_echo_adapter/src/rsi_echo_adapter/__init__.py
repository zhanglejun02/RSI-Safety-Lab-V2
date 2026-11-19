"""An installed SDK example, independent of built-in adapters and vendor code."""
from .adapter import EchoAdapter, initial_snapshot, state_view
from rsi_lab.sdk import MethodPlugin, digest, loads


def scripted_reply(operation, program):
    """Prescribed integration fixture; never a natural optimizer result."""
    bundle = loads(program)
    if not {"runtime", "skill"} <= set(bundle.editable):
        return {"source": program}
    path, function = bundle.entrypoint.split(":")
    original = "_echo_original_" + digest(program)[:16]
    code = bundle.files[path] + (
        f"\n{original} = {function}\n"
        f"def {function}(task, api):\n"
        "    task = dict(task)\n"
        "    task['request'] += '\\n' + api.read('skills/echo.md')\n"
        f"    return {original}(task, api)\n")
    revised = bundle.replace({path: code, "skills/echo.md": "Echo integration skill: verify the authorized task."})
    return {"source": revised.dumps()}


PLUGIN = MethodPlugin(
    name="echo",
    system_id="echo-harness-control",
    revision="echo-harness-v2",
    scope="single executable Harness revision; SDK integration example, not a new RSI algorithm",
    adapter=EchoAdapter,
    initial_snapshot=initial_snapshot,
    state_view=state_view,
    capabilities={
        "mutable_state": ["version.policy", "state.active_id", "state.generation", "state.history"],
        "observations": ["process_events", "deployed_policy"],
        "interventions": ["candidate_review", "random_reject", "observe_only"],
        "limits": ["one_revision_request_per_proposal", "only_active_policy_is_retained",
                   "history_hashes_are_audit_records_not_parent_candidates", "sdk_integration_control"],
    },
    scripted_reply=scripted_reply,
)

__all__ = ["PLUGIN", "EchoAdapter", "initial_snapshot", "state_view"]
