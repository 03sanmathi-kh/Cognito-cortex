from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import main
from app.agent import _exact_demo_response
from app.tools import ToolContext
from app.timeutil import AS_OF, comparison_period, resolve_period

METADATA_PATH = ROOT / "data" / "app_metadata.json"


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def test_periods() -> list[bool]:
    anchor = date(2026, 9, 30)
    expected = {
        "today": (date(2026, 9, 30), date(2026, 9, 30)),
        "last_7_days": (date(2026, 9, 24), date(2026, 9, 30)),
        "last_30_days": (date(2026, 9, 1), date(2026, 9, 30)),
        "this_month": (date(2026, 9, 1), date(2026, 9, 30)),
        "last_month": (date(2026, 8, 1), date(2026, 8, 31)),
        "this_quarter": (date(2026, 7, 1), date(2026, 9, 30)),
        "last_quarter": (date(2026, 4, 1), date(2026, 6, 30)),
        "this_year": (date(2026, 1, 1), date(2026, 9, 30)),
        "custom": (date(2026, 9, 1), date(2026, 9, 30)),
    }
    checks = [report("default as-of date", AS_OF == anchor, str(AS_OF))]
    for name, bounds in expected.items():
        actual = resolve_period(name, anchor)
        checks.append(report(f"resolve_period {name}", actual == bounds, f"{actual}"))
    checks.append(
        report(
            "this-quarter comparison is last quarter",
            comparison_period("this_quarter", *expected["this_quarter"]) == expected["last_quarter"],
        )
    )
    return checks


def test_no_runtime_clock_calls() -> bool:
    forbidden_patterns = [
        re.compile(r"\b" + "date" + r"\s*\.\s*" + "today" + r"\s*\("),
        re.compile(r"\b" + "datetime" + r"\s*\.\s*" + "now" + r"\s*\("),
        re.compile(r"\b" + "pd" + r"\s*\.\s*" + "Timestamp" + r"\s*\.\s*" + "today" + r"\s*\("),
    ]
    directories = [BACKEND_ROOT, ROOT / "data" / "scripts"]
    matches = []
    for directory in directories:
        for path in directory.rglob("*.py"):
            relative_parts = path.relative_to(directory).parts
            if relative_parts[0] in {"venv", "__pycache__"}:
                continue
            text = path.read_text(encoding="utf-8")
            if any(pattern.search(text) for pattern in forbidden_patterns):
                matches.append(str(path.relative_to(ROOT)))
    return report("no runtime clock calls in backend/data scripts", not matches, ", ".join(matches))


def test_revenue_widget() -> list[bool]:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    page = next(page for page in metadata["pages"] if page["id"] == "revenue_by_region")
    widget = next(widget for widget in page["widgets"] if widget["id"] == "kpi_total_revenue")
    region_filter = next(item for item in page["filters"] if item["name"] == "region")
    south_filter = ["South"] if region_filter.get("type") == "multi_select" else "South"
    params = {
        "page_id": page["id"],
        "widget_id": widget["id"],
        "date_range": "this_quarter",
        "filters": json.dumps({"region": south_filter}),
    }
    client = TestClient(main.app)
    metadata_response = client.get("/api/metadata")
    metadata_as_of = metadata_response.json().get("as_of") if metadata_response.status_code == 200 else None
    checks = [
        report(
            "metadata exposes the as-of date",
            metadata_response.status_code == 200 and metadata_as_of == "2026-09-30",
            str(metadata_as_of),
        )
    ]

    demo_response = _exact_demo_response("show south revenue this quarter", ToolContext("admin"))
    demo_period = demo_response.get("plan", [])
    date_step = next(
        (step for step in demo_period if step.get("tool") == "set_date_range"),
        {},
    )
    date_args = date_step.get("args", {})
    checks.append(
        report(
            "scripted South demo uses Q3 2026",
            date_args.get("start") == "2026-07-01" and date_args.get("end") == "2026-09-30",
            f"{date_args.get('start')} to {date_args.get('end')}",
        )
    )

    south_response = client.get("/api/widget-data", params=params)
    if south_response.status_code != 200:
        return [*checks, report("South this-quarter widget request", False, south_response.text)]
    payload = south_response.json()

    with duckdb.connect(str(main.DB_PATH), read_only=True) as connection:
        direct_total = connection.execute(
            """
            SELECT COALESCE(SUM(revenue), 0)
            FROM base_sales
            WHERE region = 'South'
              AND CAST(order_date AS DATE) BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
            """
        ).fetchone()[0]

    value = payload.get("rows", [{}])[0].get("value")
    change_pct = payload.get("rows", [{}])[0].get("change_pct")
    checks.extend([
        report(
            "South this-quarter widget equals direct SQL",
            payload.get("meta", {}).get("date_range") == {"start": "2026-07-01", "end": "2026-09-30"}
            and value is not None
            and abs(float(value) - float(direct_total)) < 0.01,
            f"widget={value}, SQL={direct_total}",
        ),
        report("South this-quarter KPI change is below -15%", change_pct is not None and float(change_pct) < -15, str(change_pct)),
    ])

    all_regions = client.get(
        "/api/widget-data",
        params={
            "page_id": page["id"],
            "widget_id": widget["id"],
            "date_range": "this_quarter",
        },
    )
    if all_regions.status_code != 200:
        checks.append(report("all-region this-quarter KPI exceeds 300,000", False, all_regions.text))
    else:
        all_rows = all_regions.json().get("rows", [])
        total = float(all_rows[0]["value"]) if all_rows else 0.0
        checks.append(report("all-region this-quarter KPI exceeds 300,000", total > 300000, f"${total:,.2f}"))
    return checks


def main_test() -> None:
    checks = test_periods()
    checks.append(test_no_runtime_clock_calls())
    checks.extend(test_revenue_widget())
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main_test()
