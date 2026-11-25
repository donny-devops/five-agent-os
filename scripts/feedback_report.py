#!/usr/bin/env python3
"""Print a simple feedback loop report (correction rate and recent edits)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multi_agent_os.feedback import correction_rate, load_recent_corrections


def main() -> None:
    stats = correction_rate()
    print("=== Feedback Loop Report ===")
    print(json.dumps(stats, indent=2))
    print()
    print("Recent corrections (last 5):")
    for rec in load_recent_corrections(limit=5):
        print(
            f"- {rec.get('timestamp')} | {rec.get('agent')} | "
            f"{rec.get('comment') or rec.get('human_action')}"
        )


if __name__ == "__main__":
    main()
