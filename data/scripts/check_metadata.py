from __future__ import annotations

import json
from pathlib import Path

META_PATH = Path(__file__).resolve().parents[1] / "app_metadata.json"


def load_metadata():
    try:
        with META_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        raise AssertionError(f"JSON parse failed: {exc}") from exc


def validate_filter_values(doc):
    dimensions = doc["dimensions"]
    allowed_values = {
        "region": set(dimensions["regions"]),
        "channel": set(dimensions["channels"]),
        "category": {item["name"] for item in dimensions["categories"]},
    }
    errors = []
    for page in doc["pages"]:
        for filter_item in page.get("filters", []):
            name = filter_item.get("name", "")
            values = allowed_values.get(name)
            if values is None:
                continue
            for value in filter_item.get("allowed_values", []):
                if value not in values:
                    errors.append(f"{page['id']} filter '{name}' contains invalid allowed value '{value}'")
            default = filter_item.get("default")
            if isinstance(default, list):
                for value in default:
                    if value not in values:
                        errors.append(f"{page['id']} filter '{name}' invalid default '{value}'")
            elif default is not None and default not in values:
                errors.append(f"{page['id']} filter '{name}' invalid default '{default}'")
    return errors


def main():
    print("Checking metadata...")
    try:
        doc = load_metadata()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1

    pages = doc.get("pages", [])
    errors = []

    if len(pages) != 40:
        errors.append(f"Expected 40 pages, found {len(pages)}")

    page_ids = [page["id"] for page in pages]
    duplicates = sorted({value for value in page_ids if page_ids.count(value) > 1})
    if duplicates:
        errors.append(f"Duplicate page IDs: {duplicates}")

    routes = [page["route"] for page in pages]
    dup_routes = sorted({value for value in routes if routes.count(value) > 1})
    if dup_routes:
        errors.append(f"Duplicate routes: {dup_routes}")

    data_views = []
    for page in pages:
        for widget in page.get("widgets", []):
            data_view = widget.get("data_view")
            if data_view is None:
                errors.append(f"{page['id']} widget '{widget.get('id')}' missing data_view")
                continue
            data_views.append(data_view)
            expected = f"v_{page['id']}_{widget['id']}"
            if data_view != expected:
                errors.append(f"{page['id']} widget '{widget.get('id')}' has invalid data_view '{data_view}'")

    dup_data_views = sorted({value for value in data_views if data_views.count(value) > 1})
    if dup_data_views:
        errors.append(f"Duplicate data_views: {dup_data_views}")

    errors.extend(validate_filter_values(doc))

    if errors:
        print("FAIL")
        for item in errors:
            print(f" - {item}")
        return 1

    print("PASS")
    print(f"Pages: {len(pages)}")
    print(f"Unique IDs: {len(set(page_ids))}")
    print(f"Unique routes: {len(set(routes))}")
    print(f"Unique data views: {len(set(data_views))}")
    print("All filters are within the existing dimension values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
