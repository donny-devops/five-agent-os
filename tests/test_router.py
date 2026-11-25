"""Tests for src/multi_agent_os/router.py."""

from __future__ import annotations

import pytest

from src.multi_agent_os.router import (
    build_route,
    create_task_packet,
    detect_risk,
    detect_work_types,
)


# ---------------------------------------------------------------------------
# detect_work_types
# ---------------------------------------------------------------------------
class TestDetectWorkTypes:
    def test_content_generation_keyword(self) -> None:
        result = detect_work_types("Write an email proposal for our new client")
        assert "content_generation" in result

    def test_data_analysis_keyword(self) -> None:
        result = detect_work_types("Build a KPI dashboard from CSV data")
        assert "data_analysis" in result

    def test_technical_keyword(self) -> None:
        result = detect_work_types("Deploy the API to production via workflow")
        assert "technical_implementation" in result

    def test_research_keyword(self) -> None:
        result = detect_work_types("Summarize the findings from the report")
        assert "research" in result

    def test_decision_keyword(self) -> None:
        result = detect_work_types("Decide which option to prioritize")
        assert "decision_support" in result

    def test_compliance_keyword(self) -> None:
        result = detect_work_types("Run a compliance review and check quality")
        assert "compliance_review" in result

    def test_unknown_falls_back(self) -> None:
        result = detect_work_types("blah blah blah nonsense xyz")
        assert result == ["unknown"]

    def test_case_insensitive(self) -> None:
        result = detect_work_types("CREATE AN EMAIL")
        assert "content_generation" in result

    def test_multiple_types_detected(self) -> None:
        result = detect_work_types("Write an email and analyze the data")
        assert "content_generation" in result
        assert "data_analysis" in result

    def test_no_false_positive_repo_in_report(self) -> None:
        # "repo" keyword must not match the word "report"
        result = detect_work_types("Summarize the findings from the report")
        assert "technical_implementation" not in result

    def test_no_false_positive_code_in_decode(self) -> None:
        # "code" keyword must not match "decode"
        result = detect_work_types("Please decode the message")
        assert "technical_implementation" not in result

    def test_no_false_positive_post_in_postage(self) -> None:
        # "post" keyword must not match "postage"
        result = detect_work_types("Calculate the postage cost")
        assert "content_generation" not in result


# ---------------------------------------------------------------------------
# detect_risk
# ---------------------------------------------------------------------------
class TestDetectRisk:
    def test_high_risk_term(self) -> None:
        level, human = detect_risk("This involves a contract and payment")
        assert level == "high"
        assert human is True

    def test_no_risk(self) -> None:
        level, human = detect_risk("Write a blog post about productivity tips")
        assert level == "medium"
        assert human is False

    def test_ssn_triggers_high_risk(self) -> None:
        level, human = detect_risk("Please include the SSN in the form")
        assert level == "high"
        assert human is True


# ---------------------------------------------------------------------------
# build_route
# ---------------------------------------------------------------------------
class TestBuildRoute:
    def test_content_generation_route_order(self) -> None:
        result = build_route(["content_generation"])
        # compliance must come after synthesis
        ds_idx = result.route.index("data_synthesis_agent")
        cq_idx = result.route.index("compliance_quality_agent")
        assert ds_idx < cq_idx

    def test_confidence_full_match(self) -> None:
        result = build_route(["research"])
        assert result.confidence_score == 1.0
        assert result.is_hard_route is True

    def test_confidence_reduced_for_unknown(self) -> None:
        result = build_route(["unknown"])
        assert result.confidence_score < 1.0
        assert result.is_hard_route is False

    def test_compliance_only_route(self) -> None:
        result = build_route(["compliance_review"])
        assert result.route == ["compliance_quality_agent"]

    def test_phase_order_always_preserved(self) -> None:
        result = build_route(["compliance_review", "content_generation"])
        phase_order = [
            "data_synthesis_agent",
            "decision_making_agent",
            "content_outreach_agent",
            "compliance_quality_agent",
        ]
        indexed = [phase_order.index(a) for a in result.route]
        assert indexed == sorted(indexed)


# ---------------------------------------------------------------------------
# create_task_packet
# ---------------------------------------------------------------------------
class TestCreateTaskPacket:
    def test_returns_task_packet_with_route(self) -> None:
        tp = create_task_packet("REQ-001", "Write a proposal for a new client")
        assert len(tp.route) > 0

    def test_request_id_preserved(self) -> None:
        tp = create_task_packet("MY-ID-42", "Analyze the KPI dashboard data")
        assert tp.request_id == "MY-ID-42"

    def test_high_risk_sets_human_review(self) -> None:
        tp = create_task_packet("REQ-002", "Review the contract and payment terms")
        assert tp.human_review_required is True
        assert tp.risk_level == "high"

    def test_routing_metadata_present(self) -> None:
        tp = create_task_packet("REQ-003", "Build an API workflow")
        assert "routing" in tp.metadata
        assert "confidence_score" in tp.metadata["routing"]

    def test_objective_prefixed_if_no_verb(self) -> None:
        tp = create_task_packet("REQ-004", "Something that has no action verb at all")
        assert tp.objective.startswith("Process request:")

    def test_objective_not_prefixed_if_verb_present(self) -> None:
        tp = create_task_packet("REQ-005", "Create a summary of our Q2 findings")
        assert not tp.objective.startswith("Process request:")

    def test_version_field_present(self) -> None:
        tp = create_task_packet("REQ-006", "Build a new dashboard")
        assert tp.version is not None
        assert len(tp.version) > 0


    def test_rejects_multiline_request_id(self) -> None:
        with pytest.raises(ValueError, match="request_id"):
            create_task_packet("bad\nid", "Build an API workflow")

    def test_rejects_oversized_request(self) -> None:
        with pytest.raises(ValueError, match="8000"):
            create_task_packet("REQ-009", "a" * 8001)
