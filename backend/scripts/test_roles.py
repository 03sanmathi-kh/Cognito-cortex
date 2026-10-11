import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import main

METADATA_PATH = ROOT / "data" / "app_metadata.json"


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def role_allows(page: dict, role: str) -> bool:
    allowed = page.get("allowed_roles") or []
    if isinstance(allowed, str):
        allowed = [allowed]
    return not allowed or role in allowed


def main_test() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    all_pages = metadata.get("pages", [])
    client = TestClient(main.app)
    checks = []

    admin = client.get("/api/metadata", headers={"X-Demo-Role": "admin"})
    analyst = client.get("/api/metadata", headers={"X-Demo-Role": "analyst"})
    regional = client.get("/api/metadata", headers={"X-Demo-Role": "regional_manager"})
    analyst_ids = {page["id"] for page in analyst.json().get("pages", [])}
    regional_ids = {page["id"] for page in regional.json().get("pages", [])}
    expected_analyst = {page["id"] for page in all_pages if role_allows(page, "analyst")}
    expected_regional = {page["id"] for page in all_pages if role_allows(page, "regional_manager") or role_allows(page, "analyst")}
    admin_only_ids = {page["id"] for page in all_pages if page.get("allowed_roles") == ["admin"]}
    checks.append(report("admin sees all 40 pages", admin.status_code == 200 and len(admin.json().get("pages", [])) == 40))
    checks.append(report("analyst sees no admin-only pages", analyst.status_code == 200 and not (analyst_ids & admin_only_ids)))
    checks.append(report("regional manager sees metadata-authorized pages", regional.status_code == 200 and analyst_ids == expected_analyst and regional_ids == expected_regional and regional_ids.issuperset(analyst_ids)))

    inherited_page = next(page for page in all_pages if page.get("allowed_roles") == ["admin", "analyst"])
    inherited_access = client.get(
        "/api/page-access",
        params={"path": inherited_page["route"]},
        headers={"X-Demo-Role": "regional_manager"},
    )
    checks.append(report("regional manager can directly open an analyst-visible page", inherited_access.status_code == 200 and inherited_access.json().get("accessible")))

    admin_page = next(page for page in all_pages if page.get("allowed_roles") == ["admin"])
    admin_widget = admin_page["widgets"][0]
    denied_widget = client.get(
        "/api/widget-data",
        params={"page_id": admin_page["id"], "widget_id": admin_widget["id"]},
        headers={"X-Demo-Role": "analyst"},
    )
    checks.append(report("analyst gets 403 for admin-only widget data", denied_widget.status_code == 403))

    scoped_page = next(
        page for page in all_pages
        if page.get("region_scoped")
        and any(str(item.get("name", "")).casefold() == "region" for item in page.get("filters", []))
        and any(widget.get("type") == "grid" and "region" in (widget.get("columns") or []) for widget in page.get("widgets", []))
    )
    region_filter = next(item for item in scoped_page["filters"] if str(item.get("name", "")).casefold() == "region")
    requested_region = ["North"] if region_filter.get("type") == "multi_select" else "North"
    grid_widget = next(widget for widget in scoped_page["widgets"] if widget.get("type") == "grid" and "region" in (widget.get("columns") or []))
    scoped_response = client.get(
        "/api/widget-data",
        params={
            "page_id": scoped_page["id"],
            "widget_id": grid_widget["id"],
            "filters": json.dumps({region_filter["name"]: requested_region}),
        },
        headers={"X-Demo-Role": "regional_manager"},
    )
    scoped_data = scoped_response.json()
    filters_applied = scoped_data.get("meta", {}).get("filters_applied", {})
    applied_region = filters_applied.get(region_filter["name"])
    rows = scoped_data.get("rows", [])
    rows_are_south = all(row.get("region") == "South" for row in rows if "region" in row)
    checks.append(report(
        "regional manager North request is forced to South",
        scoped_response.status_code == 200
        and applied_region in ("South", ["South"])
        and rows_are_south
        and bool(rows),
        f"filters_applied={filters_applied}, row_count={len(rows)}",
    ))

    unknown_role = client.get("/api/metadata", headers={"X-Demo-Role": "unknown_role"})
    checks.append(report("unknown role header returns 400", unknown_role.status_code == 400))

    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main_test()
