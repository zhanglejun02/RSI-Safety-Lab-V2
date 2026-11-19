"""Read-only grouped tables for a completed frozen comparison; no new scoring."""
import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path

from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest


def load_reporter(campaign):
    path = campaign / "summarize.py"
    spec = importlib.util.spec_from_file_location("campaign_frozen_reporter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strata(judgments):
    result = dict.fromkeys(("allocated", "literal_scan_available", "literal_forbidden_recipient",
                           "semantic_only_positive", "extraction_incomplete", "literal_scan_unavailable"), 0)
    for judgment in judgments:
        result["allocated"] += 1
        if judgment.get("evidence_protocol") not in ("privacy-fact-authorization-v1", "privacy-fact-authorization-v2"):
            result["literal_scan_unavailable"] += 1
            continue
        result["literal_scan_available"] += 1
        literal = any(item["source"] == "literal" and item["recipient_authorized"] is False
                      and item["span_id"].startswith("recipient_") for item in judgment["fact_matches"])
        result["literal_forbidden_recipient"] += literal
        result["semantic_only_positive"] += judgment.get("passed") is False and not literal
        result["extraction_incomplete"] += judgment.get("extraction_complete") is False
    return result


def number(value):
    return "缺失" if value is None else f"{value:.4f}"


def interval(value):
    ci = value.get("ci95")
    return number(value.get("mean")) + (" [缺失]" if ci is None else f" [{number(ci[0])}, {number(ci[1])}]")


def analyze(campaign):
    campaign = Path(campaign).resolve()
    run = campaign / "run"
    if not (run / "summary.json").is_file():
        raise ValueError("Comparison summary does not exist; refuse interim analysis")
    before = inventory(run)
    summary, manifest = (read_record(run / name) for name in ("summary.json", "manifest.json"))
    config = json.loads((campaign / "config.json").read_text())
    if config != manifest["config"]:
        raise ValueError("Campaign config does not match completed manifest")
    reporter = load_reporter(campaign)
    descriptors = {root["root_id"]: root for root in manifest["roots"]}
    if len(summary["rows"]) != len(descriptors) or {row["root_id"] for row in summary["rows"]} != set(descriptors):
        raise ValueError("Summary does not contain every allocated root exactly once")
    binding = summary["allocation"]["task_pack"]
    if binding["id"] not in ("privacy-drafts-v2", "privacy-drafts-v3"):
        raise ValueError("This secondary grouping requires versioned fact authorization evidence")
    _, tasks = reporter.frozen_reference(run, summary["allocation"])
    budget = json.loads((campaign / "budget.json").read_text())
    costs = reporter.provider_costs(run, budget["rates_cny_per_million"])
    roots = [reporter.root_metrics(run, row, descriptors[row["root_id"]],
                summary["allocation"].get("initial_policy_sha256"), costs["providers"], binding["id"])
             for row in summary["rows"]]
    raw_by_id = {row["root_id"]: row for row in summary["rows"]}
    grouped, audits = defaultdict(list), defaultdict(list)
    for root in roots:
        grouped[(root["method"], root["arm"])].append(root)
        raw = raw_by_id[root["root_id"]]
        audit = raw.get("process_audit")
        if not audit:
            continue
        if audit["scope"] != "deployed_policy" or any(not c["deployed"] for c in audit["cases"]):
            raise ValueError("Declared audit grouping supports deployed-policy observations only")
        root_path = reporter.inside(run, descriptors[root["root_id"]]["path"])
        for point in audit["points"]:
            cases = [case for case in audit["cases"] if case["point"] == point["index"]]
            judgments = []
            for case in cases:
                observation = read_record(reporter.inside(root_path, case["record"]))
                if digest(observation) != case["record_sha256"]:
                    raise ValueError("Audit observation differs from stored case binding")
                judgments.append(observation["result"].get("verdict", {}).get("judgments", {}).get("safety_llm", {}))
            audits[(root["method"], root["arm"], point["index"])].append({
                "root_id": root["root_id"], "coordinate": audit["coordinate"], "fraction": point["fraction"],
                "selected_step": point["step"], "cases": cases, "evidence": strata(judgments)})
    conditions = []
    for (method, arm), group in sorted(grouped.items()):
        cases = [case for root in group for case in raw_by_id[root["root_id"]]["cases"]]
        evidence = {key: sum(root["authorization_evidence"][key] for root in group)
                    for key in ("allocated", "literal_scan_available", "literal_forbidden_recipient", "semantic_only_positive",
                                "extraction_incomplete", "literal_scan_unavailable")}
        providers = [p for p in costs["providers"] if p["root_id"] in {r["root_id"] for r in group}]
        audit_cases = [case for root in group for case in
                       (raw_by_id[root["root_id"]].get("process_audit") or {}).get("cases", [])]
        conditions.append({"method": method, "arm": arm, "root_count": len(group), "root_ids": [r["root_id"] for r in group],
            "seeds": [r["seed"] for r in group], "utility": reporter.counted_metric(cases, "task_completion"),
            "risk": reporter.counted_metric(cases, "safety_violation"), "evidence": evidence,
            "slots_allocated": sum(r["slots"]["allocated"] for r in group), "slots_committed": sum(r["slots"]["committed"] for r in group),
            "slots_failed": sum(r["slots"]["failure"]["numerator"] for r in group),
            "candidate_slots": sum(r["slots"]["observed_candidate_slots"] for r in group),
            "native_admitted_slots": sum(r["slots"]["native_admitted"] for r in group),
            "deployment_change_events": sum(len(r["deployed_resource_changes"]) for r in group),
            "founder_still_deployed_roots": sum(r["deployed_equals_founder"] is True for r in group),
            "changed_deployment_roots": sum(r["deployed_equals_founder"] is False for r in group),
            "review_executed": sum(r["review"]["executed"] for r in group),
            "review_decisions": dict(sum((Counter(r["review"]["module_decisions"]) for r in group), Counter())),
            "review_reason_codes": dict(sum((Counter(r["review"]["reason_codes"]) for r in group), Counter())),
            "random_control_decisions": dict(sum((Counter(r.get("random_control_decisions", {}))
                                                 for r in group), Counter())),
            "audit_risk": reporter.counted_metric(audit_cases, "safety_violation"),
            "audit_utility": reporter.counted_metric(audit_cases, "task_completion"),
            "api_calls": sum(r["api_calls"] for r in group),
            "reported_tokens": sum(p["reported_total_tokens"] for p in providers),
            "usage_missing_calls": sum(p["usage_missing_calls"] for p in providers),
            "estimated_cny": sum(p["known_usage_estimated_cny"] for p in providers)})
    audit_groups = []
    for (method, arm, index), group in sorted(audits.items()):
        if len({(r["coordinate"], r["fraction"]) for r in group}) != 1:
            raise ValueError("Audit point coordinates differ between grouped roots")
        cases = [case for row in group for case in row["cases"]]
        audit_groups.append({"method": method, "arm": arm, "point": index, "coordinate": group[0]["coordinate"],
            "fraction": group[0]["fraction"], "root_count": len(group),
            "selected_steps": {r["root_id"]: r["selected_step"] for r in group},
            "risk": reporter.counted_metric(cases, "safety_violation"), "utility": reporter.counted_metric(cases, "task_completion"),
            "evidence": {key: sum(r["evidence"][key] for r in group) for key in group[0]["evidence"]}})
    risk_report = summary["risk_report"]
    contrasts, skipped_contrasts = [], []
    available_groups = set(grouped)
    for row in risk_report["methods"]:
        references = {}
        if ("frozen", "native_only") in available_groups:
            references["frozen/native_only"] = row["frozen_reference"]
        else:
            skipped_contrasts.append({"method": row["method"], "arm": row["arm"],
                                      "reference": "frozen/native_only", "reason": "reference_not_allocated"})
        references.update({row["method"] + "/" + arm: value for arm, value in row["arm_references"].items() if (row["method"], arm) in available_groups})
        for reference, value in references.items():
            contrasts.append({"method": row["method"], "arm": row["arm"], "reference": reference,
                              "differences": value["differences"], "coverage": value["coverage"], "pairing": value["pairing"],
                              "direction": value["direction"], "classification": row["classification"] if reference == "frozen/native_only" else None})
    final_ids = {case["task_id"] for row in summary["rows"] for case in row["cases"]}
    result = {"protocol": "privacy-comparison-grouped-v2", "api_calls_for_analysis": 0,
              "scope": "All allocated roots and observations; pooled counts are not independent trials. No label changes or new inference.",
              "task_pack": binding, "final_conditions": len(final_ids),
              "task_families": sorted({tasks[key]["task_family"] for key in final_ids}),
              "conditions": conditions, "audit_points": audit_groups, "stored_contrasts": contrasts,
              "skipped_contrasts": skipped_contrasts,
              "audit_status": "observed" if audit_groups else "not_enabled_or_not_observed",
              "stored_inference": risk_report["inference"], "costs": costs["total"],
              "provenance": {"summary_sha256": digest(summary), "manifest_sha256": digest(manifest),
                             "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                             "frozen_reporter_sha256": hashlib.sha256((campaign / "summarize.py").read_bytes()).hexdigest(),
                             "run_inventory_sha256": digest(before)}}
    if inventory(run) != before:
        raise ValueError("Source run changed while deriving grouped report")
    return result


def render(result):
    lines = ["# 多根比较分组表", "", "所有已分配根均纳入，包括失败、未更新、仍部署 founder 的根；未按分数筛选。", "",
             "风险与效用为冻结评分器的自动标签；独立校准状态见配对报告，不能仅凭这些数值宣称方法安全排名或危险更新检出有效。", "",
             f"任务包 `{result['task_pack']['id']}`；{result['final_conditions']} 个最终授权条件、{len(result['task_families'])} 个任务家族。重复执行与允许／禁止变体不是新增独立任务。", "",
             "| 方法 / 分组 | 根 | 提交/机会 | 失败或无新候选 | 部署变化次数 | 最终founder根 | 审查动作 | 审计缺标/分配 | 自动终测效用/有效 | 自动终测违规/有效（缺失） | API调用 | tokens | 估算元 |",
             "|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|"]
    for r in result["conditions"]:
        u, s = r["utility"], r["risk"]
        audit = r['audit_risk']
        decision = r['random_control_decisions'] if r['arm'] == 'random_reject' else r['review_decisions']
        lines.append(f"| {r['method']} / {r['arm']} | {r['root_count']} | {r['slots_committed']}/{r['slots_allocated']} | {r['slots_failed']} | {r['deployment_change_events']} | {r['founder_still_deployed_roots']} | {json.dumps(decision)} | {audit['missing']}/{audit['allocated']} | {u['positive']}/{u['known']} | {s['positive']}/{s['known']}（{s['missing']}） | {r['api_calls']} | {r['reported_tokens']} | {r['estimated_cny']:.4f} |")
    lines += ["", "终测证据分层不替代主风险标签。文字命中仅覆盖具体目录值／别名；没有命中不代表安全。语义阳性可能包含提取误报。", "",
              "| 方法 / 分组 | 文字扫描/分配 | 禁止事实文字命中 | 仅语义阳性 | 提取不完整 |",
              "|---|---:|---:|---:|---:|"]
    for r in result["conditions"]:
        e = r["evidence"]
        lines.append(f"| {r['method']} / {r['arm']} | {e['literal_scan_available']}/{e['allocated']} | {e['literal_forbidden_recipient']} | {e['semantic_only_positive']} | {e['extraction_incomplete']} |")
    lines += ["", "既有配对根差值与区间，原样读取 run 的风险报告；不新增统计检验。每组根数见上表；评分校准状态遵循冻结风险报告。", "",
              "| 条件 − 参照 | 风险差 [已有95%区间] | utility差 [已有95%区间] | 完整配对 | 状态 |",
              "|---|---|---|---:|---|"]
    for r in result["stored_contrasts"]:
        c = r["coverage"]
        status = r['classification']['status'] if r['classification'] else '未作额外分类'
        lines.append(f"| {r['method']}/{r['arm']} − {r['reference']} | {interval(r['differences']['risk'])} | {interval(r['differences']['utility'])} | {c['complete_pairs']}/{c['allocated_pairs']} | {status} |")
    if result["skipped_contrasts"]:
        lines += ["", "未分配 frozen 参照的条件跳过基线差值；工程与绝对计数仍完整保留。"]
    if not result["audit_points"]:
        lines += ["", "没有已启用且已观察的独立审计点；不生成轨迹比较。"]
    lines += ["", "独立审计点：每个点保留全部根、重复和相同源码观测；选中步骤完整映射见 JSON。", "",
              "| 条件 | 坐标/比例 | 各根选中步 | 违规/有效（缺失） | utility/有效（缺失） | 文字扫描/分配 | 文字违规 | 仅语义阳性 | 提取不完整 |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in result["audit_points"]:
        e, s, u = r["evidence"], r["risk"], r["utility"]
        lines.append(f"| {r['method']}/{r['arm']} | {r['coordinate']}/{r['fraction']:.3f} | {list(r['selected_steps'].values())} | {s['positive']}/{s['known']}（{s['missing']}） | {u['positive']}/{u['known']}（{u['missing']}） | {e['literal_scan_available']}/{e['allocated']} | {e['literal_forbidden_recipient']} | {e['semantic_only_positive']} | {e['extraction_incomplete']} |")
    lines += ["", "[分组 JSON](grouped-metrics.json) · [逐根报告](report.md) · [冻结源汇总](../run/summary.json)", "",
              f"费用按冻结价格估算 {result['costs']['known_usage_estimated_cny']:.6f} 元；非账单。未知调用和预留见 JSON。"]
    return "\n".join(lines) + "\n"


def table_rows(result):
    """Flat machine-readable main table; missing estimates stay empty, never zero."""
    rows = []
    for group in result['conditions']:
        row = {key: group[key] for key in (
            'method', 'arm', 'root_count', 'slots_allocated', 'candidate_slots',
            'native_admitted_slots', 'slots_committed', 'slots_failed',
            'deployment_change_events', 'founder_still_deployed_roots',
            'review_executed', 'api_calls', 'reported_tokens', 'usage_missing_calls', 'estimated_cny')}
        for name in ('accept', 'inconclusive', 'reject'):
            row['review_' + name] = group['review_decisions'].get(name, 0)
        for name in ('accept', 'reject'):
            row['random_' + name] = group['random_control_decisions'].get('random_control_' + name, 0)
        for phase, metric in (('final_risk', 'risk'), ('final_utility', 'utility'),
                              ('audit_risk', 'audit_risk'), ('audit_utility', 'audit_utility')):
            for name in ('allocated', 'known', 'positive', 'missing', 'estimate'):
                row[phase + '_' + name] = group[metric][name]
            row[phase + '_lower'], row[phase + '_upper'] = group[metric]['bounds']
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    result = analyze(campaign)
    output = campaign / "analysis"
    output.mkdir(exist_ok=True)
    (output / "grouped-metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (output / "grouped-report.md").write_text(render(result))
    rows = table_rows(result)
    if rows:
        with (output / "main-table.csv").open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({"conditions": len(result["conditions"]), "roots": sum(r["root_count"] for r in result["conditions"]),
                      "audit_points": len(result["audit_points"]), "report": str(output / "grouped-report.md"), "api_calls": 0}))


if __name__ == "__main__":
    main()
