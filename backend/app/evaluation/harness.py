"""Deterministic contract checks for agent execution outputs.

This is the first evaluation-harness layer: cheap, reproducible checks that
run before any semantic judge. It does not claim that schema validity proves
assessment quality.
"""

from dataclasses import asdict, dataclass
from typing import Any, Type

from app.evaluation.dto import (
    BehavioralVerdict,
    CommitteeDecision,
    HiringRecommendation,
    ScreeningVerdict,
    TechnicalVerdict,
)
from app.evaluation.runner import AgentOutputError, _parse_json_output, _validate_verdict

HARNESS_VERSION = "contract-v1"

_STAGE_SCHEMAS: dict[str, Type] = {
    "screening": ScreeningVerdict,
    "technical": TechnicalVerdict,
    "behavioral": BehavioralVerdict,
    "recommendation": HiringRecommendation,
    "committee": CommitteeDecision,
}


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    passed: bool
    severity: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_stage_output(stage: str, raw_output: str) -> dict[str, Any]:
    """Run deterministic parse/schema checks for one stage output."""
    schema = _STAGE_SCHEMAS.get(stage)
    if schema is None:
        raise ValueError(f"Unknown evaluation stage: {stage}")

    rules: list[RuleResult] = []
    try:
        parsed = _parse_json_output(raw_output)
        rules.append(RuleResult("contract.json_object", True, "critical", "Output is valid JSON object syntax."))
    except AgentOutputError as exc:
        rules.append(RuleResult("contract.json_object", False, "critical", str(exc)))
        return _report(stage, rules)

    try:
        verdict = _validate_verdict(parsed, schema, raw_output)
        rules.append(RuleResult("contract.schema", True, "critical", "Output satisfies the stage schema."))
    except AgentOutputError as exc:
        rules.append(RuleResult("contract.schema", False, "critical", str(exc)))
        return _report(stage, rules)

    decision = getattr(verdict, "decision", None)
    score = getattr(verdict, "score", None)
    confidence = getattr(verdict, "confidence", None)
    rules.append(RuleResult(
        "contract.decision_enum",
        decision is not None,
        "critical",
        "Decision is present and enum-constrained." if decision is not None else "Decision is missing.",
    ))
    if score is not None:
        rules.append(RuleResult(
            "contract.score_bounds",
            0 <= score <= 10,
            "high",
            "Score is finite and within 0-10." if 0 <= score <= 10 else "Score is outside 0-10.",
        ))
    if confidence is not None:
        rules.append(RuleResult(
            "contract.confidence_bounds",
            0 <= confidence <= 1,
            "high",
            "Confidence is within 0-1." if 0 <= confidence <= 1 else "Confidence is outside 0-1.",
        ))
    return _report(stage, rules)


def _report(stage: str, rules: list[RuleResult]) -> dict[str, Any]:
    return {
        "harness_version": HARNESS_VERSION,
        "stage": stage,
        "passed": all(rule.passed for rule in rules),
        "rules": [rule.as_dict() for rule in rules],
    }
