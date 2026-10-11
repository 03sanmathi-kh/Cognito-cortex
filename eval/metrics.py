from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], p: float) -> float:
    """Compute percentile p (0.0 to 1.0) deterministically."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * p
    lower = int(idx)
    upper = lower + 1
    weight = idx - lower
    if upper >= len(sorted_vals):
        return float(sorted_vals[-1])
    return float(sorted_vals[lower] * (1.0 - weight) + sorted_vals[upper] * weight)


def precision_at_k(ranked: list[str], target: str, k: int) -> float:
    """Precision@k for a single relevant item target."""
    if k <= 0 or not ranked:
        return 0.0
    top_k = ranked[:k]
    return 1.0 / k if target in top_k else 0.0


def recall_at_k(ranked: list[str], target: str, k: int) -> float:
    """Recall@k for a single relevant item target."""
    if k <= 0 or not ranked:
        return 0.0
    top_k = ranked[:k]
    return 1.0 if target in top_k else 0.0


def reciprocal_rank(ranked: list[str], target: str) -> float:
    """Reciprocal rank of target in ranked list."""
    for rank, item in enumerate(ranked, start=1):
        if item == target:
            return 1.0 / rank
    return 0.0


def simulate_plan(plan: list[dict[str, Any]], initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply plan steps to simulate resulting UI state."""
    state = {
        "page_id": None,
        "filters": {},
        "date_range": None,
        "sort": None,
        "metric": None,
        "dimension": None,
    }
    if initial_state:
        state.update(initial_state)

    for step in plan or []:
        tool = step.get("tool") or step.get("name")
        args = step.get("args") or step.get("parameters") or {}

        if tool == "navigate":
            state["page_id"] = args.get("page_id")
        elif tool == "set_filter":
            field = args.get("field")
            value = args.get("value")
            if field:
                state["filters"][field] = value
        elif tool == "set_filters":
            for field, val in (args.get("filters") or {}).items():
                state["filters"][field] = val
        elif tool == "set_date_range":
            state["date_range"] = args.get("period") or args.get("preset") or args.get("start")
        elif tool in ("sort", "set_sort"):
            field = args.get("field")
            order = args.get("order") or args.get("direction")
            state["sort"] = {"field": field, "order": order} if order else field
        elif tool in ("compare_periods", "find_contributors", "show_trend"):
            state["metric"] = args.get("metric")
            if args.get("dimension"):
                state["dimension"] = args.get("dimension")
            if args.get("period"):
                state["date_range"] = args.get("period")

    return state


def detect_hallucinations_in_record(record: dict[str, Any], metadata: dict[str, Any]) -> int:
    """Count invalid page/filter/value references in plan plus unverified numbers in answer."""
    count = 0
    pages_map = {p["id"]: p for p in metadata.get("pages", [])}

    result = record.get("result") or {}
    plan = result.get("plan") or []

    current_page = None
    for step in plan:
        tool = step.get("tool") or step.get("name")
        args = step.get("args") or step.get("parameters") or {}

        if tool == "navigate":
            pid = args.get("page_id")
            if pid not in pages_map:
                count += 1
            else:
                current_page = pages_map[pid]
        elif tool == "set_filter":
            f_field = args.get("field")
            f_val = args.get("value")
            if current_page:
                p_filters = {f["name"]: f for f in current_page.get("filters", [])}
                if f_field not in p_filters:
                    count += 1
                else:
                    allowed = p_filters[f_field].get("allowed_values")
                    if allowed and f_val not in allowed:
                        count += 1
            else:
                count += 1
        elif tool == "set_date_range":
            dr = args.get("period") or args.get("preset") or args.get("start")
            if current_page and current_page.get("date_range_options"):
                if dr not in current_page["date_range_options"]:
                    count += 1

    unverified = result.get("faithfulness", {}).get("unverified", [])
    if isinstance(unverified, list):
        count += len(unverified)

    return count


def evaluate_single_record(record: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single test execution record against its expected values."""
    expected = record.get("expected") or {}
    result = record.get("result") or {}

    outcome = result.get("outcome", "answered")
    expected_outcome = expected.get("outcome", "answered")
    outcome_match = (outcome == expected_outcome)

    plan = result.get("plan") or []
    simulated = simulate_plan(plan)

    # Check evidence page if simulate_plan did not navigate explicitly
    evidence_page = result.get("evidence", {}).get("page")
    actual_page = simulated.get("page_id")
    if not actual_page and isinstance(evidence_page, dict):
        actual_page = evidence_page.get("id")

    exp_page = expected.get("page_id")
    routing_correct = True
    if exp_page is not None:
        routing_correct = (actual_page == exp_page)

    # Check UI-state correctness
    exp_filters = expected.get("filters") or {}
    sim_filters = simulated.get("filters") or {}
    evidence_filters = result.get("evidence", {}).get("filters") or {}
    if not sim_filters and isinstance(evidence_filters, dict):
        sim_filters = evidence_filters

    filters_correct = True
    for k, v in exp_filters.items():
        actual_v = sim_filters.get(k)
        if isinstance(actual_v, list):
            if v not in actual_v:
                filters_correct = False
        elif actual_v != v:
            filters_correct = False

    exp_date = expected.get("date_range")
    date_correct = True
    if exp_date is not None:
        actual_date = simulated.get("date_range")
        date_correct = (actual_date == exp_date)

    exp_sort = expected.get("sort")
    sort_correct = True
    if exp_sort is not None:
        actual_sort = simulated.get("sort")
        if isinstance(actual_sort, dict):
            sort_correct = (actual_sort.get("field") == exp_sort or actual_sort == exp_sort)
        else:
            sort_correct = (actual_sort == exp_sort)

    ui_state_correct = routing_correct and filters_correct and date_correct and sort_correct

    # Analysis metric and dimension check
    analysis = result.get("analysis") or {}
    actual_metric = simulated.get("metric") or analysis.get("metric")
    actual_dim = simulated.get("dimension") or analysis.get("dimension")

    metric_correct = True
    exp_metric = expected.get("metric")
    if exp_metric is not None:
        metric_correct = (actual_metric == exp_metric)

    dim_correct = True
    exp_dim = expected.get("dimension")
    if exp_dim is not None:
        dim_correct = (actual_dim == exp_dim)

    # Task success
    if expected_outcome == "answered":
        task_success = outcome_match and routing_correct and filters_correct and date_correct and sort_correct and metric_correct and dim_correct
    elif expected_outcome == "clarify":
        task_success = outcome_match or bool(result.get("clarify"))
    elif expected_outcome == "refused":
        task_success = outcome_match or bool(result.get("refusal_reason"))
    else:
        task_success = outcome_match

    # Faithfulness
    unverified = result.get("faithfulness", {}).get("unverified", [])
    faithful = (len(unverified) == 0)

    # Abstention correctness (refuse when expected, answer when not)
    abstention_correct = ((outcome == "refused") == (expected_outcome == "refused"))

    # Clarification correctness (clarify when expected, not when not)
    clarification_correct = ((outcome == "clarify") == (expected_outcome == "clarify"))

    # Hallucinations
    hallucination_count = detect_hallucinations_in_record(record, metadata)

    latency_ms = float(record.get("latency_ms") or result.get("latency_ms") or 0.0)
    steps_count = len(plan)

    failure_reason = None
    if not task_success:
        reasons = []
        if not outcome_match:
            reasons.append(f"outcome mismatch (expected {expected_outcome}, got {outcome})")
        if exp_page and not routing_correct:
            reasons.append(f"routing mismatch (expected page {exp_page}, got {actual_page})")
        if not filters_correct:
            reasons.append(f"filters mismatch (expected {exp_filters}, got {sim_filters})")
        if not date_correct:
            reasons.append(f"date mismatch (expected {exp_date}, got {simulated.get('date_range')})")
        if not sort_correct:
            reasons.append(f"sort mismatch (expected {exp_sort}, got {simulated.get('sort')})")
        if not metric_correct:
            reasons.append(f"metric mismatch (expected {exp_metric}, got {actual_metric})")
        if not dim_correct:
            reasons.append(f"dim mismatch (expected {exp_dim}, got {actual_dim})")
        failure_reason = "; ".join(reasons) or "Task requirements not met"

    return {
        "id": record.get("id"),
        "routing_correct": routing_correct,
        "has_expected_page": (exp_page is not None),
        "ui_state_correct": ui_state_correct,
        "task_success": task_success,
        "faithful": faithful,
        "abstention_correct": abstention_correct,
        "clarification_correct": clarification_correct,
        "hallucination_count": hallucination_count,
        "steps_count": steps_count,
        "latency_ms": latency_ms,
        "failure_reason": failure_reason,
    }


def aggregate_kpi_metrics(eval_details: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate individual evaluation detail dicts into KPI metrics."""
    n = len(eval_details)
    if n == 0:
        return {
            "count": 0,
            "routing_accuracy": 0.0,
            "ui_state_correctness": 0.0,
            "task_success_rate": 0.0,
            "average_steps": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
            "faithfulness": 0.0,
            "abstention_correctness": 0.0,
            "clarification_correctness": 0.0,
            "hallucination_count": 0,
        }

    routed_items = [d for d in eval_details if d["has_expected_page"]]
    routing_acc = (sum(1 for d in routed_items if d["routing_correct"]) / len(routed_items)) if routed_items else 1.0
    ui_state_acc = sum(1 for d in eval_details if d["ui_state_correct"]) / n
    task_succ = sum(1 for d in eval_details if d["task_success"]) / n
    avg_steps = sum(d["steps_count"] for d in eval_details) / n
    latencies = [d["latency_ms"] for d in eval_details]
    p50 = percentile(latencies, 0.50)
    p95 = percentile(latencies, 0.95)
    faith = sum(1 for d in eval_details if d["faithful"]) / n
    abstention = sum(1 for d in eval_details if d["abstention_correct"]) / n
    clarify = sum(1 for d in eval_details if d["clarification_correct"]) / n
    hallucinations = sum(d["hallucination_count"] for d in eval_details)

    return {
        "count": n,
        "routing_accuracy": round(routing_acc, 4),
        "ui_state_correctness": round(ui_state_acc, 4),
        "task_success_rate": round(task_succ, 4),
        "average_steps": round(avg_steps, 2),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "faithfulness": round(faith, 4),
        "abstention_correctness": round(abstention, 4),
        "clarification_correctness": round(clarify, 4),
        "hallucination_count": int(hallucinations),
    }


def compute_metrics(
    records: list[dict[str, Any]],
    metadata_sales: dict[str, Any] | None = None,
    metadata_clinic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute overall, per-group, per-language, and dev vs heldout metrics."""
    if metadata_sales is None:
        sales_path = ROOT / "data" / "app_metadata.json"
        metadata_sales = json.loads(sales_path.read_text(encoding="utf-8")) if sales_path.exists() else {}
    if metadata_clinic is None:
        clinic_path = ROOT / "data" / "apps" / "clinic" / "app_metadata.json"
        metadata_clinic = json.loads(clinic_path.read_text(encoding="utf-8")) if clinic_path.exists() else {}

    evaluated: list[tuple[dict[str, Any], dict[str, Any]]] = []
    failed_items: list[dict[str, Any]] = []

    for r in records:
        app = r.get("app", "sales")
        meta = metadata_clinic if app == "clinic" else metadata_sales
        eval_res = evaluate_single_record(r, meta)
        evaluated.append((r, eval_res))
        if not eval_res["task_success"]:
            failed_items.append({
                "id": r.get("id"),
                "message": r.get("message"),
                "group": r.get("group"),
                "language": r.get("language"),
                "split": r.get("split"),
                "reason": eval_res.get("failure_reason") or "Unknown failure",
            })

    all_details = [e[1] for e in evaluated]
    overall = aggregate_kpi_metrics(all_details)

    # By split
    splits = {"dev": [], "heldout": []}
    for r, d in evaluated:
        sp = r.get("split", "dev")
        splits.setdefault(sp, []).append(d)
    by_split = {sp: aggregate_kpi_metrics(items) for sp, items in splits.items()}

    # By group
    groups: dict[str, list[dict[str, Any]]] = {}
    for r, d in evaluated:
        g = r.get("group", "general")
        groups.setdefault(g, []).append(d)
    by_group = {g: aggregate_kpi_metrics(items) for g, items in groups.items()}

    # By language
    langs: dict[str, list[dict[str, Any]]] = {}
    for r, d in evaluated:
        l = r.get("language", "en")
        langs.setdefault(l, []).append(d)
    by_language = {l: aggregate_kpi_metrics(items) for l, items in langs.items()}

    return {
        "overall": overall,
        "by_split": by_split,
        "by_group": by_group,
        "by_language": by_language,
        "total_evaluated": len(records),
        "failed_items": failed_items,
    }
