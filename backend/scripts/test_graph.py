import json
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.graph import (
    METADATA_PATH,
    accessible_pages,
    get_graph,
    get_valid_filters,
    is_valid_filter,
    suggest_pages,
)


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def main() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    graph = get_graph()
    counts = Counter(attributes.get("type", "unknown") for _, attributes in graph.nodes(data=True))
    print("Node counts:", dict(sorted(counts.items())))

    checks = []
    checks.append(report("expected metadata graph counts", counts.get("app") == 1 and counts.get("directory") == len(metadata.get("directories", [])) and counts.get("page") == len(metadata.get("pages", [])) and counts.get("widget") == sum(len(page.get("widgets", [])) for page in metadata.get("pages", []))))

    scoped_page = next((
        page for page in metadata.get("pages", [])
        if page.get("region_scoped") and any(item.get("name") == "region" for item in page.get("filters", []))
    ), None)
    region_filter = next((item for item in (scoped_page or {}).get("filters", []) if item.get("name") == "region"), {})
    region_values = [str(value) for value in region_filter.get("allowed_values", [])]
    page_id = str((scoped_page or {}).get("id", ""))
    valid_region = region_values[0] if region_values else None
    accepted = is_valid_filter(page_id, "region", valid_region) if scoped_page and valid_region else {"valid": False}
    checks.append(report("accepts a real region value", accepted.get("valid", False), str(valid_region)))

    rejected = is_valid_filter(page_id, "region", "Southwest") if scoped_page else {"valid": True}
    nearest = rejected.get("suggestions", [])
    checks.append(report("rejects an invalid region and suggests the nearest value", not rejected.get("valid", True) and bool(nearest) and nearest[0] in region_values, str(nearest)))

    suggestions = suggest_pages("revenue by regon", k=5)
    titles = [str(item.get("title", "")) for item in suggestions]
    matching_titles = [title for title in titles if "revenue by region" in title.casefold()]
    checks.append(report("typo query suggests Revenue by Region", bool(matching_titles) and titles.index(matching_titles[0]) < 3, ", ".join(titles[:3])))

    admin_only_ids = {
        str(page.get("id"))
        for page in metadata.get("pages", [])
        if set(page.get("allowed_roles") or []) == {"admin"}
    }
    analyst_ids = {str(page.get("id")) for page in accessible_pages("analyst")}
    checks.append(report("analyst excludes admin-only pages", not (admin_only_ids & analyst_ids)))

    similar_sources = {
        source
        for source, _, edge in graph.edges(data=True)
        if edge.get("type") == "similar_to"
    }
    checks.append(report("at least eight pages have similar-page edges", len(similar_sources) >= 8, str(len(similar_sources))))

    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
