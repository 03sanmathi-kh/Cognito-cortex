import json
from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import duckdb
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.graph import accessible_pages, get_graph, get_page_neighborhood, is_valid_filter
from app.retrieval import build_index, get_roles, search as search_metadata
from app.tools import ToolContext, get_tool_registry, region_scope_for_role, run_tool
from app.agent import run_agent, validate_undo_state
from app.events import get_events_summary, record_verification_event
from app.llm import get_llm_client
from app.timeutil import comparison_period, get_as_of, resolve_period

ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = ROOT / "data" / "app_metadata.json"
VIEWS_MANIFEST_PATH = ROOT / "data" / "views_manifest.json"
DB_PATH = ROOT / "data" / "business.duckdb"
DEMO_ROLES = {"admin", "regional_manager", "analyst"}

from app.apps import (
    get_active_app_id,
    get_active_metadata_path,
    get_active_metadata,
    get_active_db_path,
    get_active_views_path,
    list_apps,
    select_app,
)


def get_allowed_roles() -> set[str]:
    roles = set(DEMO_ROLES)
    try:
        meta = get_active_metadata()
        for r in meta.get("roles") or []:
            if isinstance(r, dict):
                roles.add(str(r.get("id")).casefold())
            elif isinstance(r, str):
                roles.add(r.casefold())
    except Exception:
        pass
    return roles


def get_demo_role(
    x_demo_role: str | None = Header(default=None, alias="X-Demo-Role"),
    role: str | None = Query(default=None),
) -> str:
    raw = x_demo_role or role or "admin"
    role_val = raw.strip().casefold()
    allowed = get_allowed_roles()
    if role_val not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown demo role '{x_demo_role or role}'.")
    return role_val


class ToolRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    role: str | None = None
    ui_context: dict[str, Any] = Field(default_factory=dict)


class UiDateRange(BaseModel):
    preset: str | None = None
    start: str | None = None
    end: str | None = None


class UiContextModel(BaseModel):
    page_id: str | None = None
    route: str | None = None
    filters: dict[str, Any] | None = None
    date_range: UiDateRange | dict[str, Any] | str | None = None
    sort: str | None = None
    role: str | None = None


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    role: str
    ui_context: UiContextModel | dict[str, Any] | None = None
    session_id: str | None = None


class UndoRequest(BaseModel):
    role: str
    state: dict[str, Any]


class VerifyRequest(BaseModel):
    session_id: str | None = None
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(_: FastAPI):
    metadata = get_active_metadata()
    build_index(metadata)
    get_graph()
    yield


app = FastAPI(
    title="Cognito Cortex API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(get_demo_role)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _normalise_metadata_value(value: Any) -> list[str] | str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def _fetch_filtered_rows(
    view_name: str,
    date_column: str,
    start: date,
    end: date,
    filters: dict[str, Any],
    filter_definitions: dict[str, dict[str, Any]],
    sort_config: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str, list[Any]]:
    conditions: list[str] = [f'widget_view."{date_column}" >= ?']
    params: list[Any] = [start.isoformat()]
    conditions.append(f'widget_view."{date_column}" <= ?')
    params.append(end.isoformat())

    with duckdb.connect(str(get_active_db_path()), read_only=True) as connection:
        columns = connection.execute(f'SELECT * FROM "{view_name}" LIMIT 0').description
        column_names = [column[0] for column in columns]

        for name, value in filters.items():
            if name not in column_names:
                continue
            if value is None or value == "" or value == []:
                continue
            definition = filter_definitions[name]
            if definition.get("type") == "multi_select":
                values = value if isinstance(value, list) else [value]
            else:
                values = [value]

            if not values:
                continue
            placeholders = ", ".join(["?"] * len(values))
            existing_values = {
                row[0]
                for row in connection.execute(
                    f'SELECT DISTINCT widget_view."{name}" FROM '
                    f'(SELECT * FROM "{view_name}") AS widget_view '
                    f'WHERE widget_view."{name}" IN ({placeholders})',
                    values,
                ).fetchall()
            }
            matching_values = [value for value in values if value in existing_values]
            if not matching_values:
                continue
            if len(matching_values) == 1:
                conditions.append(f'widget_view."{name}" = ?')
                params.append(matching_values[0])
            else:
                value_placeholders = ", ".join(["?"] * len(matching_values))
                conditions.append(f'widget_view."{name}" IN ({value_placeholders})')
                params.extend(matching_values)

        query = (
            f'SELECT * FROM (SELECT * FROM "{view_name}") AS widget_view '
            f'WHERE {' AND '.join(conditions)}'
        )
        if sort_config and sort_config.get("field") in column_names:
            direction = "DESC" if sort_config.get("order") == "desc" else "ASC"
            query += f' ORDER BY widget_view."{sort_config["field"]}" {direction}'
        rows = connection.execute(query, params).fetchall()

    if not rows:
        return [], query, params

    payload = [dict(zip(column_names, row)) for row in rows]
    return payload, query, params


def _is_numeric_like(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _coerce_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _resolve_metric(measures: list[str], columns: list[str], rows: list[dict[str, Any]]) -> str:
    aliases = {
        "revenue": ("revenue", "gross_revenue", "sales"),
        "sales": ("revenue", "gross_revenue", "sales"),
        "units": ("units_sold", "quantity", "units"),
        "quantity": ("quantity", "units_sold", "units"),
        "orders": ("order_count", "orders"),
        "customers": ("customer_count", "customer_id"),
        "cost": ("cost", "total_cost"),
        "expense": ("expense", "amount", "cost"),
        "profit": ("profit", "gross_profit", "revenue"),
    }

    for measure in measures:
        if measure in columns:
            return measure
        normalised = measure.lower()
        for prefix in ("sum_", "total_", "avg_", "average_", "top_"):
            normalised = normalised.removeprefix(prefix)
        if normalised in columns:
            return normalised
        for token, candidates in aliases.items():
            if token in normalised:
                candidate = next((name for name in candidates if name in columns), None)
                if candidate:
                    return candidate

    for column in columns:
        if column in {"quantity", "units_sold", "revenue", "cost", "amount", "expense", "order_count"}:
            if rows and any(_is_numeric_like(row.get(column)) for row in rows):
                return column
    return "value"


def _aggregate_rows(
    rows: list[dict[str, Any]],
    metric_name: str,
    dimensions: list[str],
    default_sort: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    dimensions = [name for name in dimensions if name in rows[0] and name != metric_name]
    if not dimensions:
        return [{metric_name: sum(_coerce_number(item.get(metric_name, 0)) for item in rows)}]

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key_parts = []
        for dimension in dimensions:
            key_parts.append(str(row.get(dimension, "")))
        group_key = "|".join(key_parts)
        if group_key not in grouped:
            grouped[group_key] = {dimension: row.get(dimension) for dimension in dimensions}
            grouped[group_key][metric_name] = 0.0
        grouped[group_key][metric_name] += _coerce_number(row.get(metric_name, 0))

    aggregated = list(grouped.values())
    if default_sort:
        field_name = default_sort.get("field")
        sort_field = field_name if field_name in aggregated[0] else metric_name
        aggregated.sort(key=lambda record: _coerce_number(record.get(sort_field, 0)), reverse=default_sort.get("order") == "desc")
    return aggregated


def _build_widget_payload(
    page: dict[str, Any],
    widget: dict[str, Any],
    view_entry: dict[str, Any],
    filters: dict[str, Any],
    date_range: str,
    sort_config: dict[str, Any] | None,
    custom_bounds: tuple[date, date] | None = None,
) -> dict[str, Any]:
    view_name = view_entry["data_view"]
    date_column = view_entry.get("date_column", "order_date")
    table_columns = list(view_entry.get("columns", []))
    current_start, current_end = custom_bounds or resolve_period(date_range, get_as_of())
    previous_start, previous_end = comparison_period(date_range, current_start, current_end)

    filter_definitions = {definition["name"]: definition for definition in page.get("filters", [])}

    def fetch_for_range(start: date, end: date):
        filtered_rows, query, params = _fetch_filtered_rows(
            view_name=view_name,
            date_column=date_column,
            start=start,
            end=end,
            filters=filters,
            filter_definitions=filter_definitions,
            sort_config=sort_config,
        )
        return filtered_rows, query, params

    current_rows, current_sql, current_params = fetch_for_range(current_start, current_end)
    if widget.get("type") == "kpi":
        previous_rows, previous_sql, previous_params = fetch_for_range(previous_start, previous_end)
    else:
        previous_rows, previous_sql, previous_params = [], "", []

    if not current_rows and not previous_rows:
        return {
            "widget_id": widget["id"],
            "type": widget.get("type", "kpi"),
            "title": widget.get("title", "Widget"),
            "sql": current_sql,
            "params": current_params,
            "rows": [],
            "meta": {"date_range": {"start": current_start.isoformat(), "end": current_end.isoformat()}, "filters": filters, "sort": sort_config},
            "row_count": 0,
        }

    if widget.get("type") == "kpi":
        target_measures = widget.get("measures") or []
        metric_name = _resolve_metric(target_measures, table_columns, current_rows)
        current_total = sum(_coerce_number(row.get(metric_name, 0)) for row in current_rows)
        previous_total = sum(_coerce_number(row.get(metric_name, 0)) for row in previous_rows)

        if "online_pct" in target_measures:
            metric_name = "online_pct"

            def channel_share(rows: list[dict[str, Any]]) -> float:
                total = sum(_coerce_number(row.get("revenue")) for row in rows)
                online = sum(_coerce_number(row.get("revenue")) for row in rows if row.get("channel") == "Online")
                return online / total * 100 if total else 0.0

            current_total = channel_share(current_rows)
            previous_total = channel_share(previous_rows)
        elif "primary_share_pct" in target_measures:
            metric_name = "primary_share_pct"

            def primary_channel_share(rows: list[dict[str, Any]]) -> float:
                totals: dict[str, float] = defaultdict(float)
                for row in rows:
                    totals[str(row.get("channel", ""))] += _coerce_number(row.get("revenue"))
                total = sum(totals.values())
                return max(totals.values(), default=0.0) / total * 100 if total else 0.0

            current_total = primary_channel_share(current_rows)
            previous_total = primary_channel_share(previous_rows)
        elif target_measures and any(name.startswith("top_") for name in target_measures):
            group_column = next((name for name in (widget.get("columns") or []) + ["product_name", "customer_id"] if current_rows and name in current_rows[0]), None)
            if group_column:
                grouped_totals: dict[str, float] = defaultdict(float)
                for row in current_rows:
                    grouped_totals[str(row.get(group_column))] += _coerce_number(row.get(metric_name, 0))
                current_total = max(grouped_totals.values(), default=0.0)

                prev_grouped: dict[str, float] = defaultdict(float)
                for row in previous_rows:
                    prev_grouped[str(row.get(group_column))] += _coerce_number(row.get(metric_name, 0))
                previous_total = max(prev_grouped.values(), default=0.0)
        elif "velocity_growth_pct" in target_measures or (widget.get("title") and "velocity rate" in str(widget.get("title", "")).lower()):
            metric_name = "velocity_growth_pct"
            base_col = "quantity" if "quantity" in table_columns else ("revenue" if "revenue" in table_columns else metric_name)
            curr_base = sum(_coerce_number(row.get(base_col, 0)) for row in current_rows)
            prev_base = sum(_coerce_number(row.get(base_col, 0)) for row in previous_rows)
            if prev_base <= 0.01:
                current_total = 0.0
                previous_total = 0.0
                change_pct = 0.0
            else:
                rate = ((curr_base - prev_base) / prev_base) * 100
                current_total = rate
                previous_total = 0.0
                change_pct = rate

        if abs(previous_total) < 0.01:
            change_pct = 0.0
        else:
            calc_pct = ((current_total - previous_total) / previous_total) * 100
            change_pct = None if abs(calc_pct) > 10000 else calc_pct

        payload = {
            "widget_id": widget["id"],
            "type": "kpi",
            "title": widget.get("title", "Widget"),
            "sql": current_sql,
            "params": current_params,
            "rows": [{
                "metric": metric_name,
                "value": round(current_total, 2),
                "previous_value": round(previous_total, 2),
                "change_pct": round(change_pct, 2),
            }],
            "meta": {
                "date_range": {"start": current_start.isoformat(), "end": current_end.isoformat()},
                "compare_range": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
                "filters": filters,
                "sort": sort_config,
            },
            "row_count": 1,
        }
        return payload

    if page.get("id") == "revenue_by_region" and widget.get("id") == "grid_region_summary":
        conditions = ["CAST(o.order_date AS DATE) >= ?", "CAST(o.order_date AS DATE) <= ?"]
        params: list[Any] = [current_start.isoformat(), current_end.isoformat()]
        for name in ("region", "channel"):
            value = filters.get(name)
            if value in (None, "", []):
                continue
            values = value if isinstance(value, list) else [value]
            placeholders = ", ".join("?" for _ in values)
            conditions.append(f'o."{name}" IN ({placeholders})')
            params.extend(values)
        query = (
            "SELECT o.region, COUNT(DISTINCT o.order_id) AS order_count, "
            "ROUND(SUM(i.revenue), 2) AS gross_revenue, "
            "ROUND(SUM(i.revenue) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS avg_order_value "
            "FROM orders o JOIN order_items i ON i.order_id = o.order_id "
            f"WHERE {' AND '.join(conditions)} GROUP BY o.region"
        )
        if sort_config and sort_config.get("field") in {"region", "order_count", "gross_revenue", "avg_order_value"}:
            direction = "DESC" if sort_config.get("order") == "desc" else "ASC"
            query += f' ORDER BY "{sort_config["field"]}" {direction}'
        with duckdb.connect(str(get_active_db_path()), read_only=True) as connection:
            rows = [
                {
                    "region": row[0],
                    "order_count": int(row[1]),
                    "gross_revenue": float(row[2] or 0),
                    "avg_order_value": float(row[3] or 0),
                }
                for row in connection.execute(query, params).fetchall()
            ]
        return {
            "widget_id": widget["id"],
            "type": "grid",
            "title": widget.get("title", "Widget"),
            "sql": query,
            "params": params,
            "rows": rows,
            "meta": {"date_range": {"start": current_start.isoformat(), "end": current_end.isoformat()}, "filters": filters, "sort": sort_config},
            "row_count": len(rows),
        }

    metric_name = _resolve_metric(widget.get("measures") or [], table_columns, current_rows)

    if widget.get("type") in {"bar_chart", "pie_chart", "line_chart"}:
        dimension_name = None
        if "columns" in widget and widget["columns"]:
            dimension_name = next((column for column in widget["columns"] if column in table_columns and column != date_column), None)
        if not dimension_name:
            dimension_name = next((column for column in table_columns if column not in {date_column, metric_name}), None)

        if widget.get("type") == "line_chart":
            bucket_map: dict[str, dict[str, float]] = defaultdict(dict)
            for row in current_rows:
                bucket = str(row.get(date_column, "unknown"))[:7] if row.get(date_column) else "unknown"
                label = bucket
                dimension_value = row.get(dimension_name, "All") if dimension_name else "All"
                bucket_map[label][str(dimension_value)] = bucket_map[label].get(str(dimension_value), 0.0) + _coerce_number(row.get(metric_name, 0))

            transformed = []
            for bucket in sorted(bucket_map.keys()):
                item: dict[str, Any] = {"period": bucket}
                for dimension_value, total in bucket_map[bucket].items():
                    item[str(dimension_value)] = round(total, 2)
                transformed.append(item)
            if sort_config and sort_config.get("field") in {date_column, "period"} and sort_config.get("order") == "desc":
                transformed.reverse()

            return {
                "widget_id": widget["id"],
                "type": "line_chart",
                "title": widget.get("title", "Widget"),
                "sql": current_sql,
                "params": current_params,
                "rows": transformed,
                "meta": {"date_range": {"start": current_start.isoformat(), "end": current_end.isoformat()}, "metric": metric_name, "dimension": dimension_name},
                "row_count": len(transformed),
            }

        group_map: dict[str, float] = defaultdict(float)
        for row in current_rows:
            label = row.get(dimension_name, "All") if dimension_name else "All"
            group_map[str(label)] += _coerce_number(row.get(metric_name, 0))

        if sort_config and sort_config.get("field") == dimension_name:
            sorted_groups = sorted(group_map.items(), key=lambda item: item[0], reverse=sort_config.get("order") == "desc")
        else:
            sorted_groups = sorted(group_map.items(), key=lambda item: item[1], reverse=sort_config is None or sort_config.get("order") == "desc")
        transformed = [{"label": name, "value": round(total, 2)} for name, total in sorted_groups][:12]
        return {
            "widget_id": widget["id"],
            "type": widget.get("type", "bar_chart"),
            "title": widget.get("title", "Widget"),
            "sql": current_sql,
            "params": current_params,
            "rows": transformed,
            "meta": {"date_range": {"start": current_start.isoformat(), "end": current_end.isoformat()}, "metric": metric_name, "dimension": dimension_name},
            "row_count": len(transformed),
        }

    widget_dimensions = widget.get("columns") or []
    if not widget_dimensions:
        widget_dimensions = [
            column for column in table_columns
            if column not in {date_column, metric_name, "status", "customer_id"}
        ][:1]
    aggregated_rows = _aggregate_rows(current_rows, metric_name, widget_dimensions, sort_config)
    transformed = []
    for row in aggregated_rows:
        item = {}
        for key, value in row.items():
            if key == metric_name:
                item["value"] = round(_coerce_number(value), 2)
            elif key == "date":
                item["date"] = value
            else:
                item[key] = value
        transformed.append(item)

    return {
        "widget_id": widget["id"],
        "type": "grid",
        "title": widget.get("title", "Widget"),
        "sql": current_sql,
        "params": current_params,
        "rows": transformed[:200],
        "meta": {"date_range": {"start": current_start.isoformat(), "end": current_end.isoformat()}, "metric": metric_name, "sort": sort_config},
        "row_count": len(transformed),
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/llm/status")
def get_llm_status(role: str = Depends(get_demo_role)):
    return get_llm_client().status()


@app.get("/api/metadata")
def get_metadata(role: str = Depends(get_demo_role)):
    metadata = get_active_metadata()
    metadata["as_of"] = get_as_of().isoformat()
    allowed_ids = {page["id"] for page in accessible_pages(role)}
    metadata["pages"] = [page for page in metadata.get("pages", []) if page.get("id") in allowed_ids]
    for directory in metadata.get("directories", []):
        retained_subdirectories = []
        for subdirectory in directory.get("subdirectories", []):
            has_pages = any(
                page.get("directory") == directory.get("id") and page.get("subdirectory") == subdirectory.get("id")
                for page in metadata["pages"]
            )
            if has_pages:
                retained_subdirectories.append(subdirectory)
        directory["subdirectories"] = retained_subdirectories
    metadata["directories"] = [
        directory for directory in metadata.get("directories", [])
        if any(page.get("directory") == directory.get("id") for page in metadata["pages"])
    ]
    return metadata


@app.get("/api/page-access")
def get_page_access(path: str, role: str = Depends(get_demo_role)):
    metadata = get_active_metadata()
    page = next((entry for entry in metadata.get("pages", []) if entry.get("route") == path), None)
    if page is None:
        return {"exists": False, "accessible": False, "role": role, "reason": "No page is defined for this route."}
    accessible_ids = {accessible_page["id"] for accessible_page in accessible_pages(role)}
    accessible = page.get("id") in accessible_ids
    return {
        "exists": True,
        "accessible": accessible,
        "page_id": page.get("id"),
        "title": page.get("title"),
        "role": role,
        "reason": None if accessible else f"Your {role} role is not permitted to access this page.",
    }


@app.get("/api/search")
def search_app_metadata(
    q: str = Query(..., min_length=1),
    k: int = Query(default=5, ge=1, le=50),
    role: str = Depends(get_demo_role),
):
    try:
        return search_metadata(q, k=k, role=role)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/roles")
def get_metadata_roles():
    metadata = get_active_metadata()
    return get_roles(metadata)


@app.get("/api/tools")
def get_tools():
    return get_tool_registry()


@app.post("/api/tools/{name}")
def execute_tool_endpoint(name: str, request: ToolRequest, role: str = Depends(get_demo_role)):
    context = ToolContext.from_payload(role, request.ui_context)
    return run_tool(name, request.args, context)


@app.post("/api/agent")
def run_agent_endpoint(request: AgentRequest, role: str = Depends(get_demo_role)):
    requested_role = request.role.strip().casefold()
    allowed_roles = get_allowed_roles()
    if requested_role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Unknown demo role '{request.role}'.")
    if requested_role != role:
        raise HTTPException(status_code=403, detail="The request role must match the active demo role.")
    ui_context = request.ui_context
    if hasattr(ui_context, "model_dump"):
        ui_context = ui_context.model_dump()
    return run_agent(request.message.strip(), role, ui_context=ui_context, session_id=request.session_id)


@app.post("/api/undo")
def undo_agent_endpoint(request: UndoRequest, role: str = Depends(get_demo_role)):
    requested_role = request.role.strip().casefold()
    allowed_roles = get_allowed_roles()
    if requested_role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Unknown demo role '{request.role}'.")
    if requested_role != role:
        raise HTTPException(status_code=403, detail="The request role must match the active demo role.")
    try:
        restored = validate_undo_state(request.state, ToolContext(role))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"restored": restored}


ALLOWED_VERIFY_FIELDS = {
    "page_id",
    "route",
    "path",
    "filters",
    "date_range",
    "sort",
    "sort_direction",
    "direction",
    "custom_start",
    "custom_end",
}


def _normalize_filter_val(val: Any) -> Any:
    if isinstance(val, list):
        if len(val) == 1:
            return val[0]
        return sorted(str(x) for x in val)
    return val


def _normalize_filters(filters: Any) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}
    return {k: _normalize_filter_val(v) for k, v in filters.items() if v not in (None, "", [])}


@app.post("/api/agent/verify")
def verify_agent_endpoint(request: VerifyRequest, role: str = Depends(get_demo_role)):
    cleaned_expected = {k: v for k, v in request.expected.items() if k in ALLOWED_VERIFY_FIELDS}
    cleaned_actual = {k: v for k, v in request.actual.items() if k in ALLOWED_VERIFY_FIELDS}

    differing: list[str] = []
    for k, v in cleaned_expected.items():
        actual_val = cleaned_actual.get(k)
        if k == "filters" and isinstance(v, dict):
            if _normalize_filters(v) != _normalize_filters(actual_val):
                differing.append(k)
        elif k in ("route", "path"):
            exp_r = str(v).rstrip("/")
            act_r = str(cleaned_actual.get("route") or cleaned_actual.get("path") or "").rstrip("/")
            if exp_r != act_r:
                differing.append(k)
        elif k == "date_range":
            exp_d = v.get("preset") if isinstance(v, dict) else v
            act_d = actual_val.get("preset") if isinstance(actual_val, dict) else actual_val
            if exp_d != act_d:
                differing.append(k)
        else:
            if v != actual_val:
                differing.append(k)

    matched = len(differing) == 0
    status_str = "Verified" if matched else "Mismatch"

    verification_result = {
        "status": status_str,
        "matched": matched,
        "differing": differing,
        "expected": cleaned_expected,
        "actual": cleaned_actual,
    }

    record_verification_event(
        session_id=request.session_id,
        verification_result=verification_result,
        role=role,
    )

    return {
        "ok": True,
        "status": status_str,
        "matched": matched,
        "differing": differing,
        "expected": cleaned_expected,
        "actual": cleaned_actual,
    }


@app.get("/api/events/summary")
def get_events_summary_endpoint():
    return get_events_summary()


@app.get("/api/graph/summary")
def get_graph_summary():
    graph = get_graph()
    counts: dict[str, int] = defaultdict(int)
    for _, attributes in graph.nodes(data=True):
        counts[str(attributes.get("type", "unknown"))] += 1
    return {"counts_by_type": dict(sorted(counts.items())), "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}


@app.get("/api/graph/page/{page_id}")
def get_graph_page(page_id: str, role: str = Depends(get_demo_role)):
    allowed_ids = {page["id"] for page in accessible_pages(role)}
    if page_id not in allowed_ids:
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot access page '{page_id}'.")
    neighborhood = get_page_neighborhood(page_id)
    if neighborhood is None:
        raise HTTPException(status_code=404, detail=f"Unknown page '{page_id}'")
    return neighborhood


@app.get("/api/graph/validate-filter")
def validate_graph_filter(page_id: str, name: str, value: str, role: str = Depends(get_demo_role)):
    allowed_ids = {page["id"] for page in accessible_pages(role)}
    if page_id not in allowed_ids:
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot access page '{page_id}'.")
    return is_valid_filter(page_id, name, value)


@app.get("/api/widget-data")
def get_widget_data(
    page_id: str = Query(...),
    widget_id: str = Query(...),
    filters: str | None = Query(default=None),
    date_range: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    role: str = Depends(get_demo_role),
):
    app_data = get_active_metadata()
    views_path = get_active_views_path()
    with views_path.open("r", encoding="utf-8") as views_handle:
        views_manifest = json.load(views_handle)

    page = next((entry for entry in app_data.get("pages", []) if entry.get("id") == page_id), None)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_id}' not found")

    allowed_ids = {accessible_page["id"] for accessible_page in accessible_pages(role)}
    if page_id not in allowed_ids:
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot access page '{page_id}'.")

    widget = next((entry for entry in page.get("widgets", []) if entry.get("id") == widget_id), None)
    if not widget:
        raise HTTPException(status_code=404, detail=f"Widget '{widget_id}' not found on page '{page_id}'")

    view_entry = next(
        (
            entry
            for entry in views_manifest
            if entry.get("page_id") == page_id and entry.get("widget_id") == widget_id
        ),
        None,
    )
    if not view_entry:
        raise HTTPException(
            status_code=404,
            detail=f"Widget '{widget_id}' is not mapped to any data view for page '{page_id}'",
        )

    filter_definitions = {definition["name"]: definition for definition in page.get("filters", [])}
    if filters is None:
        selected_filters = {
            name: definition.get("default", definition.get("default_value"))
            for name, definition in filter_definitions.items()
        }
    else:
        try:
            selected_filters = json.loads(filters)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=422, detail="filters must be a JSON object") from error
        if not isinstance(selected_filters, dict):
            raise HTTPException(status_code=422, detail="filters must be a JSON object keyed by filter name")

    region_scope = region_scope_for_role(role)
    if region_scope and page.get("region_scoped"):
        region_definition = next(
            (item for item in page.get("filters", []) if str(item.get("name", "")).casefold() == "region"),
            None,
        )
        if region_definition:
            region_name = region_definition["name"]
            selected_filters[region_name] = [region_scope] if region_definition.get("type") == "multi_select" else region_scope

    unknown_filter = next((name for name in selected_filters if name not in filter_definitions), None)
    if unknown_filter is not None:
        raise HTTPException(status_code=422, detail=f"Unknown filter '{unknown_filter}' for page '{page_id}'")

    for name, value in selected_filters.items():
        definition = filter_definitions[name]
        if value in (None, "", []):
            continue
        allowed_values = definition.get("allowed_values", [])
        values = value if isinstance(value, list) else [value]
        if definition.get("type") == "multi_select":
            if not isinstance(value, list):
                raise HTTPException(status_code=422, detail=f"Filter '{name}' requires a list of values")
        elif isinstance(value, list):
            raise HTTPException(status_code=422, detail=f"Filter '{name}' accepts a single value")
        invalid_values = [item for item in values if item not in allowed_values]
        if invalid_values:
            raise HTTPException(status_code=422, detail=f"Invalid value for filter '{name}': {invalid_values[0]}")

    date_options = page.get("date_range_options", [])
    selected_date_range = date_range or page.get("default_date_range") or (date_options[0] if date_options else None)
    if date_options and selected_date_range not in date_options:
        raise HTTPException(status_code=422, detail=f"Invalid date range '{selected_date_range}' for page '{page_id}'")
    if not date_options and date_range:
        raise HTTPException(status_code=422, detail=f"Page '{page_id}' does not define date ranges")
    custom_bounds = None
    if start_date is not None or end_date is not None:
        if selected_date_range != "custom" or not start_date or not end_date:
            raise HTTPException(status_code=422, detail="Custom start_date and end_date require the custom date range.")
        try:
            custom_start = date.fromisoformat(start_date)
            custom_end = date.fromisoformat(end_date)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Custom dates must use YYYY-MM-DD format.") from error
        bounds = app_data.get("dimensions", {}).get("date_range", {})
        earliest = date.fromisoformat(str(bounds.get("start", "1900-01-01")))
        latest = date.fromisoformat(str(bounds.get("end", "2999-12-31")))
        if custom_start > custom_end or custom_start < earliest or custom_end > latest:
            raise HTTPException(status_code=422, detail="Custom dates are outside the available data range.")
        custom_bounds = (custom_start, custom_end)

    sort_options = page.get("sort_options", [])
    sort_ids = [option.get("id", option.get("field")) for option in sort_options]
    default_sort = page.get("default_sort", {})
    default_sort_id = default_sort.get("id", default_sort.get("field"))
    selected_sort = sort if sort is not None else default_sort_id
    if selected_sort is None and sort_ids:
        selected_sort = sort_ids[0]
    if sort_options and selected_sort not in sort_ids:
        raise HTTPException(status_code=422, detail=f"Invalid sort option '{selected_sort}' for page '{page_id}'")
    if not sort_options and sort:
        raise HTTPException(status_code=422, detail=f"Page '{page_id}' does not define sort options")

    selected_sort_option = next(
        (option for option in sort_options if option.get("id", option.get("field")) == selected_sort),
        None,
    )
    sort_config = None
    if selected_sort_option:
        order = selected_sort_option.get("order")
        if order is None and default_sort.get("field") == selected_sort:
            order = default_sort.get("order")
        if order is None:
            order = "desc" if "high to low" in selected_sort_option.get("label", "").lower() or "desc" in selected_sort_option.get("label", "").lower() else "asc"
        sort_config = {"field": selected_sort_option.get("field", selected_sort_option.get("id")), "order": order}

    payload = _build_widget_payload(
        page,
        widget,
        view_entry,
        selected_filters,
        selected_date_range or "this_quarter",
        sort_config,
        custom_bounds,
    )
    payload.setdefault("meta", {})["filters_applied"] = selected_filters
    return payload


class SelectAppRequest(BaseModel):
    app_id: str


@app.get("/api/apps")
def get_apps():
    return {"apps": list_apps()}


@app.post("/api/apps/select")
def post_select_app(req: SelectAppRequest):
    try:
        from app.noticed import clear_noticed_cache
        clear_noticed_cache()
        return select_app(req.app_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/api/suggestions")
def get_suggestions(page_id: str = Query(...), role: str = Query(...)):
    from app.suggestions import generate_suggestions
    chips = generate_suggestions(page_id=page_id, role=role)
    return {"page_id": page_id, "role": role, "suggestions": chips}


@app.get("/api/noticed")
@app.get("/api/agent/noticed")
def get_noticed(role: str = Depends(get_demo_role)):
    from app.noticed import compute_noticed
    return compute_noticed(role=role)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
