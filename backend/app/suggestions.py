from __future__ import annotations

import re
from typing import Any

from app.graph import accessible_pages, get_page
from app.analysis.catalog import get_catalog


def generate_suggestions(page_id: str, role: str) -> list[str]:
    """Generate 3 proactive suggestion chips for an accessible page without LLM calls."""
    allowed = {p["id"] for p in accessible_pages(role)}
    if page_id not in allowed:
        return []

    page = get_page(page_id)
    if not page:
        return []

    # Find relevant metric from catalog
    catalog = get_catalog()
    metric_label = None
    for metric in catalog.list_metrics():
        if page_id in metric.page_ids or metric.home_page == page_id:
            metric_label = metric.label
            break

    # If no catalog metric matched, derive from page widgets or title
    if not metric_label:
        widgets = page.get("widgets") or []
        for w in widgets:
            if w.get("type") == "kpi":
                metric_label = w.get("title") or (w.get("measures") or [None])[0]
                if metric_label:
                    break
            elif w.get("type") in {"bar_chart", "line_chart", "pie_chart"}:
                title = w.get("title", "")
                if title:
                    metric_label = title.split(" by ")[0].replace("Total ", "").strip()
                    break

    if not metric_label:
        title = page.get("title", page_id)
        metric_label = re.sub(r"\b(Overview|Summary|Analytics|Hub|Report|Deep Dive|Health)\b", "", title, flags=re.IGNORECASE).strip()
    if not metric_label:
        metric_label = "Metrics"

    # Find dimension from page filters or widgets
    dimension_label = None
    filters = page.get("filters") or []
    if filters:
        first_filter = filters[0]
        dimension_label = first_filter.get("label") or first_filter.get("name")

    if not dimension_label:
        for w in page.get("widgets") or []:
            title = w.get("title", "")
            if " by " in title:
                dimension_label = title.split(" by ")[-1].strip()
                break

    if not dimension_label:
        dimension_label = "dimension"

    # Time frame (quarter by default, month if clinic)
    period = "this_quarter"
    period_str = "this quarter"
    date_options = page.get("date_range_options") or []
    if "this_month" in date_options and "this_quarter" not in date_options:
        period_str = "this month"

    chip1 = f"Why did {metric_label} change {period_str}?"
    chip2 = f"Compare {metric_label} by {dimension_label.lower()}"
    chip3 = f"Show {metric_label} trend"

    return [chip1, chip2, chip3]
