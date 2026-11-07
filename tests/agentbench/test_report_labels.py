from rsi_lab.studies.agent_bench import _report


def test_report_labels_control_per_row_and_distinguishes_meta_capability(tmp_path):
    score = {"clean_utility": 1, "attack_successes": 0,
             "attack_labels_known": 1, "missing_episodes": 0, "incomplete_episodes": 0}
    summary = {"origin": "control", "rows": [
        {"method": method, "benchmark": "agentdojo", "suite": "banking",
         "baseline": score, "final": score}
        for method in ("frozen", "gepa", "openevolve", "hyperagents")]}
    _report(tmp_path, summary)
    text = (tmp_path / "report.md").read_text()
    assert text.count("| CONTROL |") == 4
    assert "fixed optimizer" in text and "editable meta profile" in text
    assert "not evidence that a meta edit occurred" in text
    summary["origin"] = "natural"
    _report(tmp_path, summary)
    text = (tmp_path / "report.md").read_text()
    assert "| CONTROL |" not in text
    assert text.count("| DEVELOPMENT |") == 4
    assert "deliberately abstains" not in text
    assert "scripted abstention callback is not used" in text
