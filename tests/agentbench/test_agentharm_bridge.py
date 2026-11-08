"""Optional native Inspect integration; no provider network or real business tools."""
import asyncio
from pathlib import Path

import pytest

pytest.importorskip("inspect_ai")
pytest.importorskip("inspect_evals")

from inspect_ai.model import ChatMessageUser, GenerateConfig
from inspect_ai.tool import ToolInfo

from rsi_lab.agent_bench import default_config
from rsi_lab.agents.runtime import source
from rsi_lab.benchmarks.agentharm import RefusalJudge, _model, evaluate, preflight
from rsi_lab.errors import ModelResponseValidationError
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.review import inventory


def test_json_bridge_native_tool_and_strict_judge(tmp_path):
    from inspect_evals.agentharm.benchmark.benign_tools import run_stable_diffusion_model
    from inspect_ai.tool import ToolDef
    tool = run_stable_diffusion_model()
    definition = ToolDef(tool)
    # Native tool metadata determines the actual schema; no generated code execution.
    arguments = {"prompt": "A peaceful mountain landscape", "image_path": ""}
    provider = ScriptedChatProvider(tmp_path / "actor.sqlite", lambda *_: {"tool": definition.name, "arguments": arguments})
    model = _model(provider, source())
    response = asyncio.run(model.api.generate([ChatMessageUser(content="Draw a landscape")],
        [ToolInfo(name=definition.name, description=definition.description, parameters=definition.parameters)],
        "auto", GenerateConfig(max_retries=0)))
    call = response.choices[0].message.tool_calls[0]
    assert call.function == definition.name
    result = asyncio.run(tool(**call.arguments))
    assert "Output image from prompt" in result
    bad = ScriptedChatProvider(tmp_path / "judge.sqlite", lambda *_: {"refusal": "unknown"})
    with pytest.raises(ModelResponseValidationError):
        asyncio.run(RefusalJudge(bad).check_refusal("Some answer"))


def test_native_agentharm_dataset_and_immutable_resume(tmp_path):
    data = Path(__file__).resolve().parents[2] / "runs/datasets/agentharm"
    if not data.exists():
        pytest.skip("Pinned optional AgentHarm data not installed; see README")
    c = default_config("safety-study")
    spec = {"data_dir": str(data), "split": "test_public", "behavior_ids": ["1-1"]}
    c["evaluation"]["agentharm"] = spec
    assert preflight(spec)["datasets"]
    common = {"root_id": "control", "method": "frozen", "arm": "native_only", "seed": 11}
    output = tmp_path / "native"
    rows = evaluate(source(), output, c, common)
    assert len(rows) == 2
    for row in rows:
        assert row["error"] is None
        assert row["metrics"]["refusal"]["mean"] == 1
        assert all(m["known"] == 1 and m["missing"] == 0 for m in row["metrics"].values())
        assert row["test_usage"]["origin"] == "control"
    before = inventory(output)
    assert evaluate(source(), output, c, common) == rows
    assert inventory(output) == before
