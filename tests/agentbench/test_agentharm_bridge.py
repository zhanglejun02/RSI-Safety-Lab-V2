"""Unsupported native Harness execution is rejected before optional data or calls."""
import pytest

from rsi_lab.benchmarks import agentharm, final_evaluation
from rsi_lab.errors import UnsupportedCapability


def test_agentharm_is_rejected_during_final_allocation():
    with pytest.raises(UnsupportedCapability, match="executable Harness"):
        final_evaluation.preflight({"xstest_ids": [], "agentharm": {
            "data_dir": "not-read", "split": "test_public", "behavior_ids": ["1-1"]}})


def test_agentharm_cannot_silently_project_harness_to_instructions(tmp_path):
    output = tmp_path / "must-not-start"
    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported benchmark dispatched a provider")
    with pytest.raises(UnsupportedCapability, match="instruction projection has been removed"):
        agentharm.evaluate("unused", output, {}, {}, provider_factory=forbidden)
    assert not output.exists()
