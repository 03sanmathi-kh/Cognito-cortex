import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.graph import get_graph
from app.retrieval import build_index
from app.tools import ToolContext, get_tool_registry, run_tool

METADATA_PATH = ROOT / "data" / "app_metadata.json"


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def main() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    build_index(metadata)
    get_graph()

    analyst = ToolContext("analyst")
    admin = ToolContext("admin")
    regional_manager = ToolContext("regional_manager")
    scoped_page = next(
        page for page in metadata["pages"]
        if page.get("region_scoped") and any(item.get("name", "").casefold() == "region" for item in page.get("filters", []))
    )
    page_id = scoped_page["id"]
    region_filter = next(item for item in scoped_page["filters"] if item["name"].casefold() == "region")
    admin_page = next(page for page in metadata["pages"] if page.get("allowed_roles") == ["admin"])
    confirm_page, confirm_action = next(
        (page, action)
        for page in metadata["pages"]
        for action in page.get("actions", [])
        if action.get("id") == "export_csv" and action.get("requires_confirmation")
    )

    checks = []
    fake_page = run_tool("navigate", {"page_id": "not_a_metadata_page"}, analyst)
    checks.append(report("fake navigation returns suggestions", not fake_page["ok"] and bool(fake_page["suggestions"])))

    invalid_filters = run_tool("set_filters", {"page_id": page_id, "filters": {"region": "Southwest"}}, analyst)
    checks.append(report("invalid region suggests South", not invalid_filters["ok"] and "South" in invalid_filters["suggestions"]))
    accepted_filters = run_tool("set_filters", {"page_id": page_id, "filters": {"region": "south"}}, analyst)
    region_result = accepted_filters.get("data", {}).get("filters", {}).get("region")
    canonical_region = region_result[0] if isinstance(region_result, list) and region_result else region_result
    checks.append(report("region value canonicalized", accepted_filters["ok"] and canonical_region == "South"))

    denied_navigation = run_tool("navigate", {"page_id": admin_page["id"]}, analyst)
    checks.append(report("analyst cannot navigate admin-only page", not denied_navigation["ok"] and denied_navigation["error"]["code"] == "role_not_permitted"))
    denied_action = run_tool("run_page_action", {"page_id": confirm_page["id"], "action_id": confirm_action["id"]}, analyst)
    checks.append(report("analyst cannot run confirmation action", not denied_action["ok"] and denied_action["error"]["code"] == "role_not_permitted"))
    confirmed_action = run_tool("run_page_action", {"page_id": confirm_page["id"], "action_id": confirm_action["id"]}, admin)
    checks.append(report("export action carries confirmation requirement", confirmed_action["ok"] and confirmed_action["requires_confirmation"]))

    invalid_sort = run_tool("set_sort", {"page_id": page_id, "field": "not_a_sort_field", "direction": "asc"}, analyst)
    checks.append(report("unknown sort field rejected", not invalid_sort["ok"] and invalid_sort["error"]["code"] == "invalid_sort"))

    rejected_sql = [
        "DROP TABLE base_sales",
        "INSERT INTO base_sales SELECT * FROM base_sales",
        "ATTACH 'other.db' AS other",
        "PRAGMA version",
        "SELECT 1; SELECT 2",
        "SELECT * FROM read_csv('secret.csv')",
    ]
    sql_rejections = [run_tool("query_data", {"sql": sql}, analyst) for sql in rejected_sql]
    checks.append(report("rejects destructive, external, pragma, and multi-statement SQL", all(not result["ok"] for result in sql_rejections)))

    disallowed_relation = run_tool("query_data", {"sql": "SELECT * FROM information_schema.tables"}, analyst)
    checks.append(report("rejects relations outside the allowlist", not disallowed_relation["ok"] and bool(disallowed_relation["suggestions"])))

    limited = run_tool("query_data", {"sql": "SELECT * FROM base_sales"}, analyst)
    checks.append(report("caps analytics results at 500 rows", limited["ok"] and limited["data"]["row_count"] <= 500 and "LIMIT 500" in limited["receipt"]["sql"]))

    regional_queries = [
        "SELECT region, SUM(revenue) AS revenue FROM base_sales GROUP BY region",
        "SELECT * FROM (SELECT region, revenue FROM base_sales) AS sales",
        "WITH sales AS (SELECT region, revenue FROM base_sales) SELECT * FROM sales",
        "SELECT region, SUM(revenue) AS revenue FROM base_sales GROUP BY region UNION ALL SELECT region, SUM(revenue) AS revenue FROM base_sales GROUP BY region",
    ]
    regional_results = [run_tool("query_data", {"sql": sql}, regional_manager) for sql in regional_queries]
    regional_rows = [row for result in regional_results if result["ok"] for row in result["data"]["rows"]]
    checks.append(report("regional manager sees only South through nested queries and CTEs", len(regional_results) == len(regional_queries) and all(result["ok"] for result in regional_results) and all(row.get("region") == "South" for row in regional_rows) and bool(regional_rows)))

    registry = get_tool_registry()
    schemas_valid = bool(registry) and all(
        isinstance(tool.get("name"), str)
        and isinstance(tool.get("description"), str)
        and isinstance(tool.get("input_schema"), dict)
        and tool["input_schema"].get("type") == "object"
        and isinstance(tool["input_schema"].get("properties"), dict)
        and isinstance(tool["input_schema"].get("required"), list)
        for tool in registry
    )
    checks.append(report("registry schemas are valid JSON tool input schemas", schemas_valid, str(len(registry))))

    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
