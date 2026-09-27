"""
Regression tests for crew_runner.py's output-parsing/validation layer.

These are the tests behind CODEBASE_REVIEW.md finding B03 ("Model failures
become candidate judgments"). Before the fix, malformed agent output was
silently downgraded into a fabricated PASS/FAIL/BORDERLINE decision with a
default confidence of 0.8. The fix (crew_runner._parse_json_output /
_validate_verdict) must raise AgentOutputError instead — never a business
decision — for every one of the malformed cases below.

No network/LLM call is made anywhere in this file; these tests exercise
pure parsing/validation functions directly.
"""

import pytest

from crew_runner import AgentOutputError, _parse_json_output, _validate_verdict
from models import ScreeningVerdict


VALID_SCREENING_JSON = {
    "decision": "PASS",
    "score": 8.5,
    "strengths": ["Strong Python background"],
    "weaknesses": ["Limited cloud experience"],
    "reasoning": "Solid overall fit for the role.",
    "candidate_summary": "Mid-level backend engineer.",
    "skills_extracted": ["Python", "FastAPI"],
    "experience_years": 4,
    "recommended_questions": ["Explain idempotency."],
    "confidence": 0.9,
}


class TestParseJsonOutput:
    def test_raises_on_completely_invalid_json(self):
        with pytest.raises(AgentOutputError):
            _parse_json_output("not valid json")

    def test_raises_on_empty_object_without_required_fields(self):
        # `{}` parses as valid JSON but must fail *schema* validation later —
        # parsing alone should succeed here.
        data = _parse_json_output("{}")
        assert data == {}

    def test_extracts_json_from_markdown_code_fence(self):
        raw = '```json\n{"decision": "PASS", "score": 9}\n```'
        data = _parse_json_output(raw)
        assert data == {"decision": "PASS", "score": 9}

    def test_extracts_json_object_surrounded_by_prose(self):
        raw = 'Here is my evaluation:\n{"decision": "PASS", "score": 9}\nThank you.'
        data = _parse_json_output(raw)
        assert data == {"decision": "PASS", "score": 9}


class TestValidateVerdict:
    def test_accepts_well_formed_screening_verdict(self):
        verdict = _validate_verdict(VALID_SCREENING_JSON, ScreeningVerdict, "raw")
        assert verdict.decision.value == "PASS"
        assert verdict.score == 8.5
        assert verdict.confidence == 0.9

    def test_rejects_missing_object_body(self):
        # Empty dict is missing every required field.
        with pytest.raises(AgentOutputError):
            _validate_verdict({}, ScreeningVerdict, "{}")

    def test_rejects_non_dict_payload(self):
        with pytest.raises(AgentOutputError):
            _validate_verdict(["not", "an", "object"], ScreeningVerdict, "[...]")

    def test_rejects_out_of_range_score(self):
        payload = dict(VALID_SCREENING_JSON, score=999)
        with pytest.raises(AgentOutputError):
            _validate_verdict(payload, ScreeningVerdict, "raw")

    def test_rejects_unknown_decision_enum_value(self):
        payload = dict(VALID_SCREENING_JSON, decision="APPROVE")
        with pytest.raises(AgentOutputError):
            _validate_verdict(payload, ScreeningVerdict, "raw")

    def test_rejects_missing_confidence_no_silent_default(self):
        payload = dict(VALID_SCREENING_JSON)
        del payload["confidence"]
        with pytest.raises(AgentOutputError):
            _validate_verdict(payload, ScreeningVerdict, "raw")

    def test_error_carries_raw_output_for_triage(self):
        raw_text = "not valid json at all"
        with pytest.raises(AgentOutputError) as exc_info:
            _parse_json_output(raw_text)
        assert exc_info.value.raw_output == raw_text
