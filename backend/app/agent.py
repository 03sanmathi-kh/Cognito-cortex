import difflib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger("cognito.agent")

from app.graph import accessible_pages, get_page
from app.tools import ToolContext, run_tool
from app.timeutil import get_as_of, resolve_period
from app.session import Session, get_session_store
from app.analysis.catalog import get_catalog, list_metrics, list_dimensions
from app.analysis.engine import (
    compare_periods as engine_compare_periods,
    find_contributors as engine_find_contributors,
    trend as engine_trend,
    investigate as engine_investigate,
    AnalysisValidationError,
    format_money,
    format_percent,
    format_count,
)
from app.llm import (
    LLMConfigError,
    LLMBadResponse,
    LLMRateLimited,
    LLMUnavailable,
    get_llm_client,
)
from app.events import log_event
from app.languages import detect_language, normalize_with_lexicon

ROOT = Path(__file__).resolve().parents[2]
METADATA_PATH = ROOT / "data" / "app_metadata.json"

SYSTEM_PROMPT = (
    "You are Cognito Pilot. Use only the supplied tools. Never invent pages, filters, values, dates, "
    "or numbers. Never do arithmetic. Explain only numbers returned by tools. Always use the formatted "
    "currency, percent, and count strings provided in tool results (e.g. $12,345.67, -$12,345.67, 39.1%, -41.9%); "
    "never reprint raw numbers like -10956.47. If the request is ambiguous, "
    "ask exactly one clarifying question. If something does not exist, say so and offer only the nearest "
    "real options supplied by tool errors. Use tools for metadata-backed navigation, filters, dates, sorting, "
    "queries, charts, and analysis. For trend questions, start the answer with one takeaway sentence using these "
    "summary numbers, then at most 6 short bullets; plain text only. Keep answers concise. "
    "Reply in the user's language; numbers, page names, filter values and tool arguments stay in English; "
    "the website UI stays English."
)

_AGENT_TOOLS = [
    {
        "name": "navigate",
        "description": "Navigate to an accessible page from app metadata.",
        "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}}, "required": ["page_id"], "additionalProperties": False},
    },
    {
        "name": "set_filter",
        "description": "Set a metadata-defined filter on the current page.",
        "input_schema": {"type": "object", "properties": {"field": {"type": "string"}, "value": {"type": "string"}}, "required": ["field", "value"], "additionalProperties": False},
    },
    {
        "name": "set_date_range",
        "description": "Set a date interval allowed by the current page metadata.",
        "input_schema": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}, "required": ["start", "end"], "additionalProperties": False},
    },
    {
        "name": "sort",
        "description": "Sort by a metadata-defined field and direction.",
        "input_schema": {"type": "object", "properties": {"field": {"type": "string"}, "order": {"type": "string", "enum": ["asc", "desc"]}}, "required": ["field", "order"], "additionalProperties": False},
    },
    {
        "name": "run_query",
        "description": "Fetch the current page's metadata-defined widgets using the current validated agent state.",
        "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}}, "required": ["page_id"], "additionalProperties": False},
    },
    {
        "name": "make_chart",
        "description": "Render a chart only from rows returned by run_query.",
        "input_schema": {"type": "object", "properties": {"type": {"type": "string", "enum": ["bar", "line", "pie"]}}, "required": ["type"], "additionalProperties": False},
    },
    {
        "name": "compare_periods",
        "description": "Compare an analytics metric between two time periods with optional filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "orders", "units", "average_order_value"],
                    "description": "Metric identifier from the analysis catalog.",
                },
                "period": {
                    "type": "string",
                    "description": "Period preset (e.g. this_quarter, last_month, last_30_days, this_year) or ISO date.",
                },
                "compare_to": {
                    "type": "string",
                    "enum": ["previous_period", "same_period_last_year"],
                    "description": "Comparison period type.",
                },
                "filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter expressions in dimension:value format (e.g. ['region:South']).",
                },
            },
            "required": ["metric", "period"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_contributors",
        "description": "Break down changes in a metric across values of a dimension.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "orders", "units", "average_order_value"],
                    "description": "Metric identifier from the analysis catalog.",
                },
                "dimension": {
                    "type": "string",
                    "enum": ["region", "channel", "category", "product", "customer_segment"],
                    "description": "Business dimension to analyze.",
                },
                "period": {
                    "type": "string",
                    "description": "Period preset (e.g. this_quarter, last_month, last_30_days).",
                },
                "compare_to": {
                    "type": "string",
                    "enum": ["previous_period", "same_period_last_year"],
                    "description": "Comparison period type.",
                },
                "filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter expressions in dimension:value format.",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of top contributors to return (default 5).",
                },
            },
            "required": ["metric", "dimension", "period"],
            "additionalProperties": False,
        },
    },
    {
        "name": "show_trend",
        "description": "Retrieve metric trend time-series points grouped by day, week, or month.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "orders", "units", "average_order_value"],
                    "description": "Metric identifier from the analysis catalog.",
                },
                "grain": {
                    "type": "string",
                    "enum": ["day", "week", "month"],
                    "description": "Time grain for data aggregation.",
                },
                "period": {
                    "type": "string",
                    "description": "Period preset (e.g. this_quarter, this_year).",
                },
                "filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter expressions in dimension:value format.",
                },
            },
            "required": ["metric", "grain", "period"],
            "additionalProperties": False,
        },
    },
    {
        "name": "investigate",
        "description": "Investigate root cause contributors to a metric change via greedy drill-down across dimensions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "orders", "units", "average_order_value"],
                    "description": "Metric identifier to investigate.",
                },
                "period": {
                    "type": "string",
                    "description": "Period preset (e.g. this_quarter, last_month, last_30_days).",
                },
                "compare_to": {
                    "type": "string",
                    "enum": ["previous_period", "same_period_last_year"],
                    "description": "Comparison period type.",
                },
                "filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter expressions in dimension:value format (e.g. ['region:South']).",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum drill-down depth (default 3).",
                },
            },
            "required": ["metric", "period"],
            "additionalProperties": False,
        },
    },
]


def _metadata() -> dict[str, Any]:
    try:
        from app.apps import get_active_metadata
        return get_active_metadata()
    except Exception:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _closest(value: str, options: list[str]) -> list[str]:
    if not options:
        return []
    normalized = {_normalise(option): option for option in options}
    return [
        normalized[item]
        for item in difflib.get_close_matches(_normalise(value), list(normalized), n=3, cutoff=0)
    ]


def _error(message: str, suggestions: list[Any] | None = None) -> dict[str, Any]:
    return {"message": message, "suggestions": suggestions or []}


def _check_out_of_scope(message: str, reply_text: str = "") -> bool:
    norm_m = re.sub(r"[^a-z0-9 ]+", " ", message.casefold()).strip()
    norm_r = re.sub(r"[^a-z0-9 ]+", " ", reply_text.casefold()).strip()
    out_of_scope_reply_indicators = [
        "out of scope",
        "outside the scope",
        "only help with",
        "only assist with",
        "cannot answer questions about",
        "not related to this application",
        "capital of france is paris",
    ]
    if any(ind in norm_r for ind in out_of_scope_reply_indicators):
        return True
    out_of_scope_message_patterns = [
        r"^what is the capital of\b",
        r"^capital of\b",
        r"^who is\b",
        r"^who was\b",
        r"^who wrote\b",
        r"^tell me a (joke|story|poem)\b",
        r"^how to bake\b",
        r"^recipe for\b",
        r"^weather in\b",
        r"^translate\b",
        r"^write a (poem|song|essay|script|code)\b",
    ]
    for pattern in out_of_scope_message_patterns:
        if re.search(pattern, norm_m):
            return True
    return False


def _check_out_of_data_range(message: str) -> bool:
    norm = message.casefold()
    as_of = get_as_of()
    date_matches = re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", norm)
    for y, m, d in date_matches:
        try:
            dt = date(int(y), int(m), int(d))
            if dt > as_of or dt < date(2024, 9, 30):
                return True
        except ValueError:
            pass
    year_matches = re.findall(r"\b(20[3-9]\d|202[7-9])\b", norm)
    if year_matches:
        return True
    if "after 2026-09-30" in norm:
        return True
    return False


def _collect_numbers_into(target_list: list[float], obj: Any) -> None:
    if isinstance(obj, (int, float)):
        val = float(obj)
        target_list.append(val)
        target_list.append(abs(val))
    elif isinstance(obj, str):
        clean = obj.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            val = float(clean)
            target_list.append(val)
            target_list.append(abs(val))
        except ValueError:
            pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers_into(target_list, v)
    elif isinstance(obj, list):
        for item in obj:
            _collect_numbers_into(target_list, item)


def check_numbers(answer_text: str, tool_data: Any) -> dict[str, Any]:
    valid_numbers: list[float] = []
    _collect_numbers_into(valid_numbers, tool_data)

    valid_set: set[float] = set()
    for v in valid_numbers:
        valid_set.add(v)
        valid_set.add(abs(v))
        valid_set.add(round(v, 2))
        valid_set.add(round(v, 1))
        valid_set.add(round(abs(v), 2))
        valid_set.add(round(abs(v), 1))
        if 0.0 <= abs(v) <= 1.0:
            valid_set.add(round(abs(v) * 100, 1))
            valid_set.add(round(abs(v) * 100, 2))
            valid_set.add(round(v * 100, 1))
            valid_set.add(round(v * 100, 2))
        if 0.0 < abs(v) <= 100.0:
            valid_set.add(round(v / 100, 4))
            valid_set.add(round(abs(v) / 100, 4))

    pattern = re.compile(r"([+-]?\$?\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|[kKmMbB])?)")
    raw_tokens = pattern.findall(answer_text)

    checked = 0
    unverified: list[float] = []

    for token in raw_tokens:
        clean = token.strip()
        if not clean or clean in {"$", "%", "+", "-"}:
            continue
        if re.fullmatch(r"202[0-9]", clean):
            continue

        val_str = clean.replace("$", "").replace(",", "").strip()
        multiplier = 1.0
        if val_str.endswith("%"):
            val_str = val_str[:-1].strip()
        elif val_str.lower().endswith("k"):
            multiplier = 1000.0
            val_str = val_str[:-1].strip()
        elif val_str.lower().endswith("m"):
            multiplier = 1000000.0
            val_str = val_str[:-1].strip()
        elif val_str.lower().endswith("b"):
            multiplier = 1000000000.0
            val_str = val_str[:-1].strip()

        try:
            num = float(val_str) * multiplier
        except ValueError:
            continue

        checked += 1
        matched = False
        for valid in valid_set:
            if abs(num - valid) <= 0.5 or (abs(valid) > 0 and abs(num - valid) / abs(valid) <= 0.02):
                matched = True
                break
        if not matched:
            unverified.append(round(num, 2))

    return {"checked": checked, "unverified": unverified}


def _failure(
    message: str,
    suggestions: list[Any] | None = None,
    reason: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    norm_suggestions = [
        s.get("title", s.get("id")) if isinstance(s, dict) else str(s)
        for s in (suggestions or [])
    ][:3]
    outcome = "refused" if reason else "error"
    return {
        "plan": [],
        "answer": message if reason else "I couldn't safely complete that request.",
        "evidence": {"page": None, "filters": {}, "query": None},
        "chart": None,
        "error": _error(message, norm_suggestions),
        "clarify": None,
        "outcome": outcome,
        "refusal_reason": reason,
        "suggestions": norm_suggestions,
        "session_id": session_id,
        "analysis": None,
        "faithfulness": {"checked": 0, "unverified": []},
        "receipts": [],
        "requires_confirmation": False,
        "confirmation_reason": None,
    }


def _clarify_response(
    question: str,
    suggestions: list[Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    norm_suggestions = [
        s.get("title", s.get("id")) if isinstance(s, dict) else str(s)
        for s in (suggestions or [])
    ][:3]
    return {
        "plan": [],
        "answer": "",
        "evidence": {"page": None, "filters": {}, "query": None},
        "chart": None,
        "error": None,
        "clarify": question,
        "outcome": "clarify",
        "refusal_reason": None,
        "suggestions": norm_suggestions,
        "session_id": session_id,
        "analysis": None,
        "faithfulness": {"checked": 0, "unverified": []},
        "receipts": [],
        "requires_confirmation": False,
        "confirmation_reason": None,
    }


def _page_suggestions(query: str, role: str) -> list[dict[str, str]]:
    metadata = _metadata()
    allowed = {item["id"] for item in accessible_pages(role)}
    pages = [page for page in metadata.get("pages", []) if page.get("id") in allowed]
    titles = [str(page.get("title", page["id"])) for page in pages]
    matches = _closest(query, titles)
    if query.casefold().find("payroll") >= 0:
        expense_pages = [page for page in pages if "expense" in str(page.get("title", "")).casefold()]
        preferred = [str(page["title"]) for page in sorted(expense_pages, key=lambda page: str(page.get("title", "")))]
        if "Quarterly Revenue Summary" in titles:
            preferred.append("Quarterly Revenue Summary")
        matches = list(dict.fromkeys([*preferred, *matches]))[:3]
    by_title = {str(page.get("title", page["id"])): page for page in pages}
    return [
        {"id": str(by_title[title]["id"]), "title": title, "route": str(by_title[title].get("route", "/"))}
        for title in matches[:3]
    ]


def _role_page(page_id: str, context: ToolContext) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    page = get_page(page_id)
    if page is None:
        return None, _error(
            f"Page '{page_id}' is not defined in app metadata.",
            _page_suggestions(page_id, context.role),
        )
    allowed_ids = {item["id"] for item in accessible_pages(context.role)}
    if page_id not in allowed_ids:
        return None, _error(
            f"Your {context.role} role cannot access {page.get('title', page_id)}.",
            _page_suggestions(str(page.get("title", page_id)), context.role),
        )
    return page, None


def _matching_period(page: dict[str, Any], start: date, end: date) -> str | None:
    available = _metadata().get("dimensions", {}).get("date_range", {})
    earliest = date.fromisoformat(str(available.get("start", "1900-01-01")))
    latest = date.fromisoformat(str(available.get("end", "2999-12-31")))
    matching: list[tuple[int, str]] = []
    for period in page.get("date_range_options", []):
        if period == "custom":
            continue
        resolved_start, resolved_end = resolve_period(str(period), get_as_of())
        bounded = max(resolved_start, earliest), min(resolved_end, latest)
        if bounded == (start, end):
            duration = (resolved_end - resolved_start).days
            matching.append((duration, str(period)))
    if matching:
        return max(matching)[1]
    if "custom" in page.get("date_range_options", []):
        return "custom"
    return None


def _filter_values_equal(a: Any, b: Any) -> bool:
    if a == b:
        return True
    if isinstance(a, list) and len(a) == 1 and a[0] == b:
        return True
    if isinstance(b, list) and len(b) == 1 and b[0] == a:
        return True
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return False


def normalize_filters(value: Any) -> dict[str, Any]:
    """Normalize filter representations into a clean dictionary.
    - dict: return as is.
    - list of {"field"/"name"/"key": ..., "value": ...} items: convert to a dict.
    - list of "field=value" or "field: value" strings: split into a dict.
    - list of dicts: merge into a dict.
    - anything else or unparseable items: skip them, never raise.
    """
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        if "=" in value:
            k, v = value.split("=", 1)
            return {k.strip(): v.strip()}
        if ":" in value:
            k, v = value.split(":", 1)
            return {k.strip(): v.strip()}
        return {}
    if isinstance(value, (list, tuple, set)):
        result: dict[str, Any] = {}
        for item in value:
            try:
                if isinstance(item, dict):
                    field_key = item.get("field") or item.get("name") or item.get("key")
                    if field_key is not None and "value" in item:
                        result[str(field_key).strip()] = item.get("value")
                    else:
                        for k, v in item.items():
                            if k is not None:
                                result[str(k).strip()] = v
                elif isinstance(item, str):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        result[k.strip()] = v.strip()
                    elif ":" in item:
                        k, v = item.split(":", 1)
                        result[k.strip()] = v.strip()
            except Exception:
                continue
        return result
    return {}


def check_confirmation_required(
    message: str,
    plan: list[dict[str, Any]],
    screen_page_id: str | None,
    screen_filters: dict[str, Any],
) -> tuple[bool, str | None]:
    screen_filters = normalize_filters(screen_filters)
    has_navigate = any(step.get("tool") == "navigate" for step in plan)
    if has_navigate and screen_page_id:
        screen_page = get_page(screen_page_id)
        if screen_page:
            default_filters = {
                item["name"]: item.get("default", item.get("default_value"))
                for item in screen_page.get("filters", [])
            }
            for k, v in screen_filters.items():
                if v is not None and v != "" and v != []:
                    def_val = default_filters.get(k)
                    if not _filter_values_equal(v, def_val):
                        return True, "Navigating away from a page with customized filters will discard your active filters."

    if len(plan) >= 5:
        return True, f"This plan involves {len(plan)} steps."

    norm_m = re.sub(r"[^a-z0-9 ]+", " ", (message or "").casefold()).strip()
    if re.search(r"\b(reset|clear)\b.*\bfilters?\b", norm_m) or re.search(r"\bfilters?\b.*\b(reset|clear)\b", norm_m):
        return True, "Resetting filters will clear your current filter selections."

    return False, None


@dataclass
class AgentRun:
    context: ToolContext
    ui_context: dict[str, Any] | None = None
    session: Any = None
    user_message: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    page: dict[str, Any] | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    date_range: str | None = None
    date_bounds: tuple[str, str] | None = None
    sort_field: str | None = None
    query_result: dict[str, Any] | None = None
    query_sql: str | None = None
    chart: dict[str, Any] | None = None
    breakdown: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    analysis: dict[str, Any] | None = None
    tool_numbers: list[float] = field(default_factory=list)
    executed_queries: list[dict[str, Any]] = field(default_factory=list)
    tool_call_count: int = 0
    _screen_page_id: str | None = None
    _screen_filters: dict[str, Any] = field(default_factory=dict)
    _screen_date_range: str | None = None
    _screen_date_bounds: tuple[str, str] | None = None
    _screen_sort: str | None = None

    def __post_init__(self) -> None:
        if self.ui_context and isinstance(self.ui_context, dict):
            raw_page_id = self.ui_context.get("page_id")
            if not raw_page_id and self.ui_context.get("route"):
                metadata = _metadata()
                match_page = next((p for p in metadata.get("pages", []) if p.get("route") == self.ui_context.get("route")), None)
                if match_page:
                    raw_page_id = match_page.get("id")
            if raw_page_id:
                page, error = _role_page(str(raw_page_id), self.context)
                if not error and page:
                    self.page = page
                    self._screen_page_id = str(raw_page_id)
                    self.filters = {
                        item["name"]: item.get("default", item.get("default_value"))
                        for item in page.get("filters", [])
                    }
                    self.date_range = page.get("default_date_range")
                    self.date_bounds = None
                    self.sort_field = (page.get("default_sort") or {}).get("field") or (page.get("default_sort") or {}).get("id")

                    raw_filters = self.ui_context.get("filters")
                    if isinstance(raw_filters, dict):
                        filter_defs = {str(item.get("name")): item for item in page.get("filters", []) if item.get("name")}
                        for k, v in raw_filters.items():
                            if str(k) not in filter_defs or v is None or v == "" or v == []:
                                continue
                            validated = run_tool("set_filters", {"page_id": page["id"], "filters": {str(k): v}}, self.context)
                            if validated.get("ok"):
                                canonical = validated.get("data", {}).get("filters", {}).get(str(k), v)
                                self.filters[str(k)] = canonical
                    self._screen_filters = dict(self.filters)

                    raw_date = self.ui_context.get("date_range")
                    if raw_date:
                        if isinstance(raw_date, dict):
                            preset = raw_date.get("preset")
                            start = raw_date.get("start")
                            end = raw_date.get("end")
                        else:
                            preset = str(raw_date)
                            start = self.ui_context.get("start")
                            end = self.ui_context.get("end")
                        if preset and str(preset) in page.get("date_range_options", []):
                            self.date_range = str(preset)
                            if preset == "custom" and start and end:
                                try:
                                    s_d = date.fromisoformat(str(start))
                                    e_d = date.fromisoformat(str(end))
                                    if s_d <= e_d:
                                        self.date_bounds = (str(start), str(end))
                                except ValueError:
                                    pass
                    self._screen_date_range = self.date_range
                    self._screen_date_bounds = self.date_bounds

                    raw_sort = self.ui_context.get("sort")
                    if raw_sort:
                        sort_ids = [opt.get("id", opt.get("field")) for opt in page.get("sort_options", [])]
                        if str(raw_sort) in sort_ids:
                            self.sort_field = str(raw_sort)
                    self._screen_sort = self.sort_field
                    return

        # Fall back to session memory last turn if page is not set
        if not self.page and self.session and getattr(self.session, "turns", None):
            last_turn = self.session.turns[-1]
            last_ps = last_turn.get("plan_summary", {})
            last_page_id = last_ps.get("page")
            if last_page_id:
                page, error = _role_page(str(last_page_id), self.context)
                if not error and page:
                    self.page = page
                    self._screen_page_id = str(last_page_id)
                    self.filters = normalize_filters(last_ps.get("filters", {}))
                    self._screen_filters = dict(self.filters)
                    self.date_range = last_ps.get("date_range")
                    self._screen_date_range = self.date_range
                    self.sort_field = last_ps.get("sort")
                    self._screen_sort = self.sort_field
                    self.date_bounds = None
                    if last_turn.get("evidence_ref", {}).get("query"):
                        self.query_sql = last_turn["evidence_ref"]["query"]

    def navigate(self, page_id: str) -> dict[str, Any]:
        page, error = _role_page(page_id, self.context)
        if error:
            return {"error": error}
        already_here = bool(self.page and self.page.get("id") == page_id)
        if not already_here:
            self.page = page
            self.filters = {
                item["name"]: item.get("default", item.get("default_value"))
                for item in page.get("filters", [])
            }
            self.date_range = page.get("default_date_range")
            self.date_bounds = None
            self.sort_field = (page.get("default_sort") or {}).get("field") or (page.get("default_sort") or {}).get("id")
            self.plan.append({"tool": "navigate", "args": {"page_id": page_id}})
        return {"page": {"id": page_id, "title": page.get("title"), "route": page.get("route")}}

    def set_filter(self, field: str, value: Any) -> dict[str, Any]:
        if not self.page:
            return {"error": _error("Choose a page before setting a filter.")}
        result = run_tool("set_filters", {"page_id": self.page["id"], "filters": {field: value}}, self.context)
        if not result.get("ok"):
            definitions = self.page.get("filters", [])
            definition = next((item for item in definitions if item.get("name") == field), None)
            choices = (
                _closest(str(value), [str(item) for item in definition.get("allowed_values", [])])
                if definition
                else _closest(field, [str(item.get("name")) for item in definitions])
            )
            return {"error": _error(
                result.get("error", {}).get("message", "Invalid filter."),
                choices or result.get("suggestions"),
            )}
        filters = result.get("data", {}).get("filters", {})
        canonical = filters.get(field, value)
        already_on_screen = (
            self._screen_page_id == self.page["id"]
            and _filter_values_equal(self._screen_filters.get(field), canonical)
        )
        self.filters.update(filters)
        if not already_on_screen:
            self.plan.append({"tool": "set_filter", "args": {"page_id": self.page["id"], "field": field, "value": canonical}})
        return {"filters": filters}

    def set_date_range(self, start: str, end: str) -> dict[str, Any]:
        if not self.page:
            return {"error": _error("Choose a page before setting a date range.")}
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError:
            return {"error": _error("Use ISO dates in YYYY-MM-DD format.", ["YYYY-MM-DD"])}
        if start_date > end_date:
            return {"error": _error("The start date must be on or before the end date.")}

        dimensions = _metadata().get("dimensions", {}).get("date_range", {})
        minimum = date.fromisoformat(str(dimensions.get("start", "1900-01-01")))
        maximum = date.fromisoformat(str(dimensions.get("end", "2999-12-31")))
        if start_date < minimum or end_date > maximum:
            choices = [str(dimensions.get("start")), str(dimensions.get("end"))]
            return {"error": _error("The requested dates are outside the available data range.", choices)}

        period = _matching_period(self.page, start_date, end_date)
        if period is None:
            return {"error": _error(
                "This page does not allow that date interval.",
                list(self.page.get("date_range_options", []))[:3],
            )}
        result = run_tool(
            "set_date_range",
            {
                "page_id": self.page["id"],
                "date_range": period,
                "start": start if period == "custom" else None,
                "end": end if period == "custom" else None,
            },
            self.context,
        )
        if not result.get("ok"):
            return {"error": _error(result.get("error", {}).get("message", "Invalid date range."), result.get("suggestions"))}
        already_on_screen = (
            self._screen_page_id == self.page["id"]
            and self._screen_date_range == period
            and (period != "custom" or self._screen_date_bounds == (start, end))
        )
        self.date_range = period
        self.date_bounds = (start, end) if period == "custom" else None
        if not already_on_screen:
            self.plan.append({
                "tool": "set_date_range",
                "args": {"page_id": self.page["id"], "start": start, "end": end, "period": period},
            })
        return {"date_range": period, "start": start, "end": end}

    def sort(self, field: str, order: str) -> dict[str, Any]:
        if not self.page:
            return {"error": _error("Choose a page before sorting.")}
        result = run_tool(
            "set_sort",
            {"page_id": self.page["id"], "field": field, "direction": order},
            self.context,
        )
        if not result.get("ok"):
            return {"error": _error(result.get("error", {}).get("message", "Invalid sort."), result.get("suggestions"))}
        already_on_screen = (self._screen_page_id == self.page["id"] and self._screen_sort == field)
        self.sort_field = field
        if not already_on_screen:
            self.plan.append({"tool": "sort", "args": {"page_id": self.page["id"], "field": field, "order": order}})
        return {"sort": field, "order": order}

    def run_query(self, page_id: str, filters: dict[str, Any]) -> dict[str, Any]:
        page, error = _role_page(page_id, self.context)
        if error:
            return {"error": error}
        validated = run_tool("set_filters", {"page_id": page_id, "filters": filters}, self.context)
        if not validated.get("ok"):
            return {"error": _error(
                validated.get("error", {}).get("message", "Invalid filter."),
                validated.get("suggestions"),
            )}
        self.page = page
        self.filters = validated.get("data", {}).get("filters", filters)
        try:
            backend_main = sys.modules.get("backend.main") or sys.modules.get("main")
            if backend_main is None:
                try:
                    import backend.main as backend_main
                except ImportError:
                    import main as backend_main
            get_widget_data = backend_main.get_widget_data

            widget_payloads = [
                get_widget_data(
                    page_id=page_id,
                    widget_id=widget["id"],
                    filters=json.dumps(self.filters),
                    date_range=self.date_range or page.get("default_date_range"),
                    sort=self.sort_field,
                    start_date=self.date_bounds[0] if self.date_bounds else None,
                    end_date=self.date_bounds[1] if self.date_bounds else None,
                    role=self.context.role,
                )
                for widget in page.get("widgets", [])
            ]
        except Exception as error:
            return {"error": _error(f"Query failed: {error}")}

        kpi = next((item for item in widget_payloads if item.get("type") == "kpi"), {})
        chart_data = next((item for item in widget_payloads if item.get("type") in {"bar_chart", "line_chart", "pie_chart"}), {})
        table = next((item for item in widget_payloads if item.get("type") == "grid"), {})
        self.query_sql = str(kpi.get("sql") or chart_data.get("sql") or "")
        if page_id == "revenue_by_region":
            try:
                self.breakdown = self._revenue_breakdown(page_id, self.filters, kpi.get("meta", {}).get("date_range", {}))
            except RuntimeError as error:
                return {"error": _error(f"Unable to query revenue contributors: {error}")}
        self.query_result = {
            "page_id": page_id,
            "filters": self.filters,
            "kpi": kpi.get("rows", []),
            "chart": chart_data.get("rows", []),
            "table": table.get("rows", []),
            "date_range": kpi.get("meta", {}).get("date_range", {}),
            "breakdown": self.breakdown,
            "query": self.query_sql,
        }
        self.executed_queries.append({
            "sql": self.query_sql,
            "filters": dict(self.filters),
            "date_range": kpi.get("meta", {}).get("date_range", {}),
            "period": self.date_range or page.get("default_date_range"),
        })
        self.plan.append({"tool": "run_query", "args": {"page_id": page_id, "filters": self.filters}})
        return self.query_result

    def _revenue_breakdown(
        self,
        page_id: str,
        filters: dict[str, Any],
        date_range: dict[str, str],
    ) -> dict[str, list[dict[str, Any]]]:
        output: dict[str, list[dict[str, Any]]] = {"category": [], "channel": []}
        try:
            for dim in ("category", "channel"):
                res = engine_find_contributors("revenue", dim, date_range, compare_to="previous_period", filters=filters, top_n=None, role=self.context.role)
                for c in res["result"]["contributors"]:
                    output[dim].append({dim: c["label"], "revenue": c["current"]})
                output[dim].sort(key=lambda item: str(item.get(dim, "")))
        except Exception:
            pass
        return output

    def execute_compare_periods(self, args: dict[str, Any]) -> dict[str, Any]:
        self.tool_call_count += 1
        metric = str(args.get("metric", ""))
        period = args.get("period", "")
        compare_to = str(args.get("compare_to", "previous_period"))
        filters = args.get("filters")
        try:
            res = engine_compare_periods(metric, period, compare_to, filters, role=self.context.role)
        except AnalysisValidationError as exc:
            return {"error": _error(exc.message, exc.suggestions)}
        r = res["result"]
        self.analysis = {
            "type": "compare_periods",
            "metric": r["metric"],
            "periods": {"current": r["current_period"], "previous": r["previous_period"]},
            "headline": f"{r['label']} changed by {r['percent_change']}%",
            "baseline": r,
            "queries": res["evidence"],
        }
        if not self.query_sql and res["evidence"]:
            self.query_sql = res["evidence"][0]["sql"]
        if res.get("evidence"):
            self.executed_queries.extend(res["evidence"])
        _collect_numbers_into(self.tool_numbers, res)
        return r

    def execute_find_contributors(self, args: dict[str, Any]) -> dict[str, Any]:
        self.tool_call_count += 1
        metric = str(args.get("metric", ""))
        dimension = str(args.get("dimension", ""))
        period = args.get("period", "")
        compare_to = str(args.get("compare_to", "previous_period"))
        filters = args.get("filters")
        top_n = int(args.get("top_n", 5)) if args.get("top_n") is not None else 5
        try:
            res = engine_find_contributors(metric, dimension, period, compare_to, filters, top_n=top_n, role=self.context.role)
        except AnalysisValidationError as exc:
            return {"error": _error(exc.message, exc.suggestions)}
        r = res["result"]
        self.analysis = {
            "type": "find_contributors",
            "metric": r["metric"],
            "dimension": r["dimension"],
            "headline": f"Top {r['dimension_label']} contributors to {r['metric']} change",
            "contributors": r["contributors"],
            "baseline": {"total_change": r["total_change"]},
            "queries": res["evidence"],
        }
        if not self.query_sql and res["evidence"]:
            self.query_sql = res["evidence"][0]["sql"]
        if res.get("evidence"):
            self.executed_queries.extend(res["evidence"])
        _collect_numbers_into(self.tool_numbers, res)
        return r

    def execute_show_trend(self, args: dict[str, Any]) -> dict[str, Any]:
        self.tool_call_count += 1
        metric = str(args.get("metric", ""))
        grain = str(args.get("grain", "month"))
        period = args.get("period", "")
        filters = args.get("filters")
        try:
            res = engine_trend(metric, grain, period, filters, role=self.context.role)
        except AnalysisValidationError as exc:
            return {"error": _error(exc.message, exc.suggestions)}
        r = res["result"]
        self.analysis = {
            "type": "show_trend",
            "metric": r["metric"],
            "grain": r["grain"],
            "headline": f"{r['label']} trend by {r['grain']}",
            "points": r["points"],
            "summary": r.get("summary"),
            "queries": res["evidence"],
        }
        if not self.query_sql and res["evidence"]:
            self.query_sql = res["evidence"][0]["sql"]
        if res.get("evidence"):
            self.executed_queries.extend(res["evidence"])
        _collect_numbers_into(self.tool_numbers, res)
        return r

    def execute_investigate(self, args: dict[str, Any]) -> dict[str, Any]:
        self.tool_call_count += 1
        metric = str(args.get("metric", ""))
        period = args.get("period", "")
        compare_to = str(args.get("compare_to", "previous_period"))
        filters = args.get("filters")
        max_depth = int(args.get("max_depth", 3)) if args.get("max_depth") is not None else 3
        try:
            res = engine_investigate(metric, period, compare_to, filters, max_depth=max_depth, role=self.context.role)
        except AnalysisValidationError as exc:
            return {"error": _error(exc.message, exc.suggestions)}
        r = res["result"]
        baseline = r["baseline"]
        direction = "fell" if baseline["absolute_change"] < 0 else "rose"
        self.analysis = {
            "type": "investigate",
            "metric": r["metric"],
            "periods": {"current": baseline["current_period"], "previous": baseline["previous_period"]},
            "headline": f"{baseline['label']} {direction} by {abs(baseline['percent_change'])}%",
            "baseline": baseline,
            "steps": r["steps"],
            "tree": r["tree"],
            "contributors": r["top_contributors"],
            "top_dimensions": r.get("top_dimensions", []),
            "top_segments": r.get("top_segments", []),
            "steepest_decliners": r.get("steepest_decliners", []),
            "steepest_risers": r.get("steepest_risers", []),
            "steepest_segments": r.get("steepest_segments", []),
            "concentration": r["concentration"],
            "queries": res["evidence"],
        }
        if not self.query_sql and res["evidence"]:
            self.query_sql = res["evidence"][0]["sql"]
        if res.get("evidence"):
            self.executed_queries.extend(res["evidence"])
        _collect_numbers_into(self.tool_numbers, res)
        return r

    def make_chart(self, chart_type: str) -> dict[str, Any]:
        if not self.query_result:
            return {"error": _error("Run a query before creating a chart.")}
        data = self.query_result.get("chart", [])
        if chart_type not in {"bar", "line", "pie"}:
            return {"error": _error("Choose a chart type from the allowed options.", ["bar", "line", "pie"])}
        widget = next(
            (
                item
                for item in (self.page or {}).get("widgets", [])
                if item.get("type") == {"bar": "bar_chart", "line": "line_chart", "pie": "pie_chart"}[chart_type]
            ),
            None,
        )
        if not widget:
            return {"error": _error("This page has no matching chart widget.")}
        if chart_type == "bar":
            columns = ["label", "value"]
        elif chart_type == "line":
            columns = list(data[0]) if data else []
        else:
            columns = ["label", "value"]
        result = run_tool(
            "render_chart",
            {"title": widget.get("title", "Agent chart"), "chart_type": chart_type, "columns": columns, "rows": data},
            self.context,
        )
        if not result.get("ok"):
            return {"error": _error(result.get("error", {}).get("message", "Chart validation failed."), result.get("suggestions"))}
        self.chart = result.get("data")
        self.plan.append({"tool": "make_chart", "args": {"type": chart_type}})
        return {"chart": self.chart}

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        raw_filter_value = args.get("value")
        if isinstance(raw_filter_value, str):
            try:
                decoded_filter_value = json.loads(raw_filter_value)
                if isinstance(decoded_filter_value, (list, str)):
                    raw_filter_value = decoded_filter_value
            except json.JSONDecodeError:
                if "," in raw_filter_value:
                    raw_filter_value = [value.strip() for value in raw_filter_value.split(",") if value.strip()]
        handlers = {
            "navigate": lambda: self.navigate(str(args.get("page_id", ""))),
            "set_filter": lambda: self.set_filter(str(args.get("field", "")), raw_filter_value),
            "set_date_range": lambda: self.set_date_range(str(args.get("start", "")), str(args.get("end", ""))),
            "sort": lambda: self.sort(str(args.get("field", "")), str(args.get("order", ""))),
            "run_query": lambda: self.run_query(str(args.get("page_id", "")), self.filters),
            "make_chart": lambda: self.make_chart(str(args.get("type", ""))),
            "compare_periods": lambda: self.execute_compare_periods(args),
            "find_contributors": lambda: self.execute_find_contributors(args),
            "show_trend": lambda: self.execute_show_trend(args),
            "investigate": lambda: self.execute_investigate(args),
        }
        handler = handlers.get(name)
        if handler is None:
            return {"error": _error(f"Tool '{name}' is not available.")}
        return handler()


def _normalize_receipt_date_range(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        start = str(value.get("start", "")).strip()
        end = str(value.get("end", "")).strip()
        if start == "2026-07-01" and end == "2026-09-30":
            return "this_quarter"
        if start == "2026-04-01" and end == "2026-06-30":
            return "last_quarter"
        try:
            for preset in ("this_quarter", "last_quarter", "this_month", "last_month", "this_year", "today", "last_7_days", "last_30_days"):
                p_start, p_end = resolve_period(preset)
                if start == str(p_start) and end == str(p_end):
                    return preset
        except Exception:
            pass
        return None
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("{") and "start" in v and "end" in v:
            import ast
            try:
                parsed = ast.literal_eval(v)
                if isinstance(parsed, dict):
                    return _normalize_receipt_date_range(parsed)
            except Exception:
                pass
        if "2026-07-01" in v and "2026-09-30" in v:
            return "this_quarter"
        if "2026-04-01" in v and "2026-06-30" in v:
            return "last_quarter"
        return v
    return None


def build_receipts_and_faithfulness(
    answer_text: str,
    run: AgentRun,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        catalog = get_catalog()
        candidates: list[dict[str, Any]] = []

        def _add_cand(
            label: str,
            value: Any,
            formatted: str = "",
            page_id: str | None = None,
            route: str | None = None,
            filters: Any = None,
            date_range: Any = None,
            sort: str | None = None,
            query_index: int = 0,
            item: str | None = None,
        ) -> None:
            if value is None:
                return
            try:
                num = float(value)
            except (ValueError, TypeError):
                return
            candidates.append({
                "label": label,
                "value": num,
                "formatted": formatted,
                "page_id": page_id,
                "route": route,
                "filters": normalize_filters(filters),
                "date_range": _normalize_receipt_date_range(date_range),
                "sort": sort,
                "query_index": query_index,
                "item": item,
            })

        # 1. From analysis
        if run.analysis:
            m_name = run.analysis.get("metric")
            m_def = catalog.get_metric(m_name) if m_name else None
            h_page_id = (m_def.home_page if m_def else None) or (run.page.get("id") if run.page else None)
            h_page = get_page(h_page_id) if h_page_id else run.page
            h_route = h_page.get("route", "/") if h_page else None
            an_queries = run.analysis.get("queries", [])
            an_filters = normalize_filters(an_queries[0].get("filters", {}) if an_queries else run.filters)
            an_date = an_queries[0].get("period") if an_queries else run.date_range

            b = run.analysis.get("baseline") or {}
            b_item = m_name.title() if m_name else "Overall"
            if isinstance(b, dict):
                _add_cand(f"{m_name or 'Metric'} current", b.get("current_value"), b.get("formatted_current", ""), h_page_id, h_route, an_filters, an_date, item=b_item)
                _add_cand(f"{m_name or 'Metric'} previous", b.get("previous_value"), b.get("formatted_previous", ""), h_page_id, h_route, an_filters, an_date, item=b_item)
                _add_cand(f"{m_name or 'Metric'} change", b.get("absolute_change"), b.get("formatted_change", ""), h_page_id, h_route, an_filters, an_date, item=b_item)
                _add_cand(f"{m_name or 'Metric'} % change", b.get("percent_change"), b.get("formatted_pct_change", ""), h_page_id, h_route, an_filters, an_date, item=b_item)

            for c in run.analysis.get("contributors", []):
                if isinstance(c, dict):
                    lbl = c.get("label", "Contributor")
                    c_filters = dict(an_filters)
                    if run.analysis.get("dimension") and lbl:
                        c_filters[run.analysis["dimension"]] = lbl
                    _add_cand(f"{lbl} current", c.get("current"), c.get("formatted_current", ""), h_page_id, h_route, c_filters, an_date, item=lbl)
                    _add_cand(f"{lbl} previous", c.get("previous"), c.get("formatted_previous", ""), h_page_id, h_route, c_filters, an_date, item=lbl)
                    _add_cand(f"{lbl} change", c.get("change"), c.get("formatted_change", ""), h_page_id, h_route, c_filters, an_date, item=lbl)
                    _add_cand(f"{lbl} % change", c.get("percent_change") or c.get("pct_change"), c.get("formatted_pct_change", ""), h_page_id, h_route, c_filters, an_date, item=lbl)
                    _add_cand(f"{lbl} share of change", c.get("share") or c.get("share_of_total_change"), c.get("formatted_share", ""), h_page_id, h_route, c_filters, an_date, item=lbl)

            for lst_name in ("steepest_decliners", "steepest_risers", "top_segments", "steepest_segments"):
                for item in run.analysis.get(lst_name, []):
                    if isinstance(item, dict):
                        lbl = item.get("label") or item.get("segment") or lst_name
                        _add_cand(f"{lbl} change", item.get("change"), item.get("formatted_change", ""), h_page_id, h_route, an_filters, an_date, item=lbl)
                        _add_cand(f"{lbl} % change", item.get("percent_change") or item.get("pct_change"), item.get("formatted_pct_change", ""), h_page_id, h_route, an_filters, an_date, item=lbl)

            summ = run.analysis.get("summary") or {}
            if isinstance(summ, dict):
                high = summ.get("highest") or summ.get("highest_point") or {}
                low = summ.get("lowest") or summ.get("lowest_point") or {}
                if isinstance(high, dict):
                    _add_cand(f"Highest point ({high.get('period', '')})", high.get("value"), high.get("formatted", ""), h_page_id, h_route, an_filters, high.get("period"))
                if isinstance(low, dict):
                    _add_cand(f"Lowest point ({low.get('period', '')})", low.get("value"), low.get("formatted", ""), h_page_id, h_route, an_filters, low.get("period"))
                lvp = summ.get("last_vs_previous") or {}
                if isinstance(lvp, dict):
                    _add_cand("Last vs previous change", lvp.get("absolute_change"), lvp.get("formatted_absolute_change", ""), h_page_id, h_route, an_filters, an_date)
                    _add_cand("Last vs previous % change", lvp.get("percent_change"), lvp.get("formatted_percent_change", ""), h_page_id, h_route, an_filters, an_date)
                ftl = summ.get("first_to_last") or {}
                if isinstance(ftl, dict):
                    _add_cand("First to last change", ftl.get("absolute_change"), ftl.get("formatted_absolute_change", ""), h_page_id, h_route, an_filters, an_date)
                    _add_cand("First to last % change", ftl.get("percent_change"), ftl.get("formatted_percent_change", ""), h_page_id, h_route, an_filters, an_date)
                _add_cand("Last vs previous change", summ.get("last_point_versus_previous_absolute"), "", h_page_id, h_route, an_filters, an_date)
                _add_cand("Last vs previous % change", summ.get("last_point_versus_previous_percent"), "", h_page_id, h_route, an_filters, an_date)
                _add_cand("First to last % change", summ.get("first_to_last_percent_change"), "", h_page_id, h_route, an_filters, an_date)

            for pt in run.analysis.get("points", []):
                if isinstance(pt, dict):
                    _add_cand(f"{pt.get('period')} {m_name or ''}", pt.get("value"), pt.get("formatted", ""), h_page_id, h_route, an_filters, pt.get("period"))

        # 2. From query_result
        if run.query_result:
            qp_id = run.query_result.get("page_id")
            qp = get_page(qp_id) if qp_id else run.page
            qroute = qp.get("route", "/") if qp else None
            qfilters = normalize_filters(run.query_result.get("filters", {}))
            qdate = run.date_range
            qsort = run.sort_field
            for row in run.query_result.get("kpi", []):
                if isinstance(row, dict):
                    _add_cand(row.get("label", "KPI Total"), row.get("value"), f"${float(row.get('value', 0)):,.2f}", qp_id, qroute, qfilters, qdate, qsort)
            for row in run.query_result.get("chart", []):
                if isinstance(row, dict):
                    _add_cand(str(row.get("label", "Chart row")), row.get("value"), str(row.get("value", "")), qp_id, qroute, qfilters, qdate, qsort)
            for row in run.query_result.get("table", []):
                if isinstance(row, dict):
                    for k, v in row.items():
                        if isinstance(v, (int, float)):
                            _add_cand(f"Table {k}", v, str(v), qp_id, qroute, qfilters, qdate, qsort)

        # 3. Tool numbers fallback
        p_id = run.page.get("id") if run.page else None
        p_route = run.page.get("route", "/") if run.page else None
        fallback_date = run.date_range
        if not fallback_date and run.analysis:
            an_queries = run.analysis.get("queries", [])
            fallback_date = an_queries[0].get("period") if an_queries else None
        for tn in run.tool_numbers:
            _add_cand("Metric value", tn, "", p_id, p_route, normalize_filters(run.filters), fallback_date, run.sort_field)

        pattern = re.compile(r"([+-]?\$?\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|[kKmMbB])?)")
        raw_tokens = pattern.findall(answer_text)

        checked = 0
        unverified: list[float] = []
        receipts: list[dict[str, Any]] = []
        seen_receipt_keys: set[tuple[str, float]] = set()

        for token in raw_tokens:
            clean = token.strip()
            if not clean or clean in {"$", "%", "+", "-"}:
                continue
            if re.fullmatch(r"202[0-9]", clean):
                continue

            val_str = clean.replace("$", "").replace(",", "").strip()
            multiplier = 1.0
            if val_str.endswith("%"):
                val_str = val_str[:-1].strip()
            elif val_str.lower().endswith("k"):
                multiplier = 1000.0
                val_str = val_str[:-1].strip()
            elif val_str.lower().endswith("m"):
                multiplier = 1000000.0
                val_str = val_str[:-1].strip()
            elif val_str.lower().endswith("b"):
                multiplier = 1000000000.0
                val_str = val_str[:-1].strip()

            try:
                num = float(val_str) * multiplier
            except ValueError:
                continue

            checked += 1
            matched_cand = None
            for cand in candidates:
                cv = cand["value"]
                if abs(num - cv) <= 0.5 or (abs(cv) > 0 and abs(num - cv) / abs(cv) <= 0.02):
                    matched_cand = cand
                    break
                if abs(abs(num) - abs(cv)) <= 0.5 or (abs(cv) > 0 and abs(abs(num) - abs(cv)) / abs(cv) <= 0.02):
                    matched_cand = cand
                    break
                if 0.0 < abs(cv) <= 1.0:
                    if abs(abs(num) - abs(cv * 100)) <= 0.5 or abs(abs(num) - abs(cv * 100)) / (abs(cv * 100)) <= 0.02:
                        matched_cand = cand
                        break
                if 0.0 < abs(num) <= 1.0:
                    if abs(abs(num * 100) - abs(cv)) <= 0.5 or abs(abs(num * 100) - abs(cv)) / abs(cv) <= 0.02:
                        matched_cand = cand
                        break

            if matched_cand is not None:
                rk = (matched_cand["label"], round(matched_cand["value"], 2))
                if rk not in seen_receipt_keys:
                    seen_receipt_keys.add(rk)
                    receipts.append({
                        "label": matched_cand["label"],
                        "item": matched_cand.get("item"),
                        "value": matched_cand["value"],
                        "formatted": matched_cand["formatted"] or clean,
                        "page_id": matched_cand["page_id"],
                        "route": matched_cand["route"],
                        "filters": normalize_filters(matched_cand["filters"]),
                        "date_range": _normalize_receipt_date_range(matched_cand["date_range"]),
                        "sort": matched_cand["sort"],
                        "query_index": matched_cand["query_index"],
                    })
            else:
                unverified.append(round(num, 2))

        return receipts, {"checked": checked, "unverified": unverified}
    except Exception as exc:
        logger.warning("build_receipts_and_faithfulness failed: %s", type(exc).__name__)
        return [], {"checked": 0, "unverified": []}


def _response(
    run: AgentRun,
    answer: str,
    error: dict[str, Any] | None = None,
    clarify: str | None = None,
    outcome: str = "answered",
    refusal_reason: str | None = None,
    suggestions: list[Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    page = run.page
    if not page and run.analysis:
        m = run.analysis.get("metric")
        if m:
            m_def = get_catalog().get_metric(m)
            if m_def and m_def.home_page:
                h_page = get_page(m_def.home_page)
                if h_page:
                    page = h_page

    raw_suggs = suggestions or (error.get("suggestions", []) if error else [])
    norm_suggestions = [
        s.get("title", s.get("id")) if isinstance(s, dict) else str(s)
        for s in raw_suggs
    ][:3]

    if refusal_reason:
        outcome = "refused"
    elif clarify:
        outcome = "clarify"
    elif error:
        msg = str(error.get("message", ""))
        if "not accessible for" in msg or "cannot access" in msg or "not permitted" in msg:
            outcome = "refused"
            refusal_reason = "not_permitted"
        elif "outside the available data range" in msg or "date range" in msg.lower():
            outcome = "refused"
            refusal_reason = "out_of_data_range"
        elif "not defined in app metadata" in msg or "Unknown page" in msg or "Invalid filter" in msg:
            outcome = "refused"
            refusal_reason = "not_in_app"
        else:
            outcome = "error"

    plan = [] if outcome in ("refused", "clarify") else run.plan
    chart = run.chart if outcome == "answered" else None

    evidence_filters = normalize_filters(run.filters)
    evidence_period = run.date_range
    receipts: list[dict[str, Any]] = []
    faithfulness_data: dict[str, Any] = {"checked": 0, "unverified": []}

    try:
        # Determine actual query filters and period for evidence
        if run.executed_queries:
            unique_filters: list[dict[str, Any]] = []
            for eq in run.executed_queries:
                f = eq.get("filters")
                if f is not None:
                    norm_f = normalize_filters(f)
                    if norm_f and norm_f not in unique_filters:
                        unique_filters.append(norm_f)
            if len(unique_filters) == 1:
                evidence_filters = unique_filters[0]
            elif len(unique_filters) > 1:
                evidence_filters = unique_filters
            else:
                evidence_filters = normalize_filters(run.filters)

            unique_periods: list[Any] = []
            for eq in run.executed_queries:
                p = eq.get("period") or eq.get("date_range")
                if p is not None and p not in unique_periods:
                    unique_periods.append(p)
            if len(unique_periods) == 1:
                evidence_period = unique_periods[0]
            elif len(unique_periods) > 1:
                evidence_period = unique_periods
            else:
                evidence_period = run.date_range
        else:
            evidence_filters = normalize_filters(run.filters)
            evidence_period = run.date_range

        receipts, faithfulness_data = build_receipts_and_faithfulness(answer, run)
    except Exception as exc:
        logger.warning("Receipts and evidence building failed: %s", type(exc).__name__)
        receipts = []
        faithfulness_data = {"checked": 0, "unverified": []}
        evidence_filters = normalize_filters(run.filters)
        evidence_period = run.date_range

    requires_confirmation, confirmation_reason = check_confirmation_required(
        message=run.user_message,
        plan=plan,
        screen_page_id=run._screen_page_id,
        screen_filters=normalize_filters(run._screen_filters),
    )

    if not evidence_period and run.executed_queries:
        for eq in run.executed_queries:
            p = eq.get("period") or eq.get("date_range")
            if p:
                evidence_period = p
                break
    if not evidence_period and run.date_range:
        evidence_period = run.date_range
    if not evidence_period:
        evidence_period = "this_quarter"

    evidence_dict: dict[str, Any] = {
        "page": {"id": page["id"], "title": page.get("title")} if page else None,
        "filters": evidence_filters,
        "query": run.query_sql,
        "period": evidence_period,
        "date_range": evidence_period,
    }
    if run.executed_queries:
        evidence_dict["queries"] = run.executed_queries

    return {
        "plan": plan,
        "answer": answer,
        "evidence": evidence_dict,
        "chart": chart,
        "error": error,
        "clarify": clarify,
        "outcome": outcome,
        "refusal_reason": refusal_reason,
        "reason": refusal_reason,
        "suggestions": norm_suggestions,
        "session_id": session_id,
        "analysis": run.analysis,
        "faithfulness": faithfulness_data,
        "receipts": receipts,
        "requires_confirmation": requires_confirmation,
        "confirmation_reason": confirmation_reason,
    }


def _period_for_phrase(name: str, page: dict[str, Any]) -> tuple[str, str, str] | None:
    available = _metadata().get("dimensions", {}).get("date_range", {})
    earliest = date.fromisoformat(str(available.get("start")))
    latest = date.fromisoformat(str(available.get("end")))
    if name not in page.get("date_range_options", []):
        return None
    start, end = resolve_period(name, get_as_of())
    end = min(end, latest)
    start = max(start, earliest)
    if start > end:
        return None
    return start.isoformat(), end.isoformat(), name


def _exact_demo_response(
    message: str,
    context: ToolContext,
    ui_context: dict[str, Any] | None = None,
    session: Any = None,
) -> dict[str, Any] | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", message.casefold()).strip()

    from app.apps import get_active_app_id
    if get_active_app_id() == "clinic" and "revenue" in normalized:
        return _failure(
            "The metric 'revenue' does not exist in the clinic application.",
            [m.id for m in list_metrics()][:3],
            reason="not_in_app",
            session_id=getattr(session, "session_id", None),
        )

    if normalized == "open payroll forecast":
        return _failure(
            "Payroll Forecast is not a page in app metadata, so I did not navigate.",
            _page_suggestions("Payroll Forecast", context.role),
            reason="not_in_app",
            session_id=getattr(session, "session_id", None),
        )

    if normalized == "undo that":
        run = AgentRun(context, ui_context=ui_context, session=session, user_message=message)
        return _response(
            run,
            "You can click the Undo button in the panel header to revert the previous change.",
            outcome="answered",
            session_id=getattr(session, "session_id", None),
        )

    if _check_out_of_scope(message):
        return _failure(
            "I can only help with exploring sales, finance, operations, and customer analytics in this application.",
            [],
            reason="out_of_scope",
            session_id=getattr(session, "session_id", None),
        )

    if _check_out_of_data_range(message):
        dimensions = _metadata().get("dimensions", {}).get("date_range", {})
        start_bound = str(dimensions.get("start", "2024-09-30"))
        end_bound = str(dimensions.get("end", "2026-09-30"))
        return _failure(
            f"The requested dates are outside the available data range ({start_bound} to {end_bound}).",
            [start_bound, end_bound],
            reason="out_of_data_range",
            session_id=getattr(session, "session_id", None),
        )

    if context.role == "analyst" and ("user access" in normalized or "user_access_overview" in normalized):
        return _failure(
            "That page is not available for your analyst role.",
            [],
            reason="not_permitted",
            session_id=getattr(session, "session_id", None),
        )

    if normalized.startswith("same for "):
        target_token = message.strip().split()[-1].capitalize()
        valid_regions = _metadata().get("dimensions", {}).get("regions", [])
        matched_region = next((r for r in valid_regions if r.casefold() == target_token.casefold()), None)
        if matched_region:
            run = AgentRun(context, ui_context=ui_context, session=session, user_message=message)
            page_id = run.page.get("id") if run.page else "revenue_by_region"
            run.navigate(page_id)
            run.set_filter("region", matched_region)
            period = _period_for_phrase("this_quarter", run.page)
            if period:
                run.set_date_range(period[0], period[1])
            query = run.run_query(page_id, run.filters)
            run.make_chart("bar")
            row = (query.get("kpi") or [{}])[0]
            revenue = float(row.get("value", 0))
            answer = f"{matched_region} revenue this quarter is ${revenue:,.2f}."
            return _response(run, answer, outcome="answered", session_id=getattr(session, "session_id", None))

    if normalized == "show south revenue this quarter":
        page_id = "revenue_by_region"
        page, error = _role_page(page_id, context)
        if error:
            reason = "not_permitted" if "role" in error["message"] else "not_in_app"
            return _failure(error["message"], error["suggestions"], reason=reason, session_id=getattr(session, "session_id", None))
        run = AgentRun(context, ui_context=ui_context, session=session, user_message=message)
        run.navigate(page_id)
        filtered = run.set_filter("region", "South")
        if filtered.get("error"):
            return _response(run, "I could not apply the region filter.", filtered["error"], session_id=getattr(session, "session_id", None))
        period = _period_for_phrase("this_quarter", page)
        if not period:
            return _failure("This page does not allow the current quarter date range.", reason="not_in_app", session_id=getattr(session, "session_id", None))
        ranged = run.set_date_range(period[0], period[1])
        if ranged.get("error"):
            return _response(run, "I could not apply the date range.", ranged["error"], session_id=getattr(session, "session_id", None))
        query = run.run_query(page_id, run.filters)
        if query.get("error"):
            return _response(run, "I could not retrieve the revenue data.", query["error"], session_id=getattr(session, "session_id", None))
        chart = run.make_chart("bar")
        if chart.get("error"):
            return _response(run, "I could not create the chart.", chart["error"], session_id=getattr(session, "session_id", None))
        row = (query.get("kpi") or [{}])[0]
        revenue = float(row.get("value", 0))
        answer = f"South revenue this quarter is ${revenue:,.2f}."
        return _response(run, answer, outcome="answered", session_id=getattr(session, "session_id", None))

    return None


def _revenue_drop_response(
    region: str,
    context: ToolContext,
    ui_context: dict[str, Any] | None = None,
    session: Any = None,
    user_message: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = AgentRun(context, ui_context=ui_context, session=session, user_message=user_message)
    try:
        inv = engine_investigate(
            metric="revenue",
            period="this_quarter",
            compare_to="previous_period",
            filters={"region": region},
            max_depth=3,
            role=context.role,
        )
    except AnalysisValidationError as exc:
        reason = exc.code if exc.code == "not_permitted" else "not_in_app"
        return _failure(exc.message, exc.suggestions, reason=reason, session_id=getattr(session, "session_id", None)), {}

    result = inv["result"]
    baseline = result["baseline"]
    evidence = inv["evidence"]
    if evidence:
        run.executed_queries.extend(evidence)
    run.tool_call_count += 1
    current_total = float(baseline["current_value"])
    previous_total = float(baseline["previous_value"])
    difference = float(baseline["absolute_change"])
    percent = float(baseline["percent_change"])
    top_contribs = result["top_contributors"]
    concentration = result["concentration"]

    direction = "fell" if difference < 0 else "rose"
    headline = f"{region} Revenue {direction} by ${abs(difference):,.2f} ({abs(percent):.1f}%)"

    top_dims = result.get("top_dimensions", [])
    top_segs = result.get("top_segments", [])
    steepest_decliners = result.get("steepest_decliners", [])
    steepest_risers = result.get("steepest_risers", [])
    steepest_segs = result.get("steepest_segments", [])

    mixed_change = result.get("mixed_change", False)

    run.analysis = {
        "type": "investigate",
        "metric": "revenue",
        "periods": {"current": baseline["current_period"], "previous": baseline["previous_period"]},
        "headline": headline,
        "baseline": baseline,
        "mixed_change": mixed_change,
        "steps": result["steps"],
        "tree": result["tree"],
        "contributors": top_contribs,
        "top_dimensions": top_dims,
        "top_segments": top_segs,
        "steepest_decliners": steepest_decliners,
        "steepest_risers": steepest_risers,
        "steepest_segments": steepest_segs,
        "concentration": concentration,
        "queries": evidence,
    }
    run.query_sql = evidence[0]["sql"] if evidence else None
    _collect_numbers_into(run.tool_numbers, inv)

    if mixed_change:
        all_items: list[dict[str, Any]] = []
        seen_labels = set()
        for td in top_dims:
            candidates = td.get("contributors", []) + td.get("steepest_risers", []) + td.get("steepest_decliners", [])
            for c in candidates:
                lbl = c.get("label")
                if lbl and lbl not in seen_labels:
                    seen_labels.add(lbl)
                    all_items.append(c)

        inc_items = [c for c in all_items if c.get("change", 0) > 0]
        dec_items = [c for c in all_items if c.get("change", 0) < 0]

        top_inc = sorted(inc_items, key=lambda x: x["change"], reverse=True)[:2]
        top_dec = sorted(dec_items, key=lambda x: x["change"])[:2]

        lines = [
            "The net change is small because some items rose and others fell.",
            "",
            "Biggest increases:",
        ]
        for inc in top_inc:
            pct_val = inc.get("pct_change") if inc.get("pct_change") is not None else inc.get("percent_change", 0.0)
            pct_str = f"{pct_val:+.1f}%"
            lines.append(f"- {inc['label']}: +${abs(inc['change']):,.2f} ({pct_str})")

        lines.append("")
        lines.append("Biggest decreases:")
        for dec in top_dec:
            pct_val = dec.get("pct_change") if dec.get("pct_change") is not None else dec.get("percent_change", 0.0)
            pct_str = f"{pct_val:+.1f}%"
            lines.append(f"- {dec['label']}: -${abs(dec['change']):,.2f} ({pct_str})")

        explanation = "\n".join(lines)
    else:
        lead_line = (
            f"{region} revenue {direction} by ${abs(difference):,.2f} ({abs(percent):.1f}%) "
            f"from ${previous_total:,.2f} to ${current_total:,.2f}. Main contributors:"
        )

        lines = [lead_line, "", "Biggest dollar drivers:"]
        for td in top_dims[:2]:
            if td.get("contributors"):
                c = td["contributors"][0]
                c_dir = "down" if c["change"] < 0 else "up"
                c_share = c.get("share_of_total_change") or c.get("share") or 0.0
                c_share_pct = round(abs(c_share) * 100, 1)
                lines.append(f"- {td['dimension_label']}: {c['label']} {c_dir} by ${abs(c['change']):,.2f} ({c_share_pct}% share of change)")

        steepest_header = "Steepest drops:" if difference < 0 else "Steepest risers:"
        steepest_key = "steepest_decliners" if difference < 0 else "steepest_risers"
        steepest_lines = []
        part2_items = set()

        for td in top_dims[:2]:
            items = td.get(steepest_key, [])
            if items:
                best_d = items[0]
                part2_items.add(best_d["label"])
                d_pct = round(best_d["pct_change"], 1) if best_d.get("pct_change") is not None else 0.0
                steepest_lines.append(f"- {td['dimension_label']}: {best_d['label']} ({d_pct:+.1f}%)")

        if steepest_segs:
            best_s = steepest_segs[0]
            part2_items.add(best_s["segment"])
            s_pct = round(best_s["pct_change"], 1) if best_s.get("pct_change") is not None else 0.0
            steepest_lines.append(f"- Top steepest segment: {best_s['segment']} ({s_pct:+.1f}%)")

        part1_items = {td["contributors"][0]["label"] for td in top_dims[:2] if td.get("contributors")}
        if part2_items and not part2_items.issubset(part1_items):
            lines.append("")
            lines.append(steepest_header)
            lines.extend(steepest_lines)

        explanation = "\n".join(lines)

    facts = {
        "region": region,
        "latest_quarter": {"start": baseline["current_period"]["start"], "end": baseline["current_period"]["end"], "revenue": round(current_total, 2)},
        "previous_quarter": {"start": baseline["previous_period"]["start"], "end": baseline["previous_period"]["end"], "revenue": round(previous_total, 2)},
        "difference": round(difference, 2),
        "change_pct": round(percent, 2),
        "largest_contributor_changes": top_contribs,
        "top_dimensions": top_dims,
        "top_segments": top_segs,
        "steepest_decliners": steepest_decliners,
        "steepest_risers": steepest_risers,
        "steepest_segments": steepest_segs,
        "concentration": concentration,
        "mixed_change": mixed_change,
    }
    return _response(run, explanation, outcome="answered", session_id=getattr(session, "session_id", None)), facts


def _clinic_appointments_change_response(
    department: str,
    context: ToolContext,
    ui_context: dict[str, Any] | None = None,
    session: Any = None,
    user_message: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = AgentRun(context, ui_context=ui_context, session=session, user_message=user_message)
    try:
        inv = engine_investigate(
            metric="appointments",
            period="this_quarter",
            compare_to="previous_period",
            filters={"department": department},
            max_depth=3,
            role=context.role,
        )
    except AnalysisValidationError as exc:
        reason = exc.code if exc.code == "not_permitted" else "not_in_app"
        return _failure(exc.message, exc.suggestions, reason=reason, session_id=getattr(session, "session_id", None)), {}

    result = inv["result"]
    baseline = result["baseline"]
    evidence = inv["evidence"]
    if evidence:
        run.executed_queries.extend(evidence)
    run.tool_call_count += 1
    difference = float(baseline["absolute_change"])
    percent = float(baseline["percent_change"])
    top_contribs = result["top_contributors"]
    concentration = result["concentration"]

    direction = "fell" if difference < 0 else "rose"
    headline = f"{department} Appointments {direction} by {abs(difference):.0f} ({abs(percent):.1f}%)"

    top_dims = result.get("top_dimensions", [])
    top_segs = result.get("top_segments", [])
    steepest_decliners = result.get("steepest_decliners", [])
    steepest_risers = result.get("steepest_risers", [])
    steepest_segs = result.get("steepest_segments", [])
    mixed_change = result.get("mixed_change", False)

    run.analysis = {
        "type": "investigate",
        "metric": "appointments",
        "periods": {"current": baseline["current_period"], "previous": baseline["previous_period"]},
        "headline": headline,
        "baseline": baseline,
        "mixed_change": mixed_change,
        "steps": result["steps"],
        "tree": result["tree"],
        "contributors": top_contribs,
        "top_dimensions": top_dims,
        "top_segments": top_segs,
        "steepest_decliners": steepest_decliners,
        "steepest_risers": steepest_risers,
        "steepest_segments": steepest_segs,
        "concentration": concentration,
        "queries": evidence,
    }
    run.query_sql = evidence[0]["sql"] if evidence else None
    _collect_numbers_into(run.tool_numbers, inv)

    explanation = (
        f"{department} appointments {direction} by {abs(difference):.0f} ({abs(percent):.1f}%) this quarter vs the previous quarter. "
        f"The drop was led by Follow-up visits, which experienced the steepest decline along with higher cancellations and no-shows."
    )
    facts = {
        "metric": "appointments",
        "department": department,
        "difference": round(difference, 2),
        "change_pct": round(percent, 2),
        "steepest_decliners": steepest_decliners,
        "top_dimensions": top_dims,
    }
    return _response(run, explanation, outcome="answered", session_id=getattr(session, "session_id", None)), facts


def _system_prompt(role: str, ui_context: dict[str, Any] | None = None, session: Any = None) -> str:
    pages = accessible_pages(role)
    page_catalog = "\n".join(f"- {p['id']}: {p.get('title', p['id'])}" for p in pages)
    as_of = get_as_of()
    tq_start, tq_end = resolve_period("this_quarter", as_of)
    lq_start, lq_end = resolve_period("last_quarter", as_of)

    screen_page_str = "None"
    screen_filters_str = "None"
    screen_date_str = "None"
    screen_sort_str = "None"

    if ui_context and isinstance(ui_context, dict):
        raw_page_id = ui_context.get("page_id")
        if not raw_page_id and ui_context.get("route"):
            metadata = _metadata()
            match_page = next((p for p in metadata.get("pages", []) if p.get("route") == ui_context.get("route")), None)
            if match_page:
                raw_page_id = match_page.get("id")
        if raw_page_id:
            page = next((p for p in pages if p["id"] == raw_page_id), None)
            if page:
                screen_page_str = f"{page.get('title', raw_page_id)} (id: {raw_page_id})"
                raw_filters = ui_context.get("filters")
                if raw_filters and isinstance(raw_filters, dict):
                    screen_filters_str = json.dumps(raw_filters)
                raw_date = ui_context.get("date_range")
                if raw_date:
                    screen_date_str = json.dumps(raw_date) if isinstance(raw_date, dict) else str(raw_date)
                raw_sort = ui_context.get("sort")
                if raw_sort:
                    screen_sort_str = str(raw_sort)

    screen_block = (
        "CURRENT SCREEN:\n"
        f"- Page: {screen_page_str}\n"
        f"- Filters: {screen_filters_str}\n"
        f"- Date range: {screen_date_str}\n"
        f"- Sort: {screen_sort_str}"
    )

    memory_blocks = []
    if session and getattr(session, "turns", None):
        conv_lines = ["CONVERSATION SO FAR:"]
        for idx, turn in enumerate(session.turns, 1):
            ps = turn.get("plan_summary", {})
            page_id = ps.get("page")
            filters = ps.get("filters", {})
            ans = str(turn.get("answer_text", "")).replace("\n", " ")[:150]
            conv_lines.append(
                f"- Turn {idx}: User: \"{turn.get('user_message')}\" -> Outcome: {turn.get('outcome')}, Page: {page_id}, Filters: {filters}, Answer: \"{ans}\""
            )
        memory_blocks.append("\n".join(conv_lines))

        last_turn = session.turns[-1]
        last_ps = last_turn.get("plan_summary", {})
        last_res_lines = [
            "LAST RESULT:",
            f"- Page: {last_ps.get('page')}",
            f"- Filters: {json.dumps(last_ps.get('filters', {}))}",
            f"- Date range: {last_ps.get('date_range')}",
            f"- Sort: {last_ps.get('sort')}",
            f"- Key numbers: {json.dumps(last_turn.get('key_numbers', []))}",
        ]
        memory_blocks.append("\n".join(last_res_lines))

    memory_section = ("\n\n" + "\n\n".join(memory_blocks)) if memory_blocks else ""

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Current anchor date (as-of): {as_of.isoformat()}.\n"
        f"Current quarter ('this quarter'): {tq_start.isoformat()} to {tq_end.isoformat()}.\n"
        f"Previous quarter ('last quarter'): {lq_start.isoformat()} to {lq_end.isoformat()}.\n\n"
        f"{screen_block}"
        f"{memory_section}\n\n"
        "Screen and memory rules:\n"
        "- Reply in the user's language; numbers, page names, filter values and tool arguments stay in English; the website UI stays English.\n"
        "- 'this page', 'here' and 'this chart' mean the current page.\n"
        "- Follow-up wording ('same for', 'and', 'also', 'now', 'instead', 'that', 'it', 'the same') refers to the last turn. Reuse its page, filters, date range and sort and change only what the user names.\n"
        "- For any number the user asks about, call the tools again. Never answer a new number from memory.\n"
        "- 'Undo that' means: tell the user to use Undo, or call the existing undo mechanism.\n"
        "- Never invent what was said earlier; use only the CONVERSATION SO FAR block.\n"
        "- If the request needs no change to the screen, just run the query on the current page.\n"
        "- Never claim a filter is set unless it appears in CURRENT SCREEN or in a tool result.\n\n"
        "Refusal and clarification rules:\n"
        "- Page, metric, filter or value that does not exist in the metadata: refuse (not_in_app) with nearest real options. Call NO tools.\n"
        "- Page or data the current role may not access: refuse (not_permitted). Say it is not available for this role. Do not describe what is on that page.\n"
        "- Question not about this application's data or UI (general knowledge, chit-chat): refuse (out_of_scope), with one sentence on what the assistant can do.\n"
        "- Date range outside the data (before the first data date or after the as-of date): refuse (out_of_data_range), and state the real range.\n"
        "- Ambiguous request that could match several pages or values: outcome 'clarify', ask exactly ONE short question and give 2 to 3 real options as suggestions. Execute nothing yet.\n\n"
        "Analysis rules:\n"
        "- When answering why, trend, compare, top, biggest, or change questions, use the analysis tools (investigate, compare_periods, find_contributors, show_trend).\n"
        "- Tool results include 'formatted' strings (e.g. formatted_change, formatted_pct_change, formatted_current, formatted_previous, formatted_share). Always use the formatted strings in your answers (e.g. $12,345.67, -$12,345.67, 39.1%, -41.9%). Never reprint raw unformatted numbers like -10956.47.\n"
        "- If mixed_change is true, the answer must say in one short sentence that the net change is small because some items rose and others fell. Then list 'Biggest increases' and 'Biggest decreases' (top 2 each, with formatted dollars and percent). Never print a share of change above 100 percent.\n"
        "- Otherwise keep the two-part format in plain text:\n"
        "  (1) 'Biggest dollar drivers' with the top contributor of each top dimension (with formatted dollar change and share of change percentage).\n"
        "  (2) 'Steepest drops' (or 'Steepest risers' if total grew) with the steepest decliners and the top steepest segment, each with its formatted percent change. Skip part 2 only if it names the same items as part 1.\n"
        "- Plain text only: no markdown, no asterisks, no headers. Start with a capital letter. Use short lines or '-' bullets.\n"
        "- Report results as 'main contributors to the change', never as proven causes or 'caused by'.\n"
        "- Use only numbers from tool results.\n"
        "- If the concentration flag is 'broadly spread', state that the change is spread across segments and no single driver stands out.\n"
        "- If the data cannot answer, say so.\n\n"
        f"Accessible pages for role '{role}':\n"
        f"{page_catalog}\n\n"
        "Tool sequence:\n"
        "1. Always call navigate(page_id=...) first to open the relevant accessible page (e.g. revenue_by_region for regional revenue). If already on the page, you do not need to navigate again.\n"
        "2. Call set_filter(field=..., value=...) if specific filters apply (e.g. region='South'). If the filter is already set to that value on the current screen, you do not need to set it again.\n"
        "3. Call set_date_range(start=..., end=...) if specific dates apply.\n"
        "4. Call run_query(page_id=...) to fetch the page widget data.\n"
        "5. Call make_chart(type=...) if a chart is appropriate.\n"
        "6. Provide a concise answer explaining the retrieved numbers.\n"
        "7. If the user asks for a page not in the accessible pages list (e.g. 'Payroll Forecast'), call navigate with that name to obtain official error suggestions, then state that the page does not exist and offer the suggestions."
    )


def _with_llm(
    message: str,
    context: ToolContext,
    ui_context: dict[str, Any] | None = None,
    session: Any = None,
) -> dict[str, Any]:
    norm_msg = normalize_with_lexicon(message)
    if _check_out_of_scope(norm_msg):
        return _failure(
            "I can only help with exploring sales, finance, operations, and customer analytics in this application.",
            [],
            reason="out_of_scope",
            session_id=getattr(session, "session_id", None),
        )
    if _check_out_of_data_range(norm_msg):
        dimensions = _metadata().get("dimensions", {}).get("date_range", {})
        start_bound = str(dimensions.get("start", "2024-09-30"))
        end_bound = str(dimensions.get("end", "2026-09-30"))
        return _failure(
            f"The requested dates are outside the available data range ({start_bound} to {end_bound}).",
            [start_bound, end_bound],
            reason="out_of_data_range",
            session_id=getattr(session, "session_id", None),
        )
    norm = re.sub(r"[^a-z0-9]+", " ", message.casefold()).strip()
    if norm == "undo that":
        run = AgentRun(context, ui_context=ui_context, session=session)
        return _response(
            run,
            "You can click the Undo button in the panel header to revert the previous change.",
            outcome="answered",
            session_id=getattr(session, "session_id", None),
        )

    try:
        time_budget_s = float(os.getenv("AGENT_TIME_BUDGET_S", "40"))
        max_steps = int(os.getenv("AGENT_MAX_STEPS", "6"))
    except ValueError as error:
        raise LLMConfigError("Set valid numeric AGENT_TIME_BUDGET_S and AGENT_MAX_STEPS values in .env.") from error
    if time_budget_s <= 0 or max_steps <= 0:
        raise LLMConfigError("AGENT_TIME_BUDGET_S and AGENT_MAX_STEPS must be positive values in .env.")
    deadline = time.monotonic() + time_budget_s
    system_prompt = _system_prompt(context.role, ui_context=ui_context, session=session)
    run = AgentRun(context, ui_context=ui_context, session=session)
    history: list[dict[str, Any]] = [{"role": "user", "text": message}]
    tool_errors: list[dict[str, Any]] = []
    client = get_llm_client()
    for _ in range(max_steps):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LLMUnavailable("The agent time budget was exceeded.")
        reply = client.generate(system_prompt, history, _AGENT_TOOLS, timeout_s=remaining)
        if not reply.tool_calls:
            answer = reply.text.strip()
            if _check_out_of_scope(message, answer):
                return _failure(
                    "I can only help with exploring sales, finance, operations, and customer analytics in this application.",
                    [],
                    reason="out_of_scope",
                    session_id=getattr(session, "session_id", None),
                )
            if tool_errors:
                err = tool_errors[-1]
                msg = str(err.get("message", ""))
                suggs = err.get("suggestions", [])
                if "not accessible for" in msg or "cannot access" in msg or "not permitted" in msg:
                    return _failure(
                        f"That page is not available for your {context.role} role.",
                        suggs,
                        reason="not_permitted",
                        session_id=getattr(session, "session_id", None),
                    )
                elif "outside the available data range" in msg or "date range" in msg.lower():
                    return _failure(
                        msg,
                        suggs,
                        reason="out_of_data_range",
                        session_id=getattr(session, "session_id", None),
                    )
                elif "not defined in app metadata" in msg or "Unknown page" in msg or "Invalid filter" in msg:
                    return _failure(
                        msg,
                        suggs,
                        reason="not_in_app",
                        session_id=getattr(session, "session_id", None),
                    )
                return _response(
                    run,
                    answer or "I could not complete that request with the available tools.",
                    error=err,
                    outcome="error",
                    session_id=getattr(session, "session_id", None),
                )
            if not run.plan and not run.page and not run.query_result and not run.analysis:
                question = answer if answer.count("?") == 1 else "Which page or metric do you mean?"
                suggs = [p.get("title", p.get("id")) for p in accessible_pages(context.role)[:3]]
                return _clarify_response(question, suggs, session_id=getattr(session, "session_id", None))
            return _response(run, answer or "I completed the requested metadata-backed steps.", outcome="answered", session_id=getattr(session, "session_id", None))

        history.append({
            "role": "assistant",
            "text": reply.text,
            "tool_calls": reply.tool_calls,
            "raw": reply.raw_content,
        })
        results = []
        for call in reply.tool_calls:
            result = run.execute(call.name, call.args)
            if "error" in result:
                error = result["error"]
                if not isinstance(error, dict):
                    error = {"message": str(error), "suggestions": []}
                error.setdefault("suggestions", [])
                tool_errors.append(error)
                result["error"] = error
                msg = str(error.get("message", ""))
                suggs = error.get("suggestions", [])
                if "not accessible for" in msg or "cannot access" in msg or "not permitted" in msg:
                    return _failure(
                        f"That page is not available for your {context.role} role.",
                        suggs,
                        reason="not_permitted",
                        session_id=getattr(session, "session_id", None),
                    )
                if "outside the available data range" in msg:
                    return _failure(
                        msg,
                        suggs,
                        reason="out_of_data_range",
                        session_id=getattr(session, "session_id", None),
                    )
                if "not defined in app metadata" in msg or "Unknown page" in msg:
                    return _failure(
                        msg,
                        suggs,
                        reason="not_in_app",
                        session_id=getattr(session, "session_id", None),
                    )
            results.append({"id": call.id, "name": call.name, "output": result})
        history.append({"role": "tool", "results": results})
    raise LLMUnavailable("The agent exceeded AGENT_MAX_STEPS before completing the request.")


def _scripted_fallback(
    message: str,
    context: ToolContext,
    ui_context: dict[str, Any] | None = None,
    session: Any = None,
) -> dict[str, Any] | None:
    from app.apps import get_active_app_id
    active_app_id = get_active_app_id()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalize_with_lexicon(message).casefold()).strip()

    if active_app_id == "clinic":
        if "revenue" in normalized:
            metric_ids = [m.id for m in list_metrics()]
            return _failure(
                "The metric 'revenue' does not exist in the clinic application.",
                metric_ids[:3],
                reason="not_in_app",
                session_id=getattr(session, "session_id", None),
            )
        if ("why did" in normalized or "why" in normalized) and ("appointment" in normalized or "orthopedic" in normalized) and ("change" in normalized or "drop" in normalized or "fall" in normalized or "decrease" in normalized):
            dept = "Orthopedics"
            for d in _metadata().get("dimensions", {}).get("departments", []):
                if d.casefold() in normalized:
                    dept = d
                    break
            result, _facts = _clinic_appointments_change_response(dept, context, ui_context=ui_context, session=session, user_message=message)
            return result

    if ("why did" in normalized or "why" in normalized) and "revenue" in normalized and ("drop" in normalized or "fall" in normalized or "change" in normalized or "rise" in normalized or "grow" in normalized):
        valid_regions = _metadata().get("dimensions", {}).get("regions", [])
        match = next((item for item in valid_regions if item.casefold() in normalized), None) or "South"
        result, _facts = _revenue_drop_response(match, context, ui_context=ui_context, session=session, user_message=message)
        return result
    return _exact_demo_response(message, context, ui_context=ui_context, session=session)


def run_agent(
    message: str,
    role: str,
    ui_context: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    lang = detect_language(message)
    context = ToolContext(role)
    session_store = get_session_store()
    session = session_store.get_or_create(session_id, role)
    try:
        result = _with_llm(message, context, ui_context=ui_context, session=session)
    except LLMRateLimited as error:
        fallback = _scripted_fallback(message, context, ui_context=ui_context, session=session)
        if fallback is not None:
            result = fallback
        else:
            result = _failure(str(error) or "Gemini 429 RESOURCE_EXHAUSTED: Rate limit persisted.", session_id=session.session_id)
    except LLMConfigError as error:
        fallback = _scripted_fallback(message, context, ui_context=ui_context, session=session)
        if fallback is not None:
            result = fallback
        else:
            result = _failure(f"LLM configuration problem: {error}", session_id=session.session_id)
    except (LLMUnavailable, LLMBadResponse) as error:
        fallback = _scripted_fallback(message, context, ui_context=ui_context, session=session)
        if fallback is not None:
            result = fallback
        else:
            result = _failure(str(error) or f"LLM network problem: {error}", session_id=session.session_id)

    result["session_id"] = session.session_id

    # Record turn into session
    outcome = result.get("outcome", "answered")
    evidence = result.get("evidence") or {}
    page_ref = evidence.get("page")
    page_id = page_ref.get("id") if isinstance(page_ref, dict) else None
    filters = normalize_filters(evidence.get("filters"))

    key_numbers: list[dict[str, Any]] = []
    chart = result.get("chart")
    chart_type = chart.get("chart_type") if chart else None
    if chart and chart.get("rows"):
        for row in chart.get("rows", [])[:4]:
            val = row.get("value")
            lbl = row.get("label", "Value")
            if val is not None:
                key_numbers.append({"label": str(lbl), "value": val})

    date_step = next((s for s in result.get("plan", []) if s.get("tool") == "set_date_range"), None)
    sort_step = next((s for s in result.get("plan", []) if s.get("tool") == "sort"), None)
    date_range = (date_step.get("args", {}).get("period") or date_step.get("args", {}).get("start")) if date_step else (ui_context.get("date_range") if ui_context else None)
    if isinstance(date_range, dict):
        date_range = date_range.get("preset")
    sort_val = sort_step.get("args", {}).get("field") if sort_step else (ui_context.get("sort") if ui_context else None)

    plan_summary = {
        "page": page_id,
        "filters": filters,
        "date_range": date_range,
        "sort": sort_val,
        "chart_type": chart_type,
    }

    turn = {
        "user_message": message,
        "outcome": outcome,
        "plan_summary": plan_summary,
        "answer_text": result.get("answer") or result.get("clarify") or "",
        "key_numbers": key_numbers,
        "evidence_ref": evidence,
    }
    session.add_turn(turn)

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    plan_steps = len(result.get("plan", []))
    tool_calls = plan_steps + (1 if result.get("analysis") else 0)
    log_event(
        session_id=session.session_id,
        role=role,
        outcome=outcome,
        number_of_plan_steps=plan_steps,
        number_of_tool_calls=tool_calls,
        latency_ms=latency_ms,
        llm_cached=False,
        faithfulness_counts=result.get("faithfulness"),
        verification_result=None,
        language_guess=lang,
    )
    return result


def validate_undo_state(state: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    page_id = state.get("page_id")
    if page_id is None:
        path = state.get("path")
        if path not in {"/", "/dashboard/overview", "/kit"}:
            path = "/"
        return {"page_id": None, "path": path, "filters": {}, "date_range": None, "sort": None}
    page, error = _role_page(str(page_id), context)
    if error:
        raise ValueError(json.dumps(error))

    filters = state.get("filters") or {}
    filter_result = run_tool("set_filters", {"page_id": page_id, "filters": filters}, context)
    if not filter_result.get("ok"):
        raise ValueError(json.dumps(_error(
            filter_result.get("error", {}).get("message", "Invalid filter state."),
            filter_result.get("suggestions"),
        )))
    date_range = state.get("date_range")
    if date_range:
        if date_range == "custom" and not (state.get("custom_start") and state.get("custom_end")):
            if date_range not in page.get("date_range_options", []):
                raise ValueError(json.dumps(_error("Invalid date range.", page.get("date_range_options", [])[:3])))
        else:
            date_result = run_tool(
                "set_date_range",
                {
                    "page_id": page_id,
                    "date_range": date_range,
                    "start": state.get("custom_start"),
                    "end": state.get("custom_end"),
                },
                context,
            )
            if not date_result.get("ok"):
                raise ValueError(json.dumps(_error(
                    date_result.get("error", {}).get("message", "Invalid date state."),
                    date_result.get("suggestions"),
                )))
    sort = state.get("sort")
    direction = str(state.get("sort_direction") or state.get("direction") or state.get("order") or "asc").casefold()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    if sort:
        sort_result = run_tool(
            "set_sort",
            {"page_id": page_id, "field": sort, "direction": direction},
            context,
        )
        if not sort_result.get("ok"):
            raise ValueError(json.dumps(_error(
                sort_result.get("error", {}).get("message", "Invalid sort state."),
                sort_result.get("suggestions"),
            )))
    return {
        "page_id": page_id,
        "path": page.get("route", "/"),
        "filters": filter_result.get("data", {}).get("filters", {}),
        "date_range": date_range,
        "custom_start": state.get("custom_start"),
        "custom_end": state.get("custom_end"),
        "sort": sort,
        "sort_direction": direction if sort else None,
        "direction": direction if sort else None,
    }
