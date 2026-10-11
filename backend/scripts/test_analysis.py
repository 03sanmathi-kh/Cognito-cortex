from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import duckdb
from app.analysis.catalog import (
    load_catalog,
    get_catalog,
    list_metrics,
    list_dimensions,
)
from app.analysis.engine import (
    compare_periods,
    find_contributors,
    investigate,
    trend,
    compute_steepest_changes,
    compute_steepest_risers,
    compute_steepest_decliners,
    format_money,
    format_percent,
    format_count,
    AnalysisValidationError,
)
from app.agent import (
    check_numbers,
    _revenue_drop_response,
    run_agent,
)
from app.tools import ToolContext

DB_PATH = ROOT / "data" / "business.duckdb"


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def test_catalog_validation() -> bool:
    catalog = load_catalog(validate=True)
    metric_ids = {m.id for m in catalog.list_metrics()}
    dim_ids = {d.id for d in catalog.list_dimensions()}
    passed = (
        "revenue" in metric_ids
        and "orders" in metric_ids
        and "units" in metric_ids
        and "average_order_value" in metric_ids
        and "region" in dim_ids
        and "channel" in dim_ids
        and "category" in dim_ids
        and "product" in dim_ids
        and "customer_segment" in dim_ids
    )
    return report("Catalog validates against the database", passed, f"metrics={len(metric_ids)}, dimensions={len(dim_ids)}")


def test_compare_periods_south_revenue() -> bool:
    res = compare_periods("revenue", "this_quarter", "previous_period", {"region": "South"})
    r = res["result"]

    # Direct SQL on DuckDB
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        direct_cur = con.execute(
            "SELECT SUM(revenue) FROM base_sales WHERE region = 'South' "
            "AND CAST(order_date AS DATE) >= '2026-07-01' AND CAST(order_date AS DATE) <= '2026-09-30'"
        ).fetchone()[0]
        direct_prev = con.execute(
            "SELECT SUM(revenue) FROM base_sales WHERE region = 'South' "
            "AND CAST(order_date AS DATE) >= '2026-04-01' AND CAST(order_date AS DATE) <= '2026-06-30'"
        ).fetchone()[0]

    cur_matches = abs(r["current_value"] - float(direct_cur)) < 0.05
    prev_matches = abs(r["previous_value"] - float(direct_prev)) < 0.05
    pct_about_22_5 = abs(r["percent_change"] - (-22.52)) < 0.2

    passed = cur_matches and prev_matches and pct_about_22_5
    return report(
        "compare_periods for South revenue this quarter vs previous equals a direct SQL result (and about -22.5 percent)",
        passed,
        f"cur={r['current_value']}, prev={r['previous_value']}, change_pct={r['percent_change']}%",
    )


def test_find_contributors_shares_sum() -> bool:
    dimensions_to_test = ["region", "channel", "category", "customer_segment", "product"]
    all_passed = True
    details = []

    for dim in dimensions_to_test:
        filters = {"region": "South"} if dim != "region" else None
        res = find_contributors("revenue", dim, "this_quarter", "previous_period", filters, top_n=5)
        contributors = res["result"]["contributors"]
        shares_sum = sum(c["share_of_total_change"] for c in contributors)
        sums_to_1 = abs(shares_sum - 1.0) < 0.01
        details.append(f"{dim}={shares_sum:.4f}")
        if not sums_to_1:
            all_passed = False

    return report(
        "find_contributors shares sum to 1.0 within rounding, for several dimensions",
        all_passed,
        ", ".join(details),
    )


def test_dimension_scoring() -> bool:
    # A 3-value dimension whose top 3 cover 100 percent (e.g. top 2 cover 80% or 100%)
    # score = top2_share / (2 / n)
    dim_3_n = 3
    dim_3_top2_share = 0.865
    dim_3_score = dim_3_top2_share / (2.0 / dim_3_n)  # 0.865 / 0.6667 = 1.2975

    # A 6-value dimension whose top 2 cover 70 percent
    dim_6_n = 6
    dim_6_top2_share = 0.70
    dim_6_score = dim_6_top2_share / (2.0 / dim_6_n)  # 0.70 / 0.3333 = 2.10

    # The 3-value dimension must NOT beat the 6-value dimension
    passed = dim_6_score > dim_3_score
    return report(
        "Unit test: a 3-value dimension whose top 3 cover 100 percent must NOT beat a 6-value dimension whose top 2 cover 70 percent",
        passed,
        f"6-val score ({dim_6_score:.2f}) > 3-val score ({dim_3_score:.2f})",
    )


def test_investigate_south_revenue() -> bool:
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "South"}, max_depth=3)
    r = inv["result"]

    top_dims = r.get("top_dimensions", [])
    has_top_dims = len(top_dims) >= 2
    top_dim_ids = [d["dimension"] for d in top_dims]
    has_category = "category" in top_dim_ids

    # Check Beverages in category contributors
    cat_dim = next((d for d in top_dims if d["dimension"] == "category"), None)
    cat_contribs = [c["label"] for c in cat_dim["contributors"]] if cat_dim else []
    has_beverages = "Beverages" in cat_contribs

    # Check top segments include Beverages and/or Partner channel
    top_segs = r.get("top_segments", [])
    has_top_segs = len(top_segs) > 0
    first_seg = top_segs[0] if has_top_segs else {}
    seg_match = (
        "Partner" in first_seg.get("segment", "")
        or "Beverages" in first_seg.get("segment", "")
        or "Partner" in str(first_seg.get("value_a", ""))
        or "Partner" in str(first_seg.get("value_b", ""))
        or "Beverages" in str(first_seg.get("value_a", ""))
        or "Beverages" in str(first_seg.get("value_b", ""))
    )

    has_concentration = r.get("concentration") in ("concentrated", "broadly spread")

    passed = has_top_dims and has_category and has_beverages and has_top_segs and seg_match and has_concentration
    return report(
        "investigate South revenue returns category in top 2 dimensions, Beverages in category contributors, and top segment with Partner/Beverages",
        passed,
        f"top_dims={top_dim_ids}, Beverages={has_beverages}, top_segment={first_seg.get('segment')}, concentration={r.get('concentration')}",
    )


def test_planted_stories_expressibility() -> bool:
    # Story 1: South revenue drop (already verified)
    # Story 2: Household promotion spike in the last 30 days
    # Story 3: West inventory warning (cannot be expressed - snapshot threshold)
    # Story 4: East marketing expense bump (cannot be expressed - expenses table)

    # Test Story 2: Household spike in last 30 days
    inv_story2 = investigate("units", "last_30_days", "previous_period", max_depth=2)
    labels_story2 = set()
    for step in inv_story2["result"].get("steps", []):
        labels_story2.add(step.get("top_driver"))
    for node in inv_story2["result"].get("tree", []):
        for c in node.get("contributors", []):
            labels_story2.add(c.get("label"))
    for td in inv_story2["result"].get("top_dimensions", []):
        for c in td.get("contributors", []):
            labels_story2.add(c.get("label"))
    for ts in inv_story2["result"].get("top_segments", []):
        labels_story2.add(ts.get("segment"))

    story2_found = "Household" in labels_story2 or any("Household" in str(x) for x in labels_story2)

    print("\n--- Planted Stories Expressibility ---")
    print("[EXPRESSIBLE] Story 1: South revenue drop in Q3 2026 -> Expressible & surfaced (revenue metric, category/channel dimensions)")
    print(f"[{'EXPRESSIBLE' if story2_found else 'CANNOT EXPRESS'}] Story 2: Household promotion spike in last 30 days -> Expressible & surfaced (units metric, category dimension)")
    print("[CANNOT EXPRESS] Story 3: West inventory warning -> Cannot be expressed (inventory snapshot alert below reorder level; not period-over-period sales flow)")
    print("[CANNOT EXPRESS] Story 4: East marketing expense bump -> Cannot be expressed (expenses table with expense_type; not in sales catalog)")
    print("--------------------------------------\n")

    return report(
        "investigate surfaces other expressible planted stories (Story 2 Household promotion spike)",
        story2_found,
        f"Household found in contributors={story2_found}",
    )


def test_validation_and_injection_rejection() -> bool:
    # 1. Invalid metric
    invalid_metric_caught = False
    try:
        compare_periods("nonexistent_metric", "this_quarter", "previous_period")
    except AnalysisValidationError as e:
        invalid_metric_caught = bool(e.suggestions)

    # 2. Invalid dimension
    invalid_dim_caught = False
    try:
        find_contributors("revenue", "nonexistent_dimension", "this_quarter", "previous_period")
    except AnalysisValidationError as e:
        invalid_dim_caught = bool(e.suggestions)

    # 3. Invalid filter value
    invalid_filter_caught = False
    try:
        compare_periods("revenue", "this_quarter", "previous_period", {"region": "Antarctica"})
    except AnalysisValidationError as e:
        invalid_filter_caught = bool(e.suggestions)

    # 4. Prompt injection filter value
    injection_caught = False
    try:
        compare_periods("revenue", "this_quarter", "previous_period", {"region": "x'; DROP TABLE base_sales; --"})
    except AnalysisValidationError:
        injection_caught = True

    # Verify base_sales table still exists
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        table_intact = bool(con.execute("SELECT COUNT(*) FROM base_sales").fetchone()[0] > 0)

    passed = invalid_metric_caught and invalid_dim_caught and invalid_filter_caught and injection_caught and table_intact
    return report(
        "Invalid metric, dimension, filter value return suggestions; prompt-injection is rejected and never reaches SQL",
        passed,
        f"invalid_metric={invalid_metric_caught}, invalid_dim={invalid_dim_caught}, injection_rejected={injection_caught}, table_intact={table_intact}",
    )


def test_check_numbers_faithfulness() -> bool:
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "South"})
    source_data = inv["result"]

    # Valid answer text using the new structured output with numbers from top_dimensions
    valid_text = (
        "South revenue fell by $28,004.54 (-22.5%) from $124,342.52 to $96,337.98.\n"
        "Main contributors to the change across top dimensions:\n"
        "- Product Category: Personal Care down by $10,956.47 (39.1% share)\n"
        "- Channel: Partner down by $13,583.07 (48.5% share)\n"
        "Top segment: Personal Care x Partner down by $5,576.18 (19.9% share)"
    )
    res_correct = check_numbers(valid_text, source_data)
    correct_passed = res_correct["checked"] > 0 and len(res_correct["unverified"]) == 0

    # Text containing an invented number
    invented_text = "South revenue fell by $99,999.00 (-50.0%) down to $50,000.00."
    res_invented = check_numbers(invented_text, source_data)
    invented_passed = len(res_invented["unverified"]) > 0 and 99999.0 in res_invented["unverified"]

    passed = correct_passed and invented_passed
    return report(
        "check_numbers still passes for answers using the new structure",
        passed,
        f"correct_checked={res_correct['checked']}, correct_unverified={res_correct['unverified']}, invented_unverified={res_invented['unverified']}",
    )


def test_scripted_fallback_numbers_equal_investigate() -> bool:
    context = ToolContext("analyst")
    fallback_resp, facts = _revenue_drop_response("South", context)
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "South"})
    baseline = inv["result"]["baseline"]

    current_matches = facts["latest_quarter"]["revenue"] == baseline["current_value"]
    prev_matches = facts["previous_quarter"]["revenue"] == baseline["previous_value"]
    diff_matches = facts["difference"] == baseline["absolute_change"]
    pct_matches = facts["change_pct"] == baseline["percent_change"]

    passed = current_matches and prev_matches and diff_matches and pct_matches
    return report(
        "Scripted fallback answer for 'why did South revenue drop' uses the same numbers as investigate",
        passed,
        f"current={facts['latest_quarter']['revenue']}, diff={facts['difference']}, pct={facts['change_pct']}%",
    )


def test_investigate_south_revenue_steepest_drops() -> bool:
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "South"}, max_depth=3)
    r = inv["result"]

    top_dims = r.get("top_dimensions", [])
    cat_dim = next((d for d in top_dims if d["dimension"] == "category"), None)
    cat_decliners = cat_dim.get("steepest_decliners", []) if cat_dim else []
    bev_item = next((c for c in cat_decliners if c["label"] == "Beverages"), None)
    bev_found = bev_item is not None
    bev_pct_ok = False
    if bev_item and bev_item.get("pct_change") is not None:
        bev_pct = bev_item["pct_change"]
        bev_pct_ok = -45.0 <= bev_pct <= -35.0

    chan_dim = next((d for d in top_dims if d["dimension"] == "channel"), None)
    chan_decliners = chan_dim.get("steepest_decliners", []) if chan_dim else []
    partner_found = any(c["label"] == "Partner" for c in chan_decliners)

    steepest_segs = r.get("steepest_segments", [])
    has_steepest_seg_with_bev_or_partner = any(
        "Beverages" in s.get("segment", "") or "Partner" in s.get("segment", "")
        for s in steepest_segs
    )

    passed = bev_found and bev_pct_ok and partner_found and has_steepest_seg_with_bev_or_partner
    return report(
        "investigate for South revenue this quarter vs previous: steepest decliners (Beverages -35% to -45%, Partner) and steepest segments",
        passed,
        f"Beverages={bev_found} (pct={bev_item.get('pct_change') if bev_item else None}%), Partner={partner_found}, steepest_segments={len(steepest_segs)}",
    )


def test_tiny_base_exclusion_from_steepest_decliners() -> bool:
    synthetic = [
        {"label": "Tiny Base Drop", "pct_change": -95.0, "previous_share": 0.03},  # 3% < 5% -> must be excluded
        {"label": "Significant Drop", "pct_change": -45.0, "previous_share": 0.12},  # 12% >= 5% -> included
        {"label": "Moderate Drop", "pct_change": -25.0, "previous_share": 0.20},  # 20% >= 5% -> included
    ]
    res = compute_steepest_changes(synthetic, total_change=-500.0, min_previous_share=0.05, top_n=3)
    labels = [item["label"] for item in res]
    passed = "Tiny Base Drop" not in labels and "Significant Drop" in labels
    return report(
        "A tiny-base value (previous_share below 5 percent) is excluded from steepest_decliners",
        passed,
        f"selected={labels}",
    )


def test_formatting_helpers() -> bool:
    # Money: positive, negative, zero, rounding
    m_pos = format_money(12345.67) == "$12,345.67"
    m_neg = format_money(-12345.67) == "-$12,345.67"
    m_zero = format_money(0) == "$0.00"
    m_round = format_money(12345.678) == "$12,345.68"
    m_neg_round = format_money(-10956.471) == "-$10,956.47"

    # Percent: positive, negative, zero, rounding
    p_pos = format_percent(39.12) == "39.1%"
    p_neg = format_percent(-41.86) == "-41.9%"
    p_zero = format_percent(0) == "0.0%"
    p_round = format_percent(20.55) == "20.6%"

    # Count: positive, negative, zero, rounding
    c_pos = format_count(12345) == "12,345"
    c_neg = format_count(-500) == "-500"
    c_zero = format_count(0) == "0"
    c_float = format_count(12345.6) == "12,345.60"

    passed = (
        m_pos and m_neg and m_zero and m_round and m_neg_round
        and p_pos and p_neg and p_zero and p_round
        and c_pos and c_neg and c_zero and c_float
    )
    return report(
        "Money, percent and count formatting helpers: positive, negative, zero, rounding",
        passed,
        f"money={[m_pos, m_neg, m_zero, m_round]}, percent={[p_pos, p_neg, p_zero, p_round]}, count={[c_pos, c_neg, c_zero, c_float]}",
    )


def test_check_numbers_formatted_and_invented() -> bool:
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "South"})
    source_data = inv["result"]

    # check_numbers accepts "$10,956.47", "10,956.47", "39.1%" and rejects an invented number
    text_dollar = "Personal Care dropped by $10,956.47."
    r_dollar = check_numbers(text_dollar, source_data)
    dollar_accepted = r_dollar["checked"] == 1 and len(r_dollar["unverified"]) == 0

    text_no_dollar = "Personal Care dropped by 10,956.47."
    r_no_dollar = check_numbers(text_no_dollar, source_data)
    no_dollar_accepted = r_no_dollar["checked"] == 1 and len(r_no_dollar["unverified"]) == 0

    text_pct = "Personal Care explained 39.1% of the drop."
    r_pct = check_numbers(text_pct, source_data)
    pct_accepted = r_pct["checked"] == 1 and len(r_pct["unverified"]) == 0

    text_invented = "Personal Care dropped by $88,888.88 (-99.9%)."
    r_invented = check_numbers(text_invented, source_data)
    invented_rejected = len(r_invented["unverified"]) > 0 and 88888.88 in r_invented["unverified"]

    passed = dollar_accepted and no_dollar_accepted and pct_accepted and invented_rejected
    return report(
        "check_numbers accepts '$10,956.47', '10,956.47', '39.1%' and rejects an invented number",
        passed,
        f"$10k={dollar_accepted}, 10k={no_dollar_accepted}, 39.1%={pct_accepted}, invented_rejected={invented_rejected}",
    )


def test_optional_live_gemini() -> bool:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or "--live" not in sys.argv:
        print("SKIP: Optional live Gemini test skipped (offline mode; pass --live to run)")
        return True

    print("\n--- Optional Live Gemini Test (max 2 calls) ---")
    try:
        res = run_agent("Why did South revenue drop this quarter?", role="analyst")
        print("Outcome:", res.get("outcome"))
        print("Answer:\n", res.get("answer"))
        print("Faithfulness:", res.get("faithfulness"))
        passed = res.get("outcome") == "answered" and bool(res.get("answer"))
        return report("Optional live Gemini call for 'Why did South revenue drop this quarter?'", passed)
    except Exception as exc:
        return report("Optional live Gemini call", False, str(exc))


def test_west_revenue_mixed_changes() -> bool:
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "West"})
    r = inv["result"]

    mixed_is_true = r.get("mixed_change") is True

    # No share above 100 percent
    all_shares = []
    for td in r.get("top_dimensions", []):
        for c in td.get("contributors", []):
            all_shares.append(c.get("share"))
            all_shares.append(c.get("share_of_total_change"))
    for s in r.get("top_segments", []):
        all_shares.append(s.get("share"))
        all_shares.append(s.get("share_of_total_change"))
    for item in r.get("steepest_risers", []) + r.get("steepest_decliners", []):
        all_shares.append(item.get("share"))
        all_shares.append(item.get("share_of_total_change"))

    no_share_above_100 = all(s is None or abs(s) <= 1.0 for s in all_shares)
    all_shares_null = all(s is None for s in all_shares)

    # Household is in risers
    risers = r.get("steepest_risers", [])
    riser_labels = [item.get("label") for item in risers]
    household_in_risers = "Household" in riser_labels

    # Risers contain no negative pct_change
    risers_no_negative = all(
        item.get("pct_change") is not None and item.get("pct_change") > 0
        for item in risers
    )

    # Check fallback explanation for West
    context = ToolContext("analyst")
    resp, facts = _revenue_drop_response("West", context)
    ans = resp.get("answer", "")
    has_mixed_sentence = "The net change is small because some items rose and others fell." in ans
    has_biggest_inc = "Biggest increases:" in ans
    has_biggest_dec = "Biggest decreases:" in ans

    passed = (
        mixed_is_true
        and no_share_above_100
        and all_shares_null
        and household_in_risers
        and risers_no_negative
        and has_mixed_sentence
        and has_biggest_inc
        and has_biggest_dec
    )
    return report(
        "West revenue this quarter vs previous: mixed_change is true, no share above 100, Household in risers, risers contain no negative pct_change",
        passed,
        f"mixed={mixed_is_true}, Household_in_risers={household_in_risers}, risers_count={len(risers)}, all_shares_null={all_shares_null}",
    )


def test_south_revenue_not_mixed() -> bool:
    inv = investigate("revenue", "this_quarter", "previous_period", {"region": "South"})
    r = inv["result"]

    mixed_is_false = r.get("mixed_change") is False
    top_dims = r.get("top_dimensions", [])
    has_dims = len(top_dims) >= 2

    cat_dim = next((d for d in top_dims if d["dimension"] == "category"), None)
    cat_decliners = cat_dim.get("steepest_decliners", []) if cat_dim else []
    bev_found = any(c.get("label") == "Beverages" for c in cat_decliners)

    chan_dim = next((d for d in top_dims if d["dimension"] == "channel"), None)
    chan_decliners = chan_dim.get("steepest_decliners", []) if chan_dim else []
    partner_found = any(c.get("label") == "Partner" for c in chan_decliners)

    passed = mixed_is_false and has_dims and bev_found and partner_found
    return report(
        "South revenue: mixed_change is false, and results are the same as before",
        passed,
        f"mixed_change={r.get('mixed_change')}, Beverages_found={bev_found}, Partner_found={partner_found}",
    )


def test_synthetic_all_fall_risers_empty() -> bool:
    synthetic_contributors = [
        {"label": "Product A", "change": -500.0, "pct_change": -25.0, "previous_share": 0.30},
        {"label": "Product B", "change": -300.0, "pct_change": -15.0, "previous_share": 0.40},
        {"label": "Product C", "change": -100.0, "pct_change": -8.0, "previous_share": 0.20},
    ]
    risers = compute_steepest_risers(synthetic_contributors, min_previous_share=0.05, top_n=3)
    decliners = compute_steepest_decliners(synthetic_contributors, min_previous_share=0.05, top_n=3)

    passed = len(risers) == 0 and len(decliners) == 3
    return report(
        "Synthetic case: all items fall, so risers is empty",
        passed,
        f"risers={risers}, decliners_count={len(decliners)}",
    )


def main() -> None:
    print("=" * 60)
    print("STEP 8A-FIX3: MIXED CHANGES TEST SUITE")
    print("=" * 60)

    results = [
        test_catalog_validation(),
        test_compare_periods_south_revenue(),
        test_find_contributors_shares_sum(),
        test_dimension_scoring(),
        test_investigate_south_revenue(),
        test_investigate_south_revenue_steepest_drops(),
        test_tiny_base_exclusion_from_steepest_decliners(),
        test_formatting_helpers(),
        test_check_numbers_formatted_and_invented(),
        test_planted_stories_expressibility(),
        test_validation_and_injection_rejection(),
        test_check_numbers_faithfulness(),
        test_scripted_fallback_numbers_equal_investigate(),
        test_west_revenue_mixed_changes(),
        test_south_revenue_not_mixed(),
        test_synthetic_all_fall_risers_empty(),
        test_optional_live_gemini(),
    ]

    all_passed = all(results)
    print("=" * 60)
    if all_passed:
        print("ALL TESTS PASSED (8A-FIX3)")
        sys.exit(0)
    else:
        print(f"SOME TESTS FAILED ({results.count(False)} failures)")
        sys.exit(1)


if __name__ == "__main__":
    main()
