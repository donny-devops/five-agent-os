"""Human feedback loop support for the five-agent pipeline.

Logs structured records when a human approves, rejects, or edits an output,
and provides simple retrieval of past corrected examples.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEEDBACK_PATH = Path("feedback.jsonl")


@dataclass
class FeedbackRecord:
    request_id: str
    agent: str
    human_action: str  # "approved" | "rejected" | "edited"
    original_output: dict[str, Any]
    corrected_output: dict[str, Any] | None = None
    rating: int | None = None
    comment: str | None = None
    work_types: list[str] | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def record_feedback(record: FeedbackRecord, path: Path = FEEDBACK_PATH) -> None:
    """Append a structured feedback record as a JSONL line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def load_recent_corrections(
    limit: int = 5,
    path: Path = FEEDBACK_PATH,
) -> list[dict[str, Any]]:
    """Return the most recent human-edited examples (simple retrieval)."""
    if not path.exists():
        return []

    corrections: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("human_action") == "edited" and rec.get("corrected_output"):
                corrections.append(rec)

    return corrections[-limit:]


def correction_rate(path: Path = FEEDBACK_PATH) -> dict[str, Any]:
    """Simple measurement: how often humans correct vs approve."""
    if not path.exists():
        return {"total": 0, "edited": 0, "approved": 0, "rejected": 0, "correction_rate": 0.0}

    counts = {"edited": 0, "approved": 0, "rejected": 0}
    total = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            action = rec.get("human_action")
            if action in counts:
                counts[action] += 1
                total += 1

    rate = counts["edited"] / total if total else 0.0
    return {"total": total, **counts, "correction_rate": round(rate, 3)}
