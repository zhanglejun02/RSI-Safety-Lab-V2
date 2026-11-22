import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("feasibility_summary", Path(__file__).resolve().parents[2]
                                             / "scripts/summarize_feasibility.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def test_paired_risk_keeps_both_directions_and_missing_separate():
    left = [{"case_id": str(i), "repeat": 0, "utility": .5, "violation": risk}
            for i, risk in enumerate((False, True, None, False))]
    right = [{"case_id": str(i), "repeat": 0, "utility": utility, "violation": risk}
             for i, (utility, risk) in enumerate(((1, True), (0, False), (1, True), (None, None)))]
    result = summary.paired(left, right)
    assert result["allocated_pairs"] == 4 and result["utility_pairs"] == 3
    assert result["utility_delta"] == pytest.approx(1 / 6)
    assert result["new_risk"] == result["removed_risk"] == 1
    assert result["risk_pairs"] == result["risk_pairs_missing"] == 2
    assert result["risk_delta"] == 0
    with pytest.raises(ValueError):
        summary.paired(left, right[:-1])
    with pytest.raises(ValueError):
        summary.paired(left, right + right[:1])


def test_valid_python_does_not_hide_an_invalid_resource_manifest():
    from rsi_lab.harness import default_harness
    bundle = default_harness().to_dict()
    bundle["components"]["skills/absent.md"] = "skill"
    source = json.dumps(bundle)
    assert summary.syntax_errors(source) == []
    assert "component category" in summary.configuration_error(source)
    repaired = default_harness().replace(files=bundle["files"]).dumps()
    assert json.loads(repaired)["files"] == bundle["files"]
    assert summary.configuration_error(repaired) is None
