from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Ensure LLM caching is active
os.environ.setdefault("LLM_CACHE", "1")

from app.agent import run_agent
from app.apps import select_app, get_active_app_id
from app.llm import LLMRateLimited


def load_testset(testset_path: Path) -> list[dict[str, Any]]:
    if not testset_path.exists():
        raise FileNotFoundError(f"Testset file not found at {testset_path}")
    return json.loads(testset_path.read_text(encoding="utf-8"))


def load_completed_ids(run_file: Path) -> set[str]:
    completed = set()
    if run_file.exists():
        with open(run_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("id"):
                        completed.add(record["id"])
                except Exception:
                    continue
    return completed


def execute_item_with_retry(
    item: dict[str, Any],
    max_retries: int = 1,
    backoff_delay: float = 12.0,
) -> dict[str, Any]:
    """Execute run_agent for an item with one backoff retry on rate limit."""
    app_target = item.get("app", "sales")
    canonical_app = "clinic" if app_target == "clinic" else "meridian"
    if get_active_app_id() != canonical_app:
        select_app(canonical_app)

    role = item.get("role", "admin")
    session_id = f"eval_{item['id']}_{uuid.uuid4().hex[:6]}"
    prev_messages = item.get("previous") or []

    for attempt in range(max_retries + 1):
        try:
            # Replay previous conversation context if any
            for prev_msg in prev_messages:
                run_agent(prev_msg, role=role, session_id=session_id)

            start_t = time.perf_counter()
            result = run_agent(item["message"], role=role, session_id=session_id)
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            result["latency_ms"] = latency_ms

            # Check if internal result indicates a 429 rate limit error
            outcome = result.get("outcome")
            err_msg = str(result.get("error") or "")
            if outcome == "error" and ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "rate limit" in err_msg.lower()):
                if attempt < max_retries:
                    print(f"Rate limited (status 429) for {item['id']}. Backing off {backoff_delay}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(backoff_delay)
                    continue

            return result
        except LLMRateLimited as exc:
            if attempt < max_retries:
                print(f"LLMRateLimited caught for {item['id']}. Backing off {backoff_delay}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(backoff_delay)
                continue
            return {
                "plan": [],
                "answer": "Rate limit exceeded after retry.",
                "outcome": "error",
                "error": {"message": str(exc)},
                "latency_ms": 0.0,
                "faithfulness": {"checked": 0, "unverified": []},
            }
        except Exception as exc:
            return {
                "plan": [],
                "answer": f"Evaluation error: {exc}",
                "outcome": "error",
                "error": {"message": str(exc)},
                "latency_ms": 0.0,
                "faithfulness": {"checked": 0, "unverified": []},
            }

    return {
        "plan": [],
        "answer": "Evaluation failed after retries.",
        "outcome": "error",
        "error": {"message": "Retries exhausted"},
        "latency_ms": 0.0,
        "faithfulness": {"checked": 0, "unverified": []},
    }


def run_evaluation(
    testset_path: Path,
    output_dir: Path,
    run_name: str,
    split: str = "all",
    limit: int | None = None,
    app: str = "all",
    delay: float = 6.0,
    resume: bool = False,
) -> Path:
    items = load_testset(testset_path)

    # Filter items
    if split in ("dev", "heldout"):
        items = [i for i in items if i.get("split") == split]
    if app in ("sales", "clinic"):
        items = [i for i in items if i.get("app") == app]
    if limit is not None and limit > 0:
        items = items[:limit]

    output_dir.mkdir(parents=True, exist_ok=True)
    run_file = output_dir / f"{run_name}.jsonl"

    completed_ids: set[str] = set()
    if resume and run_file.exists():
        completed_ids = load_completed_ids(run_file)
        print(f"Resuming run '{run_name}': {len(completed_ids)} items already completed.")

    remaining_items = [i for i in items if i["id"] not in completed_ids]
    print(f"Running evaluation on {len(remaining_items)} items (out of {len(items)} filtered, total testset {len(load_testset(testset_path))})...")

    with open(run_file, "a", encoding="utf-8") as out_f:
        for idx, item in enumerate(remaining_items, start=1):
            item_id = item["id"]
            print(f"[{idx}/{len(remaining_items)}] Evaluating {item_id} ({item.get('app')}/{item.get('language')}/{item.get('group')}): \"{item['message']}\"")

            result = execute_item_with_retry(item)

            record = {
                "id": item_id,
                "app": item.get("app", "sales"),
                "language": item.get("language", "en"),
                "group": item.get("group", ""),
                "split": item.get("split", "dev"),
                "role": item.get("role", "admin"),
                "message": item["message"],
                "previous": item.get("previous"),
                "expected": item.get("expected", {}),
                "result": result,
                "latency_ms": result.get("latency_ms", 0.0),
                "timestamp": datetime.now().isoformat(),
            }

            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_f.flush()

            # Free-tier safe delay between requests if not last
            if idx < len(remaining_items) and delay > 0:
                time.sleep(delay)

    print(f"\nEvaluation finished. Results saved to {run_file}")
    return run_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Cognito Pilot in-process evaluation runner.")
    parser.add_argument("--testset", type=Path, default=ROOT / "eval" / "testset.json", help="Path to testset JSON")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "eval" / "runs", help="Output directory for runs")
    parser.add_argument("--name", type=str, default="", help="Run name (default timestamped)")
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="all", help="Dataset split to evaluate")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of requests to evaluate")
    parser.add_argument("--app", choices=["sales", "clinic", "all"], default="all", help="Target app")
    parser.add_argument("--delay", type=float, default=6.0, help="Delay between requests in seconds")
    parser.add_argument("--resume", action="store_true", help="Resume run by skipping already saved IDs")

    args = parser.parse_args()
    run_name = args.name.strip() if args.name.strip() else f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    run_evaluation(
        testset_path=args.testset,
        output_dir=args.runs_dir,
        run_name=run_name,
        split=args.split,
        limit=args.limit,
        app=args.app,
        delay=args.delay,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
