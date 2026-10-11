import difflib
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import duckdb
import sqlglot
from sqlglot import exp

from app.graph import (
    accessible_pages,
    get_page,
    get_valid_filters,
    is_valid_date_range,
    is_valid_filter,
    is_valid_sort,
    role_region_scope,
    suggest_pages,
)
from app.retrieval import search as retrieval_search

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "business.duckdb"
_ALLOWED_ROLES = {"admin", "regional_manager", "analyst"}
_QUERY_TIMEOUT_SECONDS = 5
_MAX_QUERY_ROWS = 500


def _role_key(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _get_allowed_roles() -> set[str]:
    roles = set(_ALLOWED_ROLES)
    try:
        from app.apps import get_active_metadata
        for r in get_active_metadata().get("roles") or []:
            if isinstance(r, dict):
                roles.add(str(r.get("id")))
            elif isinstance(r, str):
                roles.add(r)
    except Exception:
        pass
    return roles


def _canonical_role(value: str) -> str:
    allowed = _get_allowed_roles()
    for role in allowed:
        if _role_key(role) == _role_key(value):
            return role
    raise ValueError(f"Unknown role '{value}'. Allowed roles: {', '.join(sorted(allowed))}")


@dataclass
class ToolContext:
    role: str
    region_scope: str | None = None
    ui_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.role = _canonical_role(self.role)
        self.region_scope = region_scope_for_role(self.role)
        if not isinstance(self.ui_context, dict):
            self.ui_context = {}

    @classmethod
    def from_payload(cls, role: str, ui_context: dict[str, Any] | None = None) -> "ToolContext":
        return cls(role=role, ui_context=ui_context or {})


def region_scope_for_role(role: str) -> str | None:
    return role_region_scope(_canonical_role(role))


def _result(
    context: ToolContext,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    ok: bool,
    data: Any = None,
    error_code: str | None = None,
    error_message: str | None = None,
    suggestions: list[Any] | None = None,
    requires_confirmation: bool = False,
    ui_action: dict[str, Any] | None = None,
    sql: str | None = None,
    date_range: Any = None,
    filters: Any = None,
) -> dict[str, Any]:
    current_filters = context.ui_context.get("filters", {})
    current_date_range = context.ui_context.get("date_range")
    return {
        "ok": ok,
        "data": data,
        "error": {"code": error_code, "message": error_message},
        "suggestions": suggestions or [],
        "requires_confirmation": requires_confirmation,
        "ui_action": ui_action,
        "receipt": {
            "tool": tool_name,
            "arguments": arguments,
            "sql": sql,
            "date_range": current_date_range if date_range is None else date_range,
            "filters": current_filters if filters is None else filters,
        },
    }


def _error(
    context: ToolContext,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    message: str,
    suggestions: list[Any] | None = None,
) -> dict[str, Any]:
    return _result(
        context,
        tool_name,
        arguments,
        ok=False,
        error_code=code,
        error_message=message,
        suggestions=suggestions,
    )


def _page_allowed(page: dict[str, Any], role: str) -> bool:
    allowed_roles = page.get("allowed_roles")
    if not allowed_roles:
        return True
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]
    accepted_roles = {_role_key(role)}
    if _role_key(role) == "regionalmanager":
        accepted_roles.add(_role_key("analyst"))
    return any(_role_key(str(item.get("id", "") if isinstance(item, dict) else item)) in accepted_roles for item in allowed_roles)


def _get_accessible_page(page_id: str, context: ToolContext, tool: str, args: dict[str, Any]):
    page = get_page(page_id)
    if page is None:
        return None, _error(
            context,
            tool,
            args,
            "page_not_found",
            f"Page '{page_id}' does not exist.",
            suggest_pages(page_id, role=context.role, k=5),
        )
    if not _page_allowed(page, context.role):
        return None, _error(
            context,
            tool,
            args,
            "role_not_permitted",
            f"Role '{context.role}' cannot access page '{page_id}'.",
            suggest_pages(str(page.get("title", page_id)), role=context.role, k=5),
        )
    return page, None


def _canonical_filter_name(page_id: str, name: str) -> str | None:
    for definition in get_valid_filters(page_id):
        if _role_key(str(definition["name"])) == _role_key(name):
            return str(definition["name"])
    return None


def _canonical_filter_value(allowed: list[Any], value: Any) -> Any:
    for candidate in allowed:
        if str(candidate).casefold() == str(value).casefold():
            return candidate
    return value


def _apply_regional_scope(context: ToolContext, page_id: str, filters: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if context.region_scope is None:
        return filters, None
    region_name = _canonical_filter_name(page_id, "region")
    if region_name is None:
        return filters, None
    requested = filters.get(region_name)
    requested_values = requested if isinstance(requested, list) else [requested]
    if requested is not None and any(str(value).casefold() != context.region_scope.casefold() for value in requested_values):
        return None, _error(
            context,
            "set_filters",
            {"page_id": page_id, "filters": filters},
            "role_not_permitted",
            f"Role '{context.role}' is restricted to region '{context.region_scope}'.",
            [context.region_scope],
        )
    filters[region_name] = context.region_scope
    return filters, None


def search_components(context: ToolContext, query: str, k: int = 5) -> dict[str, Any]:
    args = {"query": query, "k": k}
    allowed_page_ids = {page["id"] for page in accessible_pages(context.role)}
    try:
        matches = retrieval_search(query, k=k, role=context.role)
    except ValueError as error:
        return _error(context, "search_components", args, "invalid_role", str(error))
    visible_matches = [match for match in matches if match.get("page_id") in allowed_page_ids]
    return _result(context, "search_components", args, ok=True, data=visible_matches)


def navigate(context: ToolContext, page_id: str) -> dict[str, Any]:
    args = {"page_id": page_id}
    page, failure = _get_accessible_page(page_id, context, "navigate", args)
    if failure:
        return failure
    return _result(
        context,
        "navigate",
        args,
        ok=True,
        data={"page_id": page_id, "title": page.get("title"), "route": page.get("route")},
        ui_action={"type": "navigate", "page_id": page_id, "route": page.get("route")},
    )


def set_filters(context: ToolContext, page_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    args = {"page_id": page_id, "filters": filters}
    page, failure = _get_accessible_page(page_id, context, "set_filters", args)
    if failure:
        return failure
    if not isinstance(filters, dict):
        return _error(context, "set_filters", args, "invalid_input", "filters must be an object keyed by filter name")

    canonical_filters: dict[str, Any] = {}
    changed: list[dict[str, Any]] = []
    suggestions: list[Any] = []
    for requested_name, requested_value in filters.items():
        canonical_name = _canonical_filter_name(page_id, str(requested_name))
        if canonical_name is None:
            validation = is_valid_filter(page_id, str(requested_name), requested_value)
            suggestions.extend(validation.get("suggestions", []))
            return _error(
                context,
                "set_filters",
                args,
                "invalid_filter",
                validation.get("reason", f"Unknown filter '{requested_name}'"),
                list(dict.fromkeys(suggestions)),
            )

        definition = next(item for item in get_valid_filters(page_id) if item["name"] == canonical_name)
        allowed_values = definition.get("allowed_values", [])
        requested_values = requested_value if isinstance(requested_value, list) else [requested_value]
        if definition.get("type") == "multi_select" and requested_value is not None and not isinstance(requested_value, list):
            canonical_values = [_canonical_filter_value(allowed_values, requested_value)]
            result_value: Any = canonical_values
        elif isinstance(requested_value, list):
            canonical_values = [_canonical_filter_value(allowed_values, value) for value in requested_values]
            result_value = canonical_values
        else:
            canonical_values = [_canonical_filter_value(allowed_values, requested_value)]
            result_value = canonical_values[0] if canonical_values else None

        validation_value = result_value
        validation = is_valid_filter(page_id, canonical_name, validation_value)
        if not validation.get("valid"):
            suggestions.extend(validation.get("suggestions", []))
            return _error(context, "set_filters", args, "invalid_filter_value", validation.get("reason", "Invalid filter value"), list(dict.fromkeys(suggestions)))

        if len(requested_values) == len(canonical_values):
            for old, new in zip(requested_values, canonical_values):
                if str(old) != str(new):
                    changed.append({"name": canonical_name, "from": old, "to": new})
        canonical_filters[canonical_name] = result_value

    scoped_filters, scope_failure = _apply_regional_scope(context, page_id, canonical_filters)
    if scope_failure:
        return scope_failure

    if context.region_scope is not None:
        region_name = _canonical_filter_name(page_id, "region")
        if region_name and region_name not in canonical_filters:
            scoped_filters[region_name] = context.region_scope
            changed.append({"name": region_name, "from": None, "to": context.region_scope})

    data = {"page_id": page_id, "filters": scoped_filters, "canonicalized": changed}
    return _result(
        context,
        "set_filters",
        args,
        ok=True,
        data=data,
        ui_action={"type": "set_filters", "page_id": page_id, "filters": scoped_filters},
        filters=scoped_filters,
    )


def set_date_range(
    context: ToolContext,
    page_id: str,
    date_range: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    args = {"page_id": page_id, "date_range": date_range, "start": start, "end": end}
    page, failure = _get_accessible_page(page_id, context, "set_date_range", args)
    if failure:
        return failure
    validation = is_valid_date_range(page_id, date_range)
    if not validation.get("valid"):
        return _error(context, "set_date_range", args, "invalid_date_range", validation["reason"], validation.get("suggestions"))

    if date_range == "custom":
        try:
            start_date = date.fromisoformat(start or "")
            end_date = date.fromisoformat(end or "")
        except ValueError:
            return _error(context, "set_date_range", args, "invalid_date", "Custom ranges require ISO dates in YYYY-MM-DD format.")
        if start_date >= end_date:
            return _error(context, "set_date_range", args, "invalid_date", "Custom range start must be before its end.")
    elif start is not None or end is not None:
        return _error(context, "set_date_range", args, "invalid_input", "start and end are only accepted for the custom date range.")

    data = {"page_id": page_id, "date_range": date_range}
    if date_range == "custom":
        data.update({"start": start, "end": end})
    return _result(
        context,
        "set_date_range",
        args,
        ok=True,
        data=data,
        ui_action={"type": "set_date_range", **data},
        date_range=data,
    )


def set_sort(context: ToolContext, page_id: str, field: str, direction: str) -> dict[str, Any]:
    args = {"page_id": page_id, "field": field, "direction": direction}
    page, failure = _get_accessible_page(page_id, context, "set_sort", args)
    if failure:
        return failure
    validation = is_valid_sort(page_id, field)
    if not validation.get("valid"):
        return _error(context, "set_sort", args, "invalid_sort", validation["reason"], validation.get("suggestions"))
    direction = direction.casefold()
    if direction not in {"asc", "desc"}:
        return _error(context, "set_sort", args, "invalid_direction", "direction must be 'asc' or 'desc'.", ["asc", "desc"])

    data = {"page_id": page_id, "field": field, "direction": direction}
    return _result(
        context,
        "set_sort",
        args,
        ok=True,
        data=data,
        ui_action={"type": "set_sort", **data},
    )


def run_page_action(context: ToolContext, page_id: str, action_id: str) -> dict[str, Any]:
    args = {"page_id": page_id, "action_id": action_id}
    page, failure = _get_accessible_page(page_id, context, "run_page_action", args)
    if failure:
        return failure
    action = next((item for item in (page.get("actions") or []) if item.get("id") == action_id), None)
    if action is None:
        suggestions = difflib.get_close_matches(action_id, [str(item.get("id")) for item in (page.get("actions") or [])], n=3, cutoff=0.35)
        return _error(context, "run_page_action", args, "action_not_found", f"Action '{action_id}' is not defined for page '{page_id}'.", suggestions)

    confirmation = bool(action.get("requires_confirmation", False))
    if confirmation and context.role == "analyst":
        return _error(context, "run_page_action", args, "role_not_permitted", "Analysts cannot run actions that require confirmation.")
    return _result(
        context,
        "run_page_action",
        args,
        ok=True,
        data={"page_id": page_id, "action_id": action_id, "label": action.get("label")},
        requires_confirmation=confirmation,
        ui_action={"type": "run_page_action", "page_id": page_id, "action_id": action_id},
    )


def _allowed_relations(connection: duckdb.DuckDBPyConnection) -> set[str]:
    rows = connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    all_tables = {str(row[0]) for row in rows}
    prefixed = {t for t in all_tables if t.casefold().startswith(("base_", "v_"))}
    try:
        from app.apps import get_active_app_id
        if get_active_app_id() != "meridian":
            return all_tables
    except Exception:
        pass
    return prefixed


def _sql_functions(expression: exp.Expression):
    for function in expression.find_all(exp.Func):
        if isinstance(function, exp.Anonymous):
            yield str(function.name).casefold()
        else:
            yield str(function.sql_name()).casefold()


def _validate_and_scope_sql(sql: str, role: str, connection: duckdb.DuckDBPyConnection) -> tuple[str | None, str | None, list[str]]:
    if not isinstance(sql, str) or not sql.strip():
        return None, "sql must be a non-empty string", []

    tokens = sqlglot.Tokenizer().tokenize(sql)
    if any(token.comments for token in tokens):
        return None, "SQL comments are not accepted", []

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as error:
        return None, f"Invalid SQL: {error}", []
    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        return None, "Exactly one SQL statement is allowed", []
    query = statements[0]
    if not isinstance(query, (exp.Select, exp.SetOperation)):
        return None, "Only SELECT, WITH ... SELECT, or SELECT set operations are allowed", []

    forbidden_functions = {
        "glob", "query", "query_table", "query_table_function", "read_xlsx", "excel_scan",
        "sqlite_scan", "postgres_scan", "mysql_scan", "iceberg_scan", "delta_scan",
        "httpfs", "read_file", "read_text", "read_blob",
    }
    for function_name in _sql_functions(query):
        if (
            function_name in forbidden_functions
            or function_name.startswith("read_")
            or function_name.endswith("_scan")
        ):
            return None, f"File, external-source, or dynamic-query function '{function_name}' is not allowed", []

    allowed_relations = _allowed_relations(connection)
    cte_names = {cte.alias_or_name.casefold() for cte in query.find_all(exp.CTE)}
    tables = list(query.find_all(exp.Table))
    for table in tables:
        relation = table.name
        if not isinstance(table.this, exp.Identifier) or not relation:
            return None, "Table functions and unnamed relations are not allowed", sorted(allowed_relations)
        if table.args.get("db") is not None or table.args.get("catalog") is not None:
            return None, "Schema-qualified relations are not allowed", sorted(allowed_relations)
        if relation.casefold() in cte_names:
            continue
        if relation not in allowed_relations:
            suggestions = difflib.get_close_matches(relation, sorted(allowed_relations), n=5, cutoff=0.25)
            return None, f"Relation '{relation}' is not allowed", suggestions or sorted(allowed_relations)

    if not any(table.name.casefold() not in cte_names for table in tables):
        return None, "Queries must reference at least one allowlisted analytics relation", sorted(allowed_relations)

    region_scope = region_scope_for_role(role)
    if region_scope is not None:
        for table in tables:
            relation = table.name
            if relation.casefold() in cte_names:
                continue
            columns = connection.execute(f'DESCRIBE SELECT * FROM "{relation}"').fetchall()
            if not any(str(column[0]).casefold() == "region" for column in columns):
                return None, f"Relation '{relation}' has no region column; South-only scope cannot be guaranteed", []

        for table in tables:
            relation = table.name
            if relation.casefold() in cte_names:
                continue
            original_alias = table.args.get("alias")
            alias = original_alias.copy() if original_alias else exp.TableAlias(this=exp.to_identifier(relation))
            source = table.copy()
            source.set("alias", None)
            scoped_select = (
                exp.select("*")
                .from_(source)
                .where(exp.column("region").eq(exp.Literal.string(region_scope)))
            )
            replacement = exp.Subquery(this=scoped_select, alias=alias)
            table.replace(replacement)

    scoped_sql = query.sql(dialect="duckdb")
    executed_sql = f"SELECT * FROM ({scoped_sql}) AS tool_query LIMIT {_MAX_QUERY_ROWS}"
    return executed_sql, None, []


def query_data(context: ToolContext, sql: str) -> dict[str, Any]:
    args = {"sql": sql}
    connection = None
    timer = None
    try:
        try:
            from app.apps import get_active_db_path
            db_file = get_active_db_path()
        except Exception:
            db_file = DB_PATH
        connection = duckdb.connect(str(db_file), read_only=True)
        executed_sql, validation_error, suggestions = _validate_and_scope_sql(sql, context.role, connection)
        if validation_error:
            return _error(context, "query_data", args, "invalid_sql", validation_error, suggestions)

        timer = threading.Timer(_QUERY_TIMEOUT_SECONDS, connection.interrupt)
        timer.daemon = True
        timer.start()
        cursor = connection.execute(executed_sql)
        columns = [item[0] for item in cursor.description or []]
        rows = [dict(zip(columns, row)) for row in cursor.fetchmany(_MAX_QUERY_ROWS)]
        data = {"columns": columns, "rows": rows, "row_count": len(rows)}
        return _result(
            context,
            "query_data",
            args,
            ok=True,
            data=data,
            sql=executed_sql,
            filters={"region": context.region_scope} if context.region_scope else context.ui_context.get("filters", {}),
        )
    except duckdb.InterruptException:
        return _error(context, "query_data", args, "query_timeout", f"Query exceeded {_QUERY_TIMEOUT_SECONDS} seconds.")
    except Exception as error:
        return _error(context, "query_data", args, "query_failed", str(error))
    finally:
        if timer:
            timer.cancel()
        if connection:
            connection.close()


def render_chart(
    context: ToolContext,
    title: str,
    chart_type: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    args = {"title": title, "chart_type": chart_type, "columns": columns, "rows": rows}
    if chart_type not in {"line", "bar", "pie"}:
        return _error(context, "render_chart", args, "invalid_chart_type", "chart_type must be line, bar, or pie.", ["line", "bar", "pie"])
    if not isinstance(title, str) or not title.strip():
        return _error(context, "render_chart", args, "invalid_input", "title must be a non-empty string.")
    if not isinstance(columns, list) or not columns or any(not isinstance(column, str) for column in columns):
        return _error(context, "render_chart", args, "invalid_input", "columns must be a non-empty list of column names.")
    if not isinstance(rows, list) or len(rows) > 200:
        return _error(context, "render_chart", args, "invalid_input", "rows must contain at most 200 records.")
    missing = [column for column in columns if any(not isinstance(row, dict) or column not in row for row in rows)]
    if missing or not rows:
        return _error(context, "render_chart", args, "invalid_columns", "Every requested column must exist in the provided rows.", missing or columns)
    chart = {"title": title.strip(), "chart_type": chart_type, "columns": columns, "rows": rows}
    return _result(
        context,
        "render_chart",
        args,
        ok=True,
        data=chart,
        ui_action={"type": "render_chart", "chart": chart},
    )


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


_TOOL_DEFINITIONS = [
    {"name": "search_components", "description": "Find metadata pages and widgets accessible to the current role.", "input_schema": _object_schema({"query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 50}}, ["query"])},
    {"name": "navigate", "description": "Suggest navigation to an accessible metadata page.", "input_schema": _object_schema({"page_id": {"type": "string"}}, ["page_id"])},
    {"name": "set_filters", "description": "Validate metadata-defined filters and suggest a UI filter update.", "input_schema": _object_schema({"page_id": {"type": "string"}, "filters": {"type": "object", "additionalProperties": {}}}, ["page_id", "filters"])},
    {"name": "set_date_range", "description": "Validate a page date range and suggest a UI date-range update.", "input_schema": _object_schema({"page_id": {"type": "string"}, "date_range": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}}, ["page_id", "date_range"])},
    {"name": "set_sort", "description": "Validate a metadata-defined sort field and direction.", "input_schema": _object_schema({"page_id": {"type": "string"}, "field": {"type": "string"}, "direction": {"type": "string", "enum": ["asc", "desc"]}}, ["page_id", "field", "direction"])},
    {"name": "run_page_action", "description": "Validate a metadata-defined page action and report its confirmation requirement.", "input_schema": _object_schema({"page_id": {"type": "string"}, "action_id": {"type": "string"}}, ["page_id", "action_id"])},
    {"name": "query_data", "description": "Run one read-only SELECT query against allowlisted analytics relations.", "input_schema": _object_schema({"sql": {"type": "string"}}, ["sql"])},
    {"name": "render_chart", "description": "Validate a chart specification for the frontend.", "input_schema": _object_schema({"title": {"type": "string"}, "chart_type": {"type": "string", "enum": ["line", "bar", "pie"]}, "columns": {"type": "array", "items": {"type": "string"}}, "rows": {"type": "array", "maxItems": 200, "items": {"type": "object"}}}, ["title", "chart_type", "columns", "rows"])},
]


def get_tool_registry() -> list[dict[str, Any]]:
    return [{**tool, "input_schema": {**tool["input_schema"]}} for tool in _TOOL_DEFINITIONS]


_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_components": search_components,
    "navigate": navigate,
    "set_filters": set_filters,
    "set_date_range": set_date_range,
    "set_sort": set_sort,
    "run_page_action": run_page_action,
    "query_data": query_data,
    "render_chart": render_chart,
}


def run_tool(name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return _error(context, name, arguments, "tool_not_found", f"Tool '{name}' is not registered.", [tool["name"] for tool in _TOOL_DEFINITIONS])
    try:
        return handler(context, **arguments)
    except TypeError as error:
        return _error(context, name, arguments, "invalid_arguments", str(error))
