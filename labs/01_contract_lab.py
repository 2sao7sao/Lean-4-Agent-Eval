"""Offline teaching lab: synthetic traces and structured report values only.

No model, real office file, external state, or Lean proof is executed here.
The supplied trace is trusted fixture data; this lab does NOT establish that
an actual trace is authentic or complete. PASS covers only the three rules below.
"""

from copy import deepcopy
from hashlib import sha256
import json
from math import expm1, log


SOURCE_CENTS = [10000, 20000, -2000]
SOURCE_HASH = sha256(json.dumps(SOURCE_CENTS).encode()).hexdigest()
EXPECTED_CENTS = sum(SOURCE_CENTS)


def verdict(status, reason):
    return {"status": status, "reason": reason}


def stage(trace, kind):
    if trace is None:
        return None, verdict("UNKNOWN", "没有过程记录")
    if not isinstance(trace, list) or any(not isinstance(e, dict) for e in trace):
        return None, verdict("ERROR", "模拟 trace 的格式错误")
    matches = [e for e in trace if e.get("kind") == kind]
    if not matches:
        return None, verdict("UNKNOWN", f"缺少 {kind} 事件")
    if len(matches) != 1:
        return None, verdict("ERROR", f"教学格式要求恰有一个 {kind} 事件")
    return matches[0], None


def check_lineage(trace):
    events = []
    for kind in ("read", "compute", "export"):
        event, problem = stage(trace, kind)
        if problem:
            return problem
        if "id" not in event or "source_hash" not in event:
            return verdict("UNKNOWN", f"{kind} 事件缺少溯源字段")
        if not isinstance(event["id"], str) or not isinstance(event["source_hash"], str):
            return verdict("ERROR", "事件标识和快照标识必须为字符串")
        events.append(event)
    read, compute, export = events
    if len({e["id"] for e in events}) != 3:
        return verdict("ERROR", "事件标识重复")
    if any(e["source_hash"] != SOURCE_HASH for e in events):
        return verdict("FAIL", "记录的输入版本与指定版本不一致")
    if "parent_id" not in compute or "parent_id" not in export:
        return verdict("UNKNOWN", "缺少事件间的因果连接")
    if compute["parent_id"] != read["id"] or export["parent_id"] != compute["id"]:
        return verdict("FAIL", "导出／计算指向了错误的上游事件")
    if not (trace.index(read) < trace.index(compute) < trace.index(export)):
        return verdict("FAIL", "教学模型的顺序约束被违反")
    return verdict("PASS", "模拟事件具有指定输入版本和读取→计算→导出的连接")


def check_total(container, label):
    if container is None:
        return verdict("UNKNOWN", f"没有{label}")
    if not isinstance(container, dict):
        return verdict("FAIL", f"{label}违反已约定的对象格式")
    if "total_cents" not in container:
        return verdict("UNKNOWN", f"{label}缺少净额")
    # bool is a subclass of int in Python; exclude it explicitly.
    if type(container["total_cents"]) is not int:
        return verdict("FAIL", f"{label}违反整数分的格式要求")
    if container["total_cents"] != EXPECTED_CENTS:
        return verdict("FAIL", f"{label}净额不等于独立重算的 {EXPECTED_CENTS} 分")
    return verdict("PASS", f"{label}净额与独立重算一致")


def check_computation(trace):
    event, problem = stage(trace, "compute")
    return problem if problem else check_total(event, "计算记录")


def aggregate(results):
    """Retain all per-rule results in the caller; this is only a summary."""
    statuses = [r["status"] for r in results]
    if not statuses:
        return "UNKNOWN"
    if any(s not in {"PASS", "FAIL", "UNKNOWN", "ERROR"} for s in statuses):
        return "ERROR"
    for priority in ("FAIL", "ERROR", "UNKNOWN"):
        if priority in statuses:
            return priority
    return "PASS"


def evaluate(case):
    rules = {
        "trace_lineage": check_lineage(case["trace"]),
        "trace_computation": check_computation(case["trace"]),
        "end_to_end_total": check_total(case["artifact"], "模拟最终产物"),
    }
    return {
        "case": case["name"],
        "toy_contract_verdict": aggregate(rules.values()),
        "rules": rules,
        "business_quality": "NOT_EVALUATED",
        "real_file_rendering": "NOT_EVALUATED",
        "trace_authenticity_and_completeness": "ASSUMED_FIXTURE_ONLY",
        "formal_verification": "NOT_PERFORMED",
    }


def baseline():
    return {
        "name": "正确的模拟计算与结果",
        "trace": [
            {"id": "r1", "kind": "read", "source_hash": SOURCE_HASH},
            {"id": "c1", "kind": "compute", "parent_id": "r1",
             "source_hash": SOURCE_HASH, "total_cents": 28000},
            {"id": "e1", "kind": "export", "parent_id": "c1", "source_hash": SOURCE_HASH},
        ],
        "artifact": {"total_cents": 28000},
    }


def scenarios():
    # Expected vectors are specified from the teaching contract, not generated
    # from the evaluator. These are regression examples, not population samples.
    cases = [(baseline(), ("PASS", "PASS", "PASS"), "PASS")]

    c = deepcopy(baseline())
    c["name"] = "过程数值正确，最终数字错误"
    c["artifact"]["total_cents"] = 30000
    cases.append((c, ("PASS", "PASS", "FAIL"), "FAIL"))

    c = deepcopy(baseline())
    c["name"] = "结果数字正确，过程记录缺失"
    c["trace"] = None
    cases.append((c, ("UNKNOWN", "UNKNOWN", "PASS"), "UNKNOWN"))

    c = deepcopy(baseline())
    c["name"] = "计算和结果一致，但两者都算错"
    c["trace"][1]["total_cents"] = 30000
    c["artifact"]["total_cents"] = 30000
    cases.append((c, ("PASS", "FAIL", "FAIL"), "FAIL"))

    c = deepcopy(baseline())
    c["name"] = "数字正确，但使用了其他来源版本"
    c["trace"][0]["source_hash"] = "different-source"
    cases.append((c, ("FAIL", "PASS", "PASS"), "FAIL"))

    c = deepcopy(baseline())
    c["name"] = "最终产物字段格式错误"
    c["artifact"]["total_cents"] = "28000"
    cases.append((c, ("PASS", "PASS", "FAIL"), "FAIL"))

    c = deepcopy(baseline())
    c["name"] = "评估采集器提供的 trace 格式损坏"
    c["trace"] = "corrupt-collector-record"
    cases.append((c, ("ERROR", "ERROR", "PASS"), "ERROR"))

    c = deepcopy(baseline())
    c["name"] = "导出指向错误的计算记录"
    c["trace"][2]["parent_id"] = "another-computation"
    cases.append((c, ("FAIL", "PASS", "PASS"), "FAIL"))

    c = deepcopy(baseline())
    c["name"] = "缺少最终产物"
    c["artifact"] = None
    cases.append((c, ("PASS", "PASS", "UNKNOWN"), "UNKNOWN"))

    c = deepcopy(baseline())
    c["name"] = "事件先后不符合教学模型"
    c["trace"][0], c["trace"][1] = c["trace"][1], c["trace"][0]
    cases.append((c, ("FAIL", "PASS", "PASS"), "FAIL"))

    c = deepcopy(baseline())
    c["name"] = "缺少导出记录"
    c["trace"].pop()
    cases.append((c, ("UNKNOWN", "PASS", "PASS"), "UNKNOWN"))
    return cases


def zero_failure_upper(n, alpha=0.05):
    """One-sided exact bound, only for fixed-n IID Bernoulli zero-failure data."""
    if type(n) is not int or n <= 0 or not 0 < alpha < 1:
        raise ValueError("n must be a positive integer and 0 < alpha < 1")
    return -expm1(log(alpha) / n)


def main():
    reports = []
    for case, expected_rules, expected_overall in scenarios():
        report = evaluate(case)
        actual_rules = tuple(r["status"] for r in report["rules"].values())
        if actual_rules != expected_rules or report["toy_contract_verdict"] != expected_overall:
            raise AssertionError(f"unexpected verdict for {case['name']}: {report}")
        reports.append(report)
    # These checks address accidental vacuous acceptance and contradictory data.
    if aggregate([]) != "UNKNOWN":
        raise AssertionError("empty requirements must not pass")
    if aggregate([verdict("FAIL", "known violation"), verdict("ERROR", "grader error")]) != "FAIL":
        raise AssertionError("a grader error must not erase a known violation")
    if check_total({"total_cents": True}, "test")["status"] != "FAIL":
        raise AssertionError("boolean must not be accepted as integer money")
    print(json.dumps({
        "evidence_scope": "synthetic_teaching_fixtures_only",
        "scenario_expectations_matched": len(reports),
        "additional_boundary_checks_matched": 3,
        "reports": reports,
        "illustrative_statistics_not_from_scenarios": {
            "assumptions": "fixed n, IID Bernoulli, zero observed failures, error-free labels",
            "one_sided_confidence_level": 0.95,
            "failure_rate_upper": {str(n): zero_failure_upper(n) for n in (20, 100, 300)},
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
