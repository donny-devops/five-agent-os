from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import TaskPacket

HIGH_RISK_TERMS = {
    "legal",
    "lawsuit",
    "contract",
    "medical",
    "diagnosis",
    "therapy",
    "investment",
    "tax",
    "financial advice",
    "fire",
    "hire",
    "termination",
    "password",
    "api key",
    "secret",
    "payment",
    "credit card",
    "ssn",
    "pii",
}

WORK_TYPE_KEYWORDS: dict[str, list[str]] = {
    "content_generation": ["email", "post", "copy", "proposal", "outreach", "linkedin", "landing page"],
    "decision_support": ["decide", "choose", "recommend", "prioritize", "score", "rank"],
    "research": ["research", "summarize", "analyze", "findings", "report"],
    "data_analysis": ["data", "spreadsheet", "csv", "dashboard", "metrics", "kpi"],
    "technical_implementation": [
        "build",
        "code",
        "api",
        "workflow",
        "integration",
        "repo",
        "deploy",
        "database",
    ],
    "compliance_review": ["compliance", "policy", "quality", "qa", "review", "risk"],
}

ROUTES: dict[str, list[str]] = {
    "content_generation": ["data_synthesis_agent", "content_outreach_agent", "compliance_quality_agent"],
    "decision_support": ["data_synthesis_agent", "decision_making_agent", "compliance_quality_agent"],
    "research": ["data_synthesis_agent", "decision_making_agent"],
    "data_analysis": ["data_synthesis_agent", "decision_making_agent", "compliance_quality_agent"],
    "technical_implementation": ["data_synthesis_agent", "decision_making_agent", "compliance_quality_agent"],
    "compliance_review": ["compliance_quality_agent"],
}


@dataclass
class RouteResult:
    """Returned by build_route; includes the ordered agent list and a confidence score."""

    route: list[str]
    confidence_score: float  # 0.0 – 1.0
    matched_work_types: list[str]
    is_hard_route: bool = True  # False when falling back to default


def normalize_request(text: str) -> str:
    """Collapse whitespace and strip leading/trailing space."""
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_work_types(text: str) -> list[str]:
    """Return every work-type category whose keywords appear in *text*."""
    lowered = normalize_request(text).lower()
    if not lowered:
        return ["unknown"]

    found: list[str] = []
    for work_type, keywords in WORK_TYPE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords):
            found.append(work_type)
    return found or ["unknown"]


def detect_risk(text: str) -> tuple[str, bool]:
    """Return (risk_level, human_review_required)."""
    lowered = normalize_request(text).lower()
    if not lowered:
        return "medium", False
    if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in HIGH_RISK_TERMS):
        return "high", True
    return "medium", False


def build_route(work_types: list[str]) -> RouteResult:
    """Build a stable phase-ordered route with a confidence score.

    Confidence is calculated as:
      - 1.0 if every detected work_type maps cleanly to a known route
      - Decremented by 0.15 for each unknown type
      - Minimum 0.1 (always some signal)
    """
    phase_order = [
        "data_synthesis_agent",
        "decision_making_agent",
        "content_outreach_agent",
        "compliance_quality_agent",
    ]

    selected: set[str] = set()
    matched: list[str] = []
    unknown_count = 0

    for work_type in work_types:
        if work_type in ROUTES:
            selected.update(ROUTES[work_type])
            matched.append(work_type)
        else:
            # fallback: include all agents for unknown categories
            selected.update(phase_order)
            unknown_count += 1

    is_hard = unknown_count == 0
    confidence = max(0.1, round(1.0 - unknown_count * 0.15, 2))

    ordered_route = [agent for agent in phase_order if agent in selected]
    return RouteResult(
        route=ordered_route,
        confidence_score=confidence,
        matched_work_types=matched,
        is_hard_route=is_hard,
    )


def create_task_packet(
    request_id: str,
    user_request: str,
    metadata: dict[str, Any] | None = None,
) -> TaskPacket:
    """Parse *user_request* and return a fully-populated TaskPacket."""
    rid = (request_id or "").strip()
    if not rid:
        raise ValueError("request_id must be a non-empty string")

    normalized = normalize_request(user_request)
    if not normalized:
        raise ValueError("user_request must be a non-empty string")

    work_types = detect_work_types(normalized)
    risk_level, human_review = detect_risk(normalized)
    route_result = build_route(work_types)

    objective = normalized.rstrip(".")
    if not objective.lower().startswith(
        ("create", "build", "draft", "analyze", "decide", "review", "summarize")
    ):
        objective = f"Process request: {objective}"

    routing_reason = (
        f"Keyword-based deterministic routing. "
        f"Matched work types: {route_result.matched_work_types}. "
        f"Confidence: {route_result.confidence_score:.0%}. "
        f"{'Hard route.' if route_result.is_hard_route else 'Soft/fallback route — consider model-based routing.'}"
    )

    return TaskPacket(
        request_id=rid,
        original_request=normalized,
        objective=objective,
        work_type=work_types,
        priority="normal",
        risk_level=risk_level,  # type: ignore[arg-type]
        missing_inputs=[],
        route=route_result.route,
        human_review_required=human_review,
        routing_reason=routing_reason,
        metadata={
            **(metadata or {}),
            "routing": {
                "confidence_score": route_result.confidence_score,
                "matched_work_types": route_result.matched_work_types,
                "is_hard_route": route_result.is_hard_route,
            },
        },
    )
