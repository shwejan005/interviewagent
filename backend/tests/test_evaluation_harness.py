"""Deterministic contract-harness regression tests."""

import json
from pathlib import Path

from app.evaluation.harness import evaluate_stage_output


def test_invalid_json_is_a_critical_contract_failure():
    report = evaluate_stage_output("screening", "not json")
    assert report["passed"] is False
    assert report["harness_version"] == "contract-v1"
    assert report["rules"][0]["rule_id"] == "contract.json_object"
    assert report["rules"][0]["severity"] == "critical"


def test_missing_required_confidence_is_a_schema_failure():
    report = evaluate_stage_output(
        "screening",
        json.dumps({"decision": "PASS", "score": 8}),
    )
    assert report["passed"] is False
    assert any(rule["rule_id"] == "contract.schema" for rule in report["rules"])


def test_starter_contract_cases_are_versioned_and_replayable():
    cases_path = Path(__file__).parents[1] / "evals" / "starter_cases.json"
    fixture = json.loads(cases_path.read_text(encoding="utf-8"))
    assert fixture["dataset_version"] == "starter-contract-v1"
    for case in fixture["cases"]:
        report = evaluate_stage_output(case["stage"], case["raw_output"])
        assert report["passed"] is case["expected_passed"]
        assert any(rule["rule_id"] == case["expected_rule"] for rule in report["rules"])
