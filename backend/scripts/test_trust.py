from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import duckdb
from fastapi.testclient import TestClient

import main as backend_main
from app.agent import (
    SYSTEM_PROMPT,
    AgentRun,
    LLMUnavailable,
    _response,
    check_confirmation_required,
    run_agent,
    validate_undo_state,
)
from app.analysis.engine import AnalysisEngine
from app.analysis.catalog import get_catalog
from app.events import (
    EVENTS_LOG_PATH,
    get_events_summary,
    log_event,
    record_verification_event,
)
from app.tools import ToolContext


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def test_evidence_query_filters() -> bool:
    """Test 1: Response evidence must report actual query filters, date range, and period used in tool execution, never screen state."""
    # Screen state has all 4 regions
    screen_ui_context = {
        "page_id": "revenue_by_region",
        "route": "/revenue/regions",
        "filters": {"region": ["East", "West", "North", "South"]},
        "date_range": "this_quarter",
    }

    run = AgentRun(
        context=ToolContext(role="admin"),
        ui_context=screen_ui_context,
        user_message="Investigate revenue drop in East",
    )

    # Agent executes tool with East only
    run.execute_investigate({
        "metric": "revenue",
        "period": "this_quarter",
        "compare_to": "previous_period",
        "filters": {"region": "East"},
    })

    # Build response
    resp = _response(run, "East revenue dropped by 15% due to supply chain issues.")
    evidence = resp.get("evidence", {})

    # Evidence filters must report East, NOT the screen state's 4 regions
    filters = evidence.get("filters", {})
    if isinstance(filters, list):
        passed_filters = any(f.get("region") in ("East", ["East"]) for f in filters if isinstance(f, dict))
        no_screen_state = not any(
            isinstance(f, dict) and isinstance(f.get("region"), list) and len(f.get("region")) == 4
            for f in filters
        )
        passed_filters = passed_filters and no_screen_state
    else:
        region_filter = filters.get("region")
        passed_filters = region_filter in ("East", ["East"])

    # Date range/period must be reported
    period = evidence.get("period") or evidence.get("date_range")
    passed_period = period is not None

    return report(
        "evidence reports actual query filters instead of screen state",
        bool(passed_filters and passed_period),
        f"filters={filters}",
    )


def test_receipts_and_unverified_numbers() -> bool:
    """Test 2: Receipts for every number, linking to catalog home_page; unverified numbers flagged."""
    catalog = get_catalog()
    rev_metric = catalog.get_metric("revenue")
    orders_metric = catalog.get_metric("orders")

    home_pages_ok = (
        rev_metric is not None
        and rev_metric.home_page == "revenue_by_region"
        and orders_metric is not None
        and orders_metric.home_page == "order_volume_trends"
    )

    run = AgentRun(
        context=ToolContext(role="admin"),
        user_message="What is the revenue?",
    )

    # Execute trend on revenue
    run.execute_show_trend({
        "metric": "revenue",
        "grain": "month",
        "period": "this_year",
        "filters": ["region:West"],
    })
    summary = run.analysis.get("summary", {}) if run.analysis else {}
    highest_obj = summary.get("highest")
    highest_val = float(highest_obj.get("value") if isinstance(highest_obj, dict) else highest_obj)

    # Craft answer with verified number and one unverified invented figure
    answer_text = f"The highest revenue was ${highest_val:,.2f}, but expected figure was $9,999,999.00."
    resp = _response(run, answer_text)

    receipts = resp.get("receipts", [])
    has_receipt = any(
        r.get("page_id") == "revenue_by_region" and abs(float(r.get("value", 0)) - float(highest_val)) < 1.0
        for r in receipts
    )

    unverified = resp.get("faithfulness", {}).get("unverified", [])
    has_unverified = any("9,999,999" in str(u) or "9999999" in str(u) for u in unverified)

    return report(
        "receipts linked to metric home_page and unverified numbers detected",
        bool(home_pages_ok and has_receipt and has_unverified),
        f"receipts_count={len(receipts)}, unverified={unverified}",
    )


def test_confirmations_rules() -> bool:
    """Test 3: requires_confirmation is True for navigating from non-default filters, >=5 steps, or reset requests."""
    # Case A: Navigating away from page with non-default filters
    nav_plan = [{"tool": "navigate", "args": {"page_id": "top_products_by_region"}}]
    req_a, reason_a = check_confirmation_required(
        "Show top products",
        nav_plan,
        screen_page_id="revenue_by_region",
        screen_filters={"region": "East"},  # non-default filter
    )
    case_a_ok = req_a is True and "filter" in str(reason_a).lower()

    # Case B: Plan has >= 5 steps
    long_plan = [
        {"tool": "navigate", "args": {"page_id": "revenue_by_region"}},
        {"tool": "set_filter", "args": {"field": "region", "value": "West"}},
        {"tool": "set_date_range", "args": {"period": "this_quarter"}},
        {"tool": "sort", "args": {"field": "revenue", "order": "desc"}},
        {"tool": "run_query", "args": {"page_id": "revenue_by_region"}},
    ]
    req_b, reason_b = check_confirmation_required(
        "Apply deep view",
        long_plan,
        screen_page_id="revenue_by_region",
        screen_filters={},
    )
    case_b_ok = req_b is True and "5" in str(reason_b)

    # Case C: User requests resetting/clearing filters
    req_c, reason_c = check_confirmation_required(
        "Please reset all filters",
        [],
        screen_page_id="revenue_by_region",
        screen_filters={},
    )
    case_c_ok = req_c is True and "reset" in str(reason_c).lower()

    # Normal Case: Default filters, short plan, regular question
    normal_plan = [{"tool": "set_filter", "args": {"field": "region", "value": "East"}}]
    req_norm, _ = check_confirmation_required(
        "Show East region",
        normal_plan,
        screen_page_id="revenue_by_region",
        screen_filters={},
    )
    case_norm_ok = req_norm is False

    return report(
        "confirmation rules (nav with filters, >=5 steps, reset requests, normal)",
        bool(case_a_ok and case_b_ok and case_c_ok and case_norm_ok),
        f"A={case_a_ok}, B={case_b_ok}, C={case_c_ok}, Norm={case_norm_ok}",
    )


def test_post_action_verification_endpoint() -> bool:
    """Test 4: /api/agent/verify match, mismatch, invalid fields dropped without error."""
    client = TestClient(backend_main.app)

    # 1. Matching verification
    res_match = client.post(
        "/api/agent/verify",
        headers={"X-Demo-Role": "admin"},
        json={
            "session_id": "sess_verify_1",
            "expected": {"page_id": "revenue_by_region", "route": "/revenue/regions", "filters": {"region": "East"}},
            "actual": {"page_id": "revenue_by_region", "route": "/revenue/regions", "filters": {"region": "East"}},
        },
    )
    data_match = res_match.json()
    match_ok = res_match.status_code == 200 and data_match.get("status") == "Verified" and data_match.get("matched") is True

    # 2. Mismatch verification
    res_mismatch = client.post(
        "/api/agent/verify",
        headers={"X-Demo-Role": "admin"},
        json={
            "session_id": "sess_verify_2",
            "expected": {"page_id": "revenue_by_region", "filters": {"region": "East"}},
            "actual": {"page_id": "order_volume_trends", "filters": {"region": "West"}},
        },
    )
    data_mismatch = res_mismatch.json()
    mismatch_ok = (
        res_mismatch.status_code == 200
        and data_mismatch.get("status") == "Mismatch"
        and data_mismatch.get("matched") is False
        and "page_id" in data_mismatch.get("differing", [])
    )

    # 3. Invalid fields dropped without error
    res_invalid_fields = client.post(
        "/api/agent/verify",
        headers={"X-Demo-Role": "admin"},
        json={
            "session_id": "sess_verify_3",
            "expected": {"page_id": "revenue_by_region", "invalid_junk_1": 12345},
            "actual": {"page_id": "revenue_by_region", "unrecognized_field_2": "test"},
        },
    )
    data_invalid = res_invalid_fields.json()
    invalid_ok = (
        res_invalid_fields.status_code == 200
        and data_invalid.get("status") == "Verified"
        and "invalid_junk_1" not in data_invalid.get("expected", {})
        and "unrecognized_field_2" not in data_invalid.get("actual", {})
    )

    return report(
        "/api/agent/verify match, mismatch, invalid fields dropped",
        bool(match_ok and mismatch_ok and invalid_ok),
        f"match={match_ok}, mismatch={mismatch_ok}, invalid_dropped={invalid_ok}",
    )


def test_trend_summary_sql_match() -> bool:
    """Test 5: engine.trend() summary includes highest, lowest, last vs prev, first to last matching direct DuckDB SQL."""
    engine = AnalysisEngine()
    res = engine.trend("revenue", "month", "this_year", filters=["region:West"])
    summary = res.get("result", {}).get("summary", {}) if "result" in res else res.get("summary", {})

    # Direct DuckDB SQL calculation
    db_path = BACKEND_ROOT.parent / "data" / "business.duckdb"
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute("""
            SELECT strftime(order_date, '%Y-%m') as m, sum(revenue) as rev
            FROM base_sales
            WHERE region = 'West' AND CAST(order_date AS DATE) >= '2026-01-01' AND CAST(order_date AS DATE) <= '2026-09-30'
            GROUP BY 1 ORDER BY 1
        """).fetchall()

    values = [r[1] for r in rows]
    highest_sql = max(values)
    lowest_sql = min(values)
    diff_sql = values[-1] - values[-2]
    pct_sql = (diff_sql / values[-2]) * 100
    first_last_sql = ((values[-1] - values[0]) / values[0]) * 100

    highest_val = float(summary.get("highest", {}).get("value") if isinstance(summary.get("highest"), dict) else summary.get("highest", 0))
    lowest_val = float(summary.get("lowest", {}).get("value") if isinstance(summary.get("lowest"), dict) else summary.get("lowest", 0))

    highest_match = abs(highest_val - highest_sql) < 0.05
    lowest_match = abs(lowest_val - lowest_sql) < 0.05
    diff_match = abs(summary.get("last_vs_previous", {}).get("absolute_change", 0) - diff_sql) < 0.05
    pct_match = abs(summary.get("last_vs_previous", {}).get("percent_change", 0) - pct_sql) < 0.05
    fl_match = abs(summary.get("first_to_last", {}).get("percent_change", 0) - first_last_sql) < 0.05

    all_matched = highest_match and lowest_match and diff_match and pct_match and fl_match
    return report(
        "trend summary matches direct DuckDB SQL",
        all_matched,
        f"highest={highest_match}, lowest={lowest_match}, diff={diff_match}, pct={pct_match}, fl={fl_match}",
    )


def test_events_log_and_summary_endpoint() -> bool:
    """Test 6: Telemetry logging to .cache/events.jsonl (no API keys) and GET /api/events/summary endpoint."""
    client = TestClient(backend_main.app)

    # 1. Log a test event
    logged = log_event(
        session_id="test_sess_telemetry",
        role="analyst",
        outcome="answered",
        number_of_plan_steps=2,
        number_of_tool_calls=3,
        latency_ms=120.5,
    )
    assert logged["session_id"] == "test_sess_telemetry"

    # Verify no API keys in file
    with EVENTS_LOG_PATH.open("r", encoding="utf-8") as handle:
        content = handle.read()
        no_keys = "gemini_api_key" not in content.lower() and "ai_key" not in content.lower()

    # 2. Call GET /api/events/summary
    res_summary = client.get("/api/events/summary", headers={"X-Demo-Role": "admin"})
    summary_data = res_summary.json()
    summary_ok = (
        res_summary.status_code == 200
        and summary_data.get("total_requests", 0) >= 1
        and "counts_by_outcome" in summary_data
        and "average_latency_ms" in summary_data
    )

    # 3. Test empty summary helper
    with tempfile.TemporaryDirectory() as tmp_dir:
        empty_path = Path(tmp_dir) / "empty_events.jsonl"
        empty_summary = get_events_summary(empty_path)
        empty_ok = empty_summary.get("total_requests") == 0 and empty_summary.get("counts_by_outcome") == {}

    return report(
        "events log security and /api/events/summary",
        bool(no_keys and summary_ok and empty_ok),
        f"no_keys={no_keys}, summary_ok={summary_ok}, empty_ok={empty_ok}",
    )


def test_system_prompt_trend_takeaway() -> bool:
    """Test 7: System prompt contains trend takeaway instructions (one sentence using summary, <= 6 bullets)."""
    has_trend_instruction = (
        "trend" in SYSTEM_PROMPT.lower()
        and "takeaway" in SYSTEM_PROMPT.lower()
        and "bullets" in SYSTEM_PROMPT.lower()
    )
    return report(
        "system prompt trend takeaway instruction",
        has_trend_instruction,
    )


def test_normalize_filters() -> bool:
    """Test Task C: normalize_filters with a dict, a list of dicts, a list of strings, an empty value, None and junk."""
    from app.agent import normalize_filters

    # 1. with a dict
    res_dict = normalize_filters({"region": "West", "channel": "Retail"})
    d_ok = res_dict == {"region": "West", "channel": "Retail"}

    # 2. with a list of dicts (both key-value items and field/value items)
    res_lod1 = normalize_filters([{"field": "region", "value": "South"}, {"key": "channel", "value": "Direct"}])
    res_lod2 = normalize_filters([{"region": ["South"]}, {"category": "Beverages"}])
    lod_ok = (
        res_lod1 == {"region": "South", "channel": "Direct"}
        and res_lod2 == {"region": ["South"], "category": "Beverages"}
    )

    # 3. with a list of strings
    res_los = normalize_filters(["region=East", "channel: Retail", "category:Beverages"])
    los_ok = res_los == {"region": "East", "channel": "Retail", "category": "Beverages"}

    # 4. with an empty value
    res_empty_list = normalize_filters([])
    res_empty_str = normalize_filters("")
    res_empty_dict = normalize_filters({})
    empty_ok = res_empty_list == {} and res_empty_str == {} and res_empty_dict == {}

    # 5. with None
    res_none = normalize_filters(None)
    none_ok = res_none == {}

    # 6. with junk
    res_junk_int = normalize_filters(12345)
    res_junk_list = normalize_filters([object(), 999, "not_a_key_value", None, [1, 2]])
    junk_ok = res_junk_int == {} and res_junk_list == {}

    all_ok = d_ok and lod_ok and los_ok and empty_ok and none_ok and junk_ok
    return report(
        "normalize_filters helper with dict, list of dicts, list of strings, empty, None, junk",
        all_ok,
        f"dict={d_ok}, lod={lod_ok}, los={los_ok}, empty={empty_ok}, none={none_ok}, junk={junk_ok}",
    )


def test_mocked_analysis_evidence_filters_list() -> bool:
    """Test Task C: mocked analysis run whose evidence filters are a list returns 200 with correct region in evidence."""
    from app.agent import normalize_filters, LLMUnavailable

    client = TestClient(backend_main.app)

    # 1. Test offline analysis run for South revenue drop which produces a list of query filters
    with patch("app.agent._with_llm", side_effect=LLMUnavailable("offline test")):
        res_real = client.post(
            "/api/agent",
            headers={"X-Demo-Role": "admin"},
            json={"message": "Why did South revenue drop this quarter?", "role": "admin"},
        )
    status_real_ok = res_real.status_code == 200
    data_real = res_real.json() if status_real_ok else {}
    ev_filters_real = data_real.get("evidence", {}).get("filters")
    is_list_real = isinstance(ev_filters_real, list)
    norm_real = normalize_filters(ev_filters_real)
    region_real_ok = norm_real.get("region") in ("South", ["South"])

    # 2. Test explicit mocked analysis run where evidence filters are a list of {"field", "value"} items
    mock_analysis_result = {
        "plan": [],
        "answer": "South region revenue dropped by 22.5%.",
        "evidence": {
            "page": {"id": "revenue_by_region", "title": "Revenue by Region"},
            "filters": [{"field": "region", "value": "South"}],
            "query": "SELECT SUM(revenue) FROM base_sales WHERE region = 'South'",
        },
        "chart": None,
        "error": None,
        "clarify": None,
        "outcome": "answered",
        "analysis": {"type": "investigate", "metric": "revenue"},
        "session_id": "sess_mock_list",
    }
    with patch("app.agent._with_llm", return_value=mock_analysis_result):
        res_mock = client.post(
            "/api/agent",
            headers={"X-Demo-Role": "admin"},
            json={"message": "Explain South drop", "role": "admin"},
        )

    status_mock_ok = res_mock.status_code == 200
    data_mock = res_mock.json() if status_mock_ok else {}
    ev_filters_mock = data_mock.get("evidence", {}).get("filters")
    is_list_mock = isinstance(ev_filters_mock, list)
    norm_mock = normalize_filters(ev_filters_mock)
    region_mock_ok = norm_mock.get("region") in ("South", ["South"])

    passed = status_real_ok and is_list_real and region_real_ok and status_mock_ok and is_list_mock and region_mock_ok
    return report(
        "mocked analysis run with evidence filters as a list returns 200 with correct region",
        passed,
        f"real_200={status_real_ok}, real_list={is_list_real}, real_region={region_real_ok}, mock_200={status_mock_ok}, mock_list={is_list_mock}, mock_region={region_mock_ok}",
    )


def test_receipt_south_revenue_date_range() -> bool:
    """Test: a receipt for South revenue this quarter has date_range == 'this_quarter'."""
    client = TestClient(backend_main.app)
    with patch("app.agent._with_llm", side_effect=LLMUnavailable("offline test")):
        res = client.post(
            "/api/agent",
            headers={"X-Demo-Role": "admin"},
            json={"message": "Why did South revenue drop this quarter?", "role": "admin"},
        )
    status_ok = res.status_code == 200
    data = res.json() if status_ok else {}
    receipts = data.get("receipts", [])
    has_receipt = bool(receipts) and any(r.get("date_range") == "this_quarter" for r in receipts)
    no_raw_dict = all(not isinstance(r.get("date_range"), dict) and "{" not in str(r.get("date_range")) for r in receipts)
    passed = status_ok and has_receipt and no_raw_dict
    return report(
        "receipt for South revenue this quarter has date_range == 'this_quarter'",
        passed,
        f"status={status_ok}, receipts_count={len(receipts)}, date_ranges={[r.get('date_range') for r in receipts[:3]]}",
    )


def test_undo_restores_sort_direction() -> bool:
    """Test: validate_undo_state and /api/agent/undo restore exact sort direction (desc and asc)."""
    context = ToolContext(role="admin")

    # 1. Test validate_undo_state directly with desc
    state_desc = {
        "page_id": "revenue_by_region",
        "sort": "gross_revenue",
        "sort_direction": "desc",
    }
    restored_desc = validate_undo_state(state_desc, context)
    desc_ok = (
        restored_desc.get("sort") == "gross_revenue"
        and (restored_desc.get("sort_direction") == "desc" or restored_desc.get("direction") == "desc")
    )

    # 2. Test validate_undo_state directly with asc
    state_asc = {
        "page_id": "revenue_by_region",
        "sort": "gross_revenue",
        "sort_direction": "asc",
    }
    restored_asc = validate_undo_state(state_asc, context)
    asc_ok = (
        restored_asc.get("sort") == "gross_revenue"
        and (restored_asc.get("sort_direction") == "asc" or restored_asc.get("direction") == "asc")
    )

    # 3. Test through /api/agent/undo endpoint
    client = TestClient(backend_main.app)
    res_undo_desc = client.post(
        "/api/undo",
        headers={"X-Demo-Role": "admin"},
        json={"role": "admin", "state": state_desc},
    )
    undo_desc_data = res_undo_desc.json().get("restored", {}) if res_undo_desc.status_code == 200 else {}
    endpoint_desc_ok = (
        res_undo_desc.status_code == 200
        and undo_desc_data.get("sort") == "gross_revenue"
        and (undo_desc_data.get("sort_direction") == "desc" or undo_desc_data.get("direction") == "desc")
    )

    res_undo_asc = client.post(
        "/api/undo",
        headers={"X-Demo-Role": "admin"},
        json={"role": "admin", "state": state_asc},
    )
    undo_asc_data = res_undo_asc.json().get("restored", {}) if res_undo_asc.status_code == 200 else {}
    endpoint_asc_ok = (
        res_undo_asc.status_code == 200
        and undo_asc_data.get("sort") == "gross_revenue"
        and (undo_asc_data.get("sort_direction") == "asc" or undo_asc_data.get("direction") == "asc")
    )

    passed = desc_ok and asc_ok and endpoint_desc_ok and endpoint_asc_ok
    return report(
        "undo restores 'desc' and 'asc' correctly",
        passed,
        f"desc={desc_ok}, asc={asc_ok}, api_desc={endpoint_desc_ok}, api_asc={endpoint_asc_ok}",
    )


def main() -> int:
    print("\n--- Running Trust & Verification Tests (Step 9A) ---")
    results = [
        test_evidence_query_filters(),
        test_receipts_and_unverified_numbers(),
        test_confirmations_rules(),
        test_post_action_verification_endpoint(),
        test_trend_summary_sql_match(),
        test_events_log_and_summary_endpoint(),
        test_system_prompt_trend_takeaway(),
        test_normalize_filters(),
        test_mocked_analysis_evidence_filters_list(),
        test_receipt_south_revenue_date_range(),
        test_undo_restores_sort_direction(),
    ]

    all_passed = all(results)
    print(f"\nResult: {'ALL PASS' if all_passed else 'SOME FAILED'} ({sum(results)}/{len(results)})")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

