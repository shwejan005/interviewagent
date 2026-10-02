"""Replay deterministic benchmark cases against the contract harness."""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


async def main() -> int:
    from app.config import database
    from app.evaluation.harness import evaluate_stage_output, HARNESS_VERSION
    from app.review import repository as review_db

    database.init_db()
    cases = review_db.list_benchmark_cases()
    failures = []
    for case in cases:
        report = evaluate_stage_output(case["stage"], case["input_json"]["raw_output"])
        expected = {rule["rule_id"]: rule["passed"] for rule in case["expected_rules_json"]}
        observed = {rule["rule_id"]: rule["passed"] for rule in report["rules"]}
        passed = all(observed.get(rule_id) == expected_value for rule_id, expected_value in expected.items()) and report["passed"] is False
        review_db.record_benchmark_run(case["case_id"], HARNESS_VERSION, passed, report)
        if not passed:
            failures.append(case["case_id"])
    print(f"benchmark_cases={len(cases)} passed={len(cases) - len(failures)} failed={len(failures)}")
    if failures:
        print("failed_cases=" + ",".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))