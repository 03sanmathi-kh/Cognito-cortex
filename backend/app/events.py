from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EVENTS_LOG_PATH = BACKEND_ROOT / ".cache" / "events.jsonl"


def log_event(
    session_id: str | None,
    role: str,
    outcome: str,
    number_of_plan_steps: int = 0,
    number_of_tool_calls: int = 0,
    latency_ms: float = 0.0,
    llm_cached: bool = False,
    faithfulness_counts: dict[str, Any] | None = None,
    verification_result: Any | None = None,
    language_guess: str | None = None,
) -> dict[str, Any]:
    EVENTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    fc = faithfulness_counts or {"checked": 0, "unverified": 0}
    # Ensure serializable counts
    if isinstance(fc, dict):
        clean_fc = {
            "checked": int(fc.get("checked", 0)),
            "unverified": len(fc.get("unverified", [])) if isinstance(fc.get("unverified"), list) else int(fc.get("unverified", 0)),
        }
    else:
        clean_fc = {"checked": 0, "unverified": 0}

    record = {
        "timestamp": datetime.fromtimestamp(time.time(), timezone.utc).isoformat(),
        "session_id": session_id,
        "role": role,
        "language_guess": language_guess,
        "outcome": outcome,
        "number_of_plan_steps": int(number_of_plan_steps),
        "number_of_tool_calls": int(number_of_tool_calls),
        "latency_ms": round(float(latency_ms), 2),
        "llm_cached": bool(llm_cached),
        "faithfulness_counts": clean_fc,
        "verification_result": verification_result,
    }

    line = json.dumps(record, default=str)
    with EVENTS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

    return record


def record_verification_event(
    session_id: str | None,
    verification_result: dict[str, Any],
    role: str = "analyst",
) -> dict[str, Any]:
    matched = bool(verification_result.get("matched", False))
    outcome = "verified" if matched else "mismatch"
    return log_event(
        session_id=session_id,
        role=role,
        outcome=outcome,
        number_of_plan_steps=0,
        number_of_tool_calls=0,
        latency_ms=0.0,
        llm_cached=False,
        faithfulness_counts={"checked": 0, "unverified": 0},
        verification_result=verification_result,
    )


def get_events_summary(log_path: Path | None = None) -> dict[str, Any]:
    path = log_path or EVENTS_LOG_PATH
    if not path.exists():
        return {
            "counts_by_outcome": {},
            "average_latency": 0.0,
            "average_latency_ms": 0.0,
            "average_steps": 0.0,
            "total_requests": 0,
        }

    counts_by_outcome: dict[str, int] = {}
    total_latency = 0.0
    total_steps = 0
    total_requests = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                row = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            outcome = row.get("outcome", "unknown")
            counts_by_outcome[outcome] = counts_by_outcome.get(outcome, 0) + 1
            total_latency += float(row.get("latency_ms", 0.0) or 0.0)
            total_steps += int(row.get("number_of_plan_steps", 0) or 0)
            total_requests += 1

    if total_requests == 0:
        return {
            "counts_by_outcome": {},
            "average_latency": 0.0,
            "average_latency_ms": 0.0,
            "average_steps": 0.0,
            "total_requests": 0,
        }

    avg_lat = round(total_latency / total_requests, 2)
    avg_st = round(total_steps / total_requests, 2)

    return {
        "counts_by_outcome": counts_by_outcome,
        "average_latency": avg_lat,
        "average_latency_ms": avg_lat,
        "average_steps": avg_st,
        "total_requests": total_requests,
    }
