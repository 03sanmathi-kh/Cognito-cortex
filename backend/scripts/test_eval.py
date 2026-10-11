from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

# Force offline mode
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["OFFLINE_TESTS"] = "1"
os.environ["LLM_CACHE"] = "1"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from eval.metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    percentile,
    simulate_plan,
    evaluate_single_record,
    compute_metrics,
)
from eval.run_eval import load_completed_ids, execute_item_with_retry
from eval.retrieval_bench import build_synthetic_catalog, run_benchmark
from eval.report import generate_report
from app.llm import LLMRateLimited


def report(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    msg = f"{status}: {name}"
    if detail:
        msg += f" - {detail}"
    print(msg)
    return passed


def test_metric_functions() -> bool:
    checks = []

    # 1. Ranking metrics
    ranked = ["doc_b", "doc_a", "doc_c", "doc_d", "doc_e"]
    # precision@k for single target
    p1 = precision_at_k(ranked, "doc_b", 1)  # 1.0
    p1_fail = precision_at_k(ranked, "doc_a", 1)  # 0.0
    p5 = precision_at_k(ranked, "doc_a", 5)  # 0.2
    checks.append(report("precision_at_k math", p1 == 1.0 and p1_fail == 0.0 and abs(p5 - 0.2) < 1e-5))

    # recall@k
    r1 = recall_at_k(ranked, "doc_b", 1)  # 1.0
    r1_fail = recall_at_k(ranked, "doc_a", 1)  # 0.0
    r5 = recall_at_k(ranked, "doc_a", 5)  # 1.0
    checks.append(report("recall_at_k math", r1 == 1.0 and r1_fail == 0.0 and r5 == 1.0))

    # reciprocal rank (MRR)
    mrr_1 = reciprocal_rank(ranked, "doc_b")  # 1.0
    mrr_2 = reciprocal_rank(ranked, "doc_a")  # 0.5
    mrr_none = reciprocal_rank(ranked, "doc_z")  # 0.0
    checks.append(report("reciprocal_rank math", mrr_1 == 1.0 and mrr_2 == 0.5 and mrr_none == 0.0))

    # percentile math (p50, p95)
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    p50 = percentile(vals, 0.50)  # 30.0
    p95 = percentile(vals, 0.95)  # 48.0
    checks.append(report("percentile p50 and p95 math", p50 == 30.0 and 45.0 <= p95 <= 50.0))

    # 2. Plan simulation & single record evaluation
    plan = [
        {"tool": "navigate", "args": {"page_id": "revenue_by_region"}},
        {"tool": "set_filter", "args": {"field": "region", "value": "South"}},
        {"tool": "set_date_range", "args": {"period": "this_quarter"}},
        {"tool": "sort", "args": {"field": "revenue", "order": "desc"}},
    ]
    sim = simulate_plan(plan)
    state_ok = (
        sim["page_id"] == "revenue_by_region"
        and sim["filters"].get("region") == "South"
        and sim["date_range"] == "this_quarter"
        and sim["sort"] == {"field": "revenue", "order": "desc"}
    )
    checks.append(report("simulate_plan correctly applies navigation, filters, dates, sort", state_ok))

    # Record evaluation (successful match)
    rec_ok = {
        "id": "t1",
        "expected": {
            "outcome": "answered",
            "page_id": "revenue_by_region",
            "filters": {"region": "South"},
            "date_range": "this_quarter",
            "sort": "revenue",
        },
        "result": {
            "outcome": "answered",
            "plan": plan,
            "evidence": {"page": {"id": "revenue_by_region"}, "filters": {"region": "South"}},
            "faithfulness": {"checked": 1, "unverified": []},
            "latency_ms": 120.0,
        },
    }
    sales_meta = json.loads((ROOT / "data" / "app_metadata.json").read_text(encoding="utf-8"))
    res_eval = evaluate_single_record(rec_ok, sales_meta)
    checks.append(report("evaluate_single_record passes for matching record", res_eval["task_success"] and res_eval["faithful"]))

    # Record evaluation (failure: unverified number & wrong page)
    rec_bad = {
        "id": "t2",
        "expected": {
            "outcome": "answered",
            "page_id": "top_products_by_region",
        },
        "result": {
            "outcome": "answered",
            "plan": plan,  # navigated to revenue_by_region instead
            "evidence": {"page": {"id": "revenue_by_region"}},
            "faithfulness": {"checked": 2, "unverified": [999999.0]},
            "latency_ms": 150.0,
        },
    }
    res_bad_eval = evaluate_single_record(rec_bad, sales_meta)
    checks.append(report(
        "evaluate_single_record fails on page mismatch and catches hallucinated number",
        not res_bad_eval["task_success"] and not res_bad_eval["faithful"] and res_bad_eval["hallucination_count"] >= 1,
    ))

    return all(checks)


def test_testset_validation() -> bool:
    checks = []
    testset_path = ROOT / "eval" / "testset.json"
    checks.append(report("eval/testset.json exists", testset_path.exists()))

    data = json.loads(testset_path.read_text(encoding="utf-8"))
    total_count = len(data)
    checks.append(report("testset has exactly 70 items", total_count == 70, f"got {total_count}"))

    sales_items = [i for i in data if i.get("app") == "sales"]
    clinic_items = [i for i in data if i.get("app") == "clinic"]
    checks.append(report("testset has 60 sales and 10 clinic items", len(sales_items) == 60 and len(clinic_items) == 10))

    heldout = [i for i in data if i.get("split") == "heldout"]
    checks.append(report("testset has about 15 heldout items", 14 <= len(heldout) <= 16, f"got {len(heldout)}"))

    en_sales = [i for i in sales_items if i.get("language") == "en"]
    hi_sales = [i for i in sales_items if i.get("language") == "hi"]
    kn_sales = [i for i in sales_items if i.get("language") == "kn"]
    checks.append(report("sales mix is 40 en, 10 hi, 10 kn", len(en_sales) == 40 and len(hi_sales) == 10 and len(kn_sales) == 10))

    # Validate all page IDs and filter values against actual metadata
    sales_meta = json.loads((ROOT / "data" / "app_metadata.json").read_text(encoding="utf-8"))
    clinic_meta = json.loads((ROOT / "data" / "apps" / "clinic" / "app_metadata.json").read_text(encoding="utf-8"))

    sales_pages = {p["id"]: p for p in sales_meta["pages"]}
    clinic_pages = {p["id"]: p for p in clinic_meta["pages"]}

    metadata_errors = []
    for item in data:
        pages_dict = clinic_pages if item.get("app") == "clinic" else sales_pages
        exp = item.get("expected", {})
        pid = exp.get("page_id")
        if pid:
            if pid not in pages_dict:
                metadata_errors.append(f"item {item['id']} unknown page {pid}")
                continue
            page_obj = pages_dict[pid]
            for f_name, f_val in (exp.get("filters") or {}).items():
                p_filters = {f["name"]: f for f in page_obj.get("filters", [])}
                if f_name not in p_filters:
                    metadata_errors.append(f"item {item['id']} page {pid} missing filter {f_name}")
                else:
                    allowed = p_filters[f_name].get("allowed_values")
                    if allowed:
                        vals = [f_val] if isinstance(f_val, str) else f_val
                        for v in vals:
                            if v not in allowed:
                                metadata_errors.append(f"item {item['id']} filter value {v} not in {allowed}")

            dr = exp.get("date_range")
            if dr and page_obj.get("date_range_options"):
                if dr not in page_obj["date_range_options"]:
                    metadata_errors.append(f"item {item['id']} date_range {dr} not in {page_obj['date_range_options']}")

    checks.append(report(
        "every expected page, filter, and date_range exists in metadata",
        len(metadata_errors) == 0,
        f"errors: {metadata_errors[:3] if metadata_errors else 'none'}",
    ))

    return all(checks)


def test_runner_resume_and_rate_limit() -> bool:
    checks = []

    # 1. Test resume skips saved IDs
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_run_file = Path(tmp_dir) / "test_run.jsonl"
        saved_records = [
            {"id": "sales-001", "result": {"outcome": "answered"}},
            {"id": "sales-002", "result": {"outcome": "answered"}},
        ]
        with open(tmp_run_file, "w", encoding="utf-8") as f:
            for r in saved_records:
                f.write(json.dumps(r) + "\n")

        loaded = load_completed_ids(tmp_run_file)
        resume_ok = (loaded == {"sales-001", "sales-002"})
        checks.append(report("load_completed_ids correctly finds saved IDs", resume_ok))

    # 2. Test runner survives rate-limit error with backoff retry
    test_item = {
        "id": "mock-001",
        "app": "sales",
        "role": "analyst",
        "message": "Open revenue by region",
        "previous": None,
    }

    call_count = 0

    def mock_run_agent_with_rate_limit(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise LLMRateLimited("Gemini 429 RESOURCE_EXHAUSTED: Rate limit persisted.")
        return {
            "plan": [{"tool": "navigate", "args": {"page_id": "revenue_by_region"}}],
            "outcome": "answered",
            "answer": "Navigated to revenue by region.",
            "faithfulness": {"checked": 0, "unverified": []},
        }

    with patch("eval.run_eval.run_agent", side_effect=mock_run_agent_with_rate_limit):
        res = execute_item_with_retry(test_item, max_retries=1, backoff_delay=0.01)
        retry_survived = (call_count == 2 and res.get("outcome") == "answered")
        checks.append(report(
            "runner survives mocked rate-limit error and succeeds on retry",
            retry_survived,
            f"calls={call_count}, outcome={res.get('outcome')}",
        ))

    return all(checks)


def test_retrieval_benchmark_fixture() -> bool:
    checks = []
    # Test synthetic catalog generation
    comps, queries = build_synthetic_catalog(seed=42)
    cat_ok = (len(comps) >= 300 and len(queries) >= 60)
    checks.append(report("synthetic catalog generates 300+ components and 60+ queries", cat_ok, f"comps={len(comps)}, queries={len(queries)}"))

    # Test full benchmark execution (offline)
    bench_res = run_benchmark(seed=42)
    methods_present = all(k in bench_res for k in ("bm25", "faiss", "hybrid"))
    metrics_valid = True
    for m in ("bm25", "faiss", "hybrid"):
        d = bench_res[m]
        if not (0.0 <= d["p1"] <= 1.0 and 0.0 <= d["mrr"] <= 1.0 and d["index_time_s"] >= 0.0):
            metrics_valid = False

    checks.append(report(
        "retrieval benchmark runs and returns valid P@1, MRR, latency for all 3 methods",
        methods_present and metrics_valid,
        f"hybrid_p1={bench_res.get('hybrid', {}).get('p1')}, hybrid_mrr={bench_res.get('hybrid', {}).get('mrr')}",
    ))

    return all(checks)


def test_report_writer_partial_run() -> bool:
    checks = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        run_file = tmp_path / "partial_run.jsonl"
        out_md = tmp_path / "results.md"
        out_json = tmp_path / "results.json"

        # Write partial run: 3 items out of 70
        partial_records = [
            {
                "id": "sales-001",
                "app": "sales",
                "language": "en",
                "group": "navigation",
                "split": "dev",
                "message": "Open revenue by region",
                "expected": {"outcome": "answered", "page_id": "revenue_by_region"},
                "result": {
                    "outcome": "answered",
                    "plan": [{"tool": "navigate", "args": {"page_id": "revenue_by_region"}}],
                    "evidence": {"page": {"id": "revenue_by_region"}},
                    "faithfulness": {"checked": 0, "unverified": []},
                    "latency_ms": 95.0,
                },
                "latency_ms": 95.0,
            },
            {
                "id": "sales-002",
                "app": "sales",
                "language": "en",
                "group": "navigation",
                "split": "dev",
                "message": "Go to top products by region",
                "expected": {"outcome": "answered", "page_id": "top_products_by_region"},
                "result": {
                    "outcome": "answered",
                    "plan": [{"tool": "navigate", "args": {"page_id": "top_products_by_region"}}],
                    "evidence": {"page": {"id": "top_products_by_region"}},
                    "faithfulness": {"checked": 0, "unverified": []},
                    "latency_ms": 110.0,
                },
                "latency_ms": 110.0,
            },
        ]
        with open(run_file, "w", encoding="utf-8") as f:
            for r in partial_records:
                f.write(json.dumps(r) + "\n")

        # Mock retrieval summary to make test fast
        mock_retrieval = {
            "total_components": 320,
            "total_queries": 64,
            "bm25": {"p1": 0.672, "p5": 0.138, "r5": 0.688, "r10": 0.688, "mrr": 0.682, "index_time_s": 0.003, "avg_query_time_ms": 0.6},
            "faiss": {"p1": 0.703, "p5": 0.147, "r5": 0.734, "r10": 0.734, "mrr": 0.712, "index_time_s": 7.5, "avg_query_time_ms": 8.5},
            "hybrid": {"p1": 0.703, "p5": 0.141, "r5": 0.703, "r10": 0.703, "mrr": 0.707, "index_time_s": 7.5, "avg_query_time_ms": 8.8},
        }

        report_data = generate_report(
            run_file=run_file,
            testset_file=ROOT / "eval" / "testset.json",
            out_md=out_md,
            out_json=out_json,
            retrieval_summary=mock_retrieval,
        )

        md_content = out_md.read_text(encoding="utf-8")
        has_measured_line = "Measured on 2 requests; targets are not results" in md_content
        has_partial_notice = "Partial Run Notice" in md_content
        has_unrun_count = report_data.get("unrun_count") == 68
        no_missing_filled = report_data.get("items_run") == 2

        checks.append(report(
            "report writer works with partial run, reports unrun count, and includes required notice line",
            has_measured_line and has_partial_notice and has_unrun_count and no_missing_filled,
            f"items_run={report_data.get('items_run')}, unrun={report_data.get('unrun_count')}",
        ))

    return all(checks)


def main() -> None:
    print("--- Running Evaluation Harness Tests (Step 5) ---")
    results = [
        test_metric_functions(),
        test_testset_validation(),
        test_runner_resume_and_rate_limit(),
        test_retrieval_benchmark_fixture(),
        test_report_writer_partial_run(),
    ]
    all_passed = all(results)
    print("\nResult:", "ALL PASS" if all_passed else "SOME FAILED", f"({sum(results)}/{len(results)})")
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
