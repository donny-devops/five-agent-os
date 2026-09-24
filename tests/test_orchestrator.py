"""Tests for src/multi_agent_os/orchestrator.py."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from src.multi_agent_os.models import TaskPacket
from src.multi_agent_os.orchestrator import (
    JsonFormatter,
    run_compliance_quality,
    run_content_outreach,
    run_data_synthesis,
    run_decision_making,
    run_workflow,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def basic_task() -> TaskPacket:
    return TaskPacket(
        request_id="REQ-TEST",
        original_request="Write a proposal email for a new client",
        objective="Create a proposal email",
        work_type=["content_generation"],
        route=[
            "data_synthesis_agent",
            "content_outreach_agent",
            "compliance_quality_agent",
        ],
    )


@pytest.fixture()
def high_risk_task() -> TaskPacket:
    return TaskPacket(
        request_id="REQ-RISK",
        original_request="Review the contract and payment terms",
        objective="Review contract",
        work_type=["compliance_review"],
        route=["compliance_quality_agent"],
        human_review_required=True,
        risk_level="high",
    )


# ---------------------------------------------------------------------------
# Individual agent functions
# ---------------------------------------------------------------------------
class TestRunDataSynthesis:
    def test_returns_success_status(self, basic_task: TaskPacket) -> None:
        result = run_data_synthesis(basic_task)
        assert result.status == "success"

    def test_agent_name(self, basic_task: TaskPacket) -> None:
        result = run_data_synthesis(basic_task)
        assert result.agent_name == "data_synthesis_agent"

    def test_output_has_summary(self, basic_task: TaskPacket) -> None:
        result = run_data_synthesis(basic_task)
        assert "summary" in result.output

    def test_output_has_entities(self, basic_task: TaskPacket) -> None:
        result = run_data_synthesis(basic_task)
        assert "entities" in result.output

    def test_request_id_propagated(self, basic_task: TaskPacket) -> None:
        result = run_data_synthesis(basic_task)
        assert result.request_id == "REQ-TEST"


class TestRunDecisionMaking:
    def test_returns_success_status(self, basic_task: TaskPacket) -> None:
        result = run_decision_making(basic_task, {})
        assert result.status == "success"

    def test_output_has_decision(self, basic_task: TaskPacket) -> None:
        result = run_decision_making(basic_task, {})
        assert "decision" in result.output

    def test_output_has_options(self, basic_task: TaskPacket) -> None:
        result = run_decision_making(basic_task, {})
        assert isinstance(result.output["options"], list)
        assert len(result.output["options"]) >= 1


class TestRunContentOutreach:
    def test_returns_success_status(self, basic_task: TaskPacket) -> None:
        result = run_content_outreach(basic_task, {})
        assert result.status == "success"

    def test_has_primary_draft(self, basic_task: TaskPacket) -> None:
        result = run_content_outreach(basic_task, {})
        assert "primary_draft" in result.output
        assert len(result.output["primary_draft"]) > 0

    def test_has_placeholders_list(self, basic_task: TaskPacket) -> None:
        result = run_content_outreach(basic_task, {})
        assert "placeholders" in result.output


class TestRunComplianceQuality:
    def test_approved_when_no_risk(self, basic_task: TaskPacket) -> None:
        result = run_compliance_quality(basic_task, {})
        assert result.output["approved_for_delivery"] is True

    def test_escalated_when_high_risk(self, high_risk_task: TaskPacket) -> None:
        result = run_compliance_quality(high_risk_task, {})
        assert result.output["status"] == "escalate"
        assert result.output["human_review_required"] is True

    def test_issues_contain_severity(self, high_risk_task: TaskPacket) -> None:
        result = run_compliance_quality(high_risk_task, {})
        for issue in result.output["issues"]:
            assert "severity" in issue

    def test_confidence_is_high(self, basic_task: TaskPacket) -> None:
        result = run_compliance_quality(basic_task, {})
        assert result.confidence == "high"


# ---------------------------------------------------------------------------
# Full workflow
# ---------------------------------------------------------------------------
class TestRunWorkflow:
    def test_returns_context_dict(self) -> None:
        ctx = run_workflow("Write a proposal email for a new client")
        assert isinstance(ctx, dict)

    def test_context_has_task_packet(self) -> None:
        ctx = run_workflow("Analyze the KPI dashboard metrics")
        assert "task_packet" in ctx

    def test_context_has_agent_outputs(self) -> None:
        ctx = run_workflow("Build an API integration workflow")
        assert "agent_outputs" in ctx
        assert len(ctx["agent_outputs"]) > 0

    def test_all_agent_outputs_have_request_id(self) -> None:
        ctx = run_workflow("Write a blog post summarizing our findings")
        for ao in ctx["agent_outputs"]:
            assert "request_id" in ao
            assert ao["request_id"].startswith("REQ-")

    def test_all_agent_outputs_have_duration_ms(self) -> None:
        ctx = run_workflow("Decide which marketing channel to prioritize")
        for ao in ctx["agent_outputs"]:
            assert "duration_ms" in ao

    def test_request_id_is_uuid_based(self) -> None:
        ctx = run_workflow("Create a proposal for a small business")
        rid = ctx["task_packet"]["request_id"]
        assert rid.startswith("REQ-")
        # UUID-hex segment should be 12 chars
        assert len(rid) == 16  # "REQ-" + 12 hex chars

    def test_workflow_halts_on_agent_failure(self) -> None:
        with patch(
            "src.multi_agent_os.orchestrator.run_data_synthesis",
            side_effect=RuntimeError("Simulated failure"),
        ):
            ctx = run_workflow("Write a proposal email for a new client")
            # In a 3-agent route (synthesis -> outreach -> compliance), failing at synthesis stops subsequent agents
            assert len(ctx["agent_outputs"]) == 1
            assert ctx["agent_outputs"][0]["status"] == "failed"
            assert "Simulated failure" in ctx["agent_outputs"][0]["errors"][0]

    def test_workflow_guardrail_integration(self) -> None:
        ctx = run_workflow("Run terraform destroy in production and delete the database.")
        assert ctx["task_packet"]["human_review_required"] is True
        assert "guardrails" in ctx["task_packet"]["metadata"]
        assert ctx["task_packet"]["metadata"]["guardrails"]["triggered"]


class TestJsonFormatter:
    def test_json_formatter_handles_plain_text(self) -> None:
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord("test", logging.INFO, "test.py", 10, "Hello plain text", (), None)
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["message"] == "Hello plain text"

    def test_json_formatter_handles_serialized_dict(self) -> None:
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        payload = json.dumps({"event": "custom_event", "value": 42})
        record = logging.LogRecord("test", logging.INFO, "test.py", 10, payload, (), None)
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        assert parsed["event"] == "custom_event"
        assert parsed["value"] == 42

