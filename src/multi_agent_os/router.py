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
