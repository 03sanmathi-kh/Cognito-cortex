from __future__ import annotations

import difflib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb

from app.analysis.catalog import (
    AnalysisCatalog,
    DimensionDefinition,
    MetricDefinition,
    get_catalog,
)
from app.graph import accessible_pages, role_region_scope
from app import timeutil

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "business.duckdb"
_MAX_QUERIES_PER_CALL = 20
_MAX_QUERY_ROWS = 500


def format_money(val: float | int | None) -> str:
    if val is None:
        return "$0.00"
    num = round(float(val), 2)
    if abs(num) < 1e-9:
        return "$0.00"
    if num < 0:
        return f"-${abs(num):,.2f}"
    return f"${num:,.2f}"


def format_percent(val: float | int | None) -> str:
    if val is None:
        return "0.0%"
    num = round(float(val), 1)
    if abs(num) < 1e-9:
        return "0.0%"
    return f"{num:.1f}%"


def format_count(val: float | int | None) -> str:
    if val is None:
        return "0"
    num = float(val)
    if abs(num) < 1e-9:
        return "0"
    if num.is_integer():
        return f"{int(num):,}"
    return f"{num:,.2f}"


def compute_steepest_risers(
    contributors: list[dict[str, Any]],
    min_previous_share: float = 0.05,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    eligible = []
    for c in contributors:
        p_share = c.get("previous_share", 0.0)
        is_above_min = (p_share >= min_previous_share) if p_share <= 1.0 else (p_share >= min_previous_share * 100)
        pct = c.get("pct_change")
        if is_above_min and pct is not None and pct > 0:
            eligible.append(c)
    return sorted(eligible, key=lambda c: c["pct_change"], reverse=True)[:top_n]


def compute_steepest_decliners(
    contributors: list[dict[str, Any]],
    min_previous_share: float = 0.05,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    eligible = []
    for c in contributors:
        p_share = c.get("previous_share", 0.0)
        is_above_min = (p_share >= min_previous_share) if p_share <= 1.0 else (p_share >= min_previous_share * 100)
        pct = c.get("pct_change")
        if is_above_min and pct is not None and pct < 0:
            eligible.append(c)
    return sorted(eligible, key=lambda c: c["pct_change"])[:top_n]


def compute_steepest_changes(
    contributors: list[dict[str, Any]],
    total_change: float,
    min_previous_share: float = 0.05,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    if total_change < 0:
        return compute_steepest_decliners(contributors, min_previous_share=min_previous_share, top_n=top_n)
    else:
        return compute_steepest_risers(contributors, min_previous_share=min_previous_share, top_n=top_n)



class AnalysisValidationError(ValueError):
    def __init__(
        self,
        message: str,
        suggestions: list[str] | None = None,
        code: str = "invalid_argument",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []
        self.code = code


class AnalysisEngine:
    def __init__(
        self,
        catalog: AnalysisCatalog | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.catalog = catalog or get_catalog()
        self.db_path = db_path or DB_PATH
        self._distinct_values_cache: dict[str, list[str]] = {}

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path), read_only=True)

    def _get_distinct_values(self, dim: DimensionDefinition) -> list[str]:
        cache_key = f"{dim.table}.{dim.column}"
        if cache_key in self._distinct_values_cache:
            return self._distinct_values_cache[cache_key]

        with self._get_connection() as con:
            rows = con.execute(
                f'SELECT DISTINCT "{dim.column}" FROM "{dim.table}" '
                f'WHERE "{dim.column}" IS NOT NULL '
                f'ORDER BY "{dim.column}"'
            ).fetchall()
            values = [str(r[0]) for r in rows if r[0] is not None]
            self._distinct_values_cache[cache_key] = values
            return values

    def _normalize_and_validate_filters(
        self,
        raw_filters: Any,
        role: str | None = None,
    ) -> dict[str, list[str]]:
        parsed_filters: dict[str, list[str]] = {}

        if isinstance(raw_filters, list):
            for item in raw_filters:
                if isinstance(item, str) and ":" in item:
                    k, v = item.split(":", 1)
                    parsed_filters.setdefault(k.strip(), []).append(v.strip())
                elif isinstance(item, dict):
                    for k, v in item.items():
                        vals = v if isinstance(v, list) else [v]
                        parsed_filters.setdefault(str(k), []).extend([str(x) for x in vals])
        elif isinstance(raw_filters, dict):
            for k, v in raw_filters.items():
                if v is None or v == "" or v == []:
                    continue
                vals = v if isinstance(v, list) else [v]
                parsed_filters[str(k)] = [str(x) for x in vals]

        # Apply role region scoping if applicable
        if role is not None:
            region_scope = role_region_scope(role)
            if region_scope is not None:
                parsed_filters["region"] = [region_scope]

        validated: dict[str, list[str]] = {}
        for dim_id, values in parsed_filters.items():
            dim = self.catalog.get_dimension(dim_id)
            if dim is None:
                all_dims = [d.id for d in self.catalog.list_dimensions()]
                suggestions = difflib.get_close_matches(dim_id, all_dims, n=3, cutoff=0.3)
                raise AnalysisValidationError(
                    f"Unknown dimension '{dim_id}'.",
                    suggestions=suggestions,
                    code="unknown_dimension",
                )

            distinct_vals = self._get_distinct_values(dim)
            canonical_values: list[str] = []
            distinct_map = {val.casefold(): val for val in distinct_vals}

            for val in values:
                val_cf = val.casefold()
                if val_cf in distinct_map:
                    canonical_values.append(distinct_map[val_cf])
                else:
                    suggestions = difflib.get_close_matches(val, distinct_vals, n=3, cutoff=0.25)
                    raise AnalysisValidationError(
                        f"Unknown filter value '{val}' for dimension '{dim_id}'.",
                        suggestions=suggestions,
                        code="unknown_filter_value",
                    )
            if canonical_values:
                validated[dim_id] = canonical_values

        return validated

    def _resolve_metric(self, metric_id: str, role: str | None = None) -> MetricDefinition:
        metric = self.catalog.get_metric(metric_id)
        if metric is None:
            all_metrics = [m.id for m in self.catalog.list_metrics()]
            suggestions = difflib.get_close_matches(metric_id, all_metrics, n=3, cutoff=0.3)
            raise AnalysisValidationError(
                f"Unknown metric '{metric_id}'.",
                suggestions=suggestions,
                code="unknown_metric",
            )

        if role is not None and metric.page_ids:
            try:
                allowed_pages = {p["id"] for p in accessible_pages(role)}
                if not any(pid in allowed_pages for pid in metric.page_ids):
                    raise AnalysisValidationError(
                        f"Metric '{metric.label}' is not accessible for role '{role}'.",
                        code="not_permitted",
                    )
            except AnalysisValidationError:
                raise
            except Exception:
                pass

        return metric

    def _resolve_periods(
        self,
        period: str | dict[str, Any],
        compare_to: str = "previous_period",
    ) -> tuple[tuple[date, date], tuple[date, date], str]:
        preset_name: str | None = None
        if isinstance(period, str):
            preset_name = period.strip().lower()
            cur_start, cur_end = timeutil.resolve_period(preset_name)
        elif isinstance(period, dict):
            if "preset" in period and period["preset"]:
                preset_name = str(period["preset"]).strip().lower()
                cur_start, cur_end = timeutil.resolve_period(preset_name)
            else:
                cur_start = date.fromisoformat(str(period["start"]))
                cur_end = date.fromisoformat(str(period["end"]))
        else:
            raise AnalysisValidationError(f"Invalid period format: {period}")

        if compare_to == "same_period_last_year":
            prev_start = date(cur_start.year - 1, cur_start.month, cur_start.day)
            prev_end = date(cur_end.year - 1, cur_end.month, cur_end.day)
        else:  # previous_period
            if preset_name:
                prev_start, prev_end = timeutil.comparison_period(preset_name, cur_start, cur_end)
            else:
                duration = (cur_end - cur_start).days + 1
                prev_end = cur_start - timedelta(days=1)
                prev_start = prev_end - timedelta(days=duration - 1)

        period_label = preset_name or f"{cur_start.isoformat()}..{cur_end.isoformat()}"
        return (cur_start, cur_end), (prev_start, prev_end), period_label

    def compare_periods(
        self,
        metric: str,
        period: str | dict[str, Any],
        compare_to: str = "previous_period",
        filters: dict[str, Any] | list[str] | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        metric_def = self._resolve_metric(metric, role=role)
        validated_filters = self._normalize_and_validate_filters(filters, role=role)
        (cur_start, cur_end), (prev_start, prev_end), period_label = self._resolve_periods(period, compare_to)

        evidence: list[dict[str, Any]] = []

        # Build parameterized where clause for filter dimensions
        filter_sql_parts: list[str] = []
        filter_params: list[Any] = []
        for dim_id, vals in validated_filters.items():
            dim = self.catalog.get_dimension(dim_id)
            if dim:
                placeholders = ", ".join("?" for _ in vals)
                filter_sql_parts.append(f'"{dim.column}" IN ({placeholders})')
                filter_params.extend(vals)
        filter_where = (" AND " + " AND ".join(filter_sql_parts)) if filter_sql_parts else ""

        # Current period query
        sql_cur = (
            f'SELECT {metric_def.sql_expression} AS val '
            f'FROM "{metric_def.base_table}" '
            f'WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
            f'  AND CAST("{metric_def.date_column}" AS DATE) <= ?{filter_where}'
        )
        params_cur = [str(cur_start), str(cur_end)] + filter_params

        # Previous period query
        sql_prev = (
            f'SELECT {metric_def.sql_expression} AS val '
            f'FROM "{metric_def.base_table}" '
            f'WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
            f'  AND CAST("{metric_def.date_column}" AS DATE) <= ?{filter_where}'
        )
        params_prev = [str(prev_start), str(prev_end)] + filter_params

        evidence.append({
            "sql": sql_cur,
            "parameters": params_cur,
            "period": {"start": str(cur_start), "end": str(cur_end)},
            "filters": validated_filters,
        })
        evidence.append({
            "sql": sql_prev,
            "parameters": params_prev,
            "period": {"start": str(prev_start), "end": str(prev_end)},
            "filters": validated_filters,
        })

        with self._get_connection() as con:
            cur_row = con.execute(sql_cur, params_cur).fetchone()
            prev_row = con.execute(sql_prev, params_prev).fetchone()

        cur_val = float(cur_row[0] or 0.0) if cur_row else 0.0
        prev_val = float(prev_row[0] or 0.0) if prev_row else 0.0

        diff = cur_val - prev_val
        pct_change = (diff / prev_val * 100.0) if prev_val != 0.0 else 0.0

        fmt = metric_def.format
        fmt_fn = format_money if fmt == "currency" else (format_percent if fmt == "percent" else format_count)

        return {
            "result": {
                "metric": metric_def.id,
                "label": metric_def.label,
                "format": metric_def.format,
                "period": period_label,
                "compare_to": compare_to,
                "current_period": {"start": str(cur_start), "end": str(cur_end)},
                "previous_period": {"start": str(prev_start), "end": str(prev_end)},
                "current_value": round(cur_val, 2),
                "previous_value": round(prev_val, 2),
                "absolute_change": round(diff, 2),
                "percent_change": round(pct_change, 2),
                "formatted_current": fmt_fn(cur_val),
                "formatted_previous": fmt_fn(prev_val),
                "formatted_change": fmt_fn(diff),
                "formatted_pct_change": format_percent(pct_change),
            },
            "evidence": evidence,
        }

    def find_contributors(
        self,
        metric: str,
        dimension: str,
        period: str | dict[str, Any],
        compare_to: str = "previous_period",
        filters: dict[str, Any] | list[str] | None = None,
        top_n: int = 5,
        role: str | None = None,
    ) -> dict[str, Any]:
        metric_def = self._resolve_metric(metric, role=role)
        dim_def = self.catalog.get_dimension(dimension)
        if dim_def is None:
            all_dims = [d.id for d in self.catalog.list_dimensions()]
            suggestions = difflib.get_close_matches(dimension, all_dims, n=3, cutoff=0.3)
            raise AnalysisValidationError(
                f"Unknown dimension '{dimension}'.",
                suggestions=suggestions,
                code="unknown_dimension",
            )

        validated_filters = self._normalize_and_validate_filters(filters, role=role)
        (cur_start, cur_end), (prev_start, prev_end), period_label = self._resolve_periods(period, compare_to)

        evidence: list[dict[str, Any]] = []

        filter_sql_parts: list[str] = []
        filter_params: list[Any] = []
        for dim_id, vals in validated_filters.items():
            d = self.catalog.get_dimension(dim_id)
            if d:
                placeholders = ", ".join("?" for _ in vals)
                filter_sql_parts.append(f'"{d.column}" IN ({placeholders})')
                filter_params.extend(vals)
        filter_where = (" AND " + " AND ".join(filter_sql_parts)) if filter_sql_parts else ""

        sql_cur = (
            f'SELECT "{dim_def.column}" AS label, {metric_def.sql_expression} AS val '
            f'FROM "{metric_def.base_table}" '
            f'WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
            f'  AND CAST("{metric_def.date_column}" AS DATE) <= ?{filter_where} '
            f'GROUP BY "{dim_def.column}" '
            f'LIMIT {_MAX_QUERY_ROWS}'
        )
        params_cur = [str(cur_start), str(cur_end)] + filter_params

        sql_prev = (
            f'SELECT "{dim_def.column}" AS label, {metric_def.sql_expression} AS val '
            f'FROM "{metric_def.base_table}" '
            f'WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
            f'  AND CAST("{metric_def.date_column}" AS DATE) <= ?{filter_where} '
            f'GROUP BY "{dim_def.column}" '
            f'LIMIT {_MAX_QUERY_ROWS}'
        )
        params_prev = [str(prev_start), str(prev_end)] + filter_params

        evidence.append({
            "sql": sql_cur,
            "parameters": params_cur,
            "period": {"start": str(cur_start), "end": str(cur_end)},
            "filters": validated_filters,
        })
        evidence.append({
            "sql": sql_prev,
            "parameters": params_prev,
            "period": {"start": str(prev_start), "end": str(prev_end)},
            "filters": validated_filters,
        })

        with self._get_connection() as con:
            rows_cur = con.execute(sql_cur, params_cur).fetchall()
            rows_prev = con.execute(sql_prev, params_prev).fetchall()

        cur_map = {str(r[0]): float(r[1] or 0.0) for r in rows_cur if r[0] is not None}
        prev_map = {str(r[0]): float(r[1] or 0.0) for r in rows_prev if r[0] is not None}
        all_labels = sorted(set(cur_map) | set(prev_map))
        total_prev_dim = sum(prev_map.values())

        contributors: list[dict[str, Any]] = []
        for label in all_labels:
            c_val = cur_map.get(label, 0.0)
            p_val = prev_map.get(label, 0.0)
            diff = c_val - p_val
            pct = (diff / p_val * 100.0) if p_val != 0.0 else None
            p_share = (p_val / total_prev_dim) if total_prev_dim != 0.0 else 0.0
            contributors.append({
                "label": label,
                "current": round(c_val, 2),
                "previous": round(p_val, 2),
                "change": round(diff, 2),
                "percent_change": round(pct, 2) if pct is not None else 0.0,
                "pct_change": round(pct, 2) if pct is not None else None,
                "previous_share": round(p_share, 4),
                "formatted_current": format_money(c_val),
                "formatted_previous": format_money(p_val),
                "formatted_change": format_money(diff),
                "formatted_pct_change": format_percent(pct),
            })

        total_change = sum(item["change"] for item in contributors)

        for item in contributors:
            if total_change != 0.0:
                item["share_of_total_change"] = round(item["change"] / total_change, 4)
            else:
                item["share_of_total_change"] = 0.0
            item["formatted_share"] = format_percent(abs(item["share_of_total_change"]) * 100)

        # Sort by absolute contribution descending
        contributors.sort(key=lambda x: abs(x["change"]), reverse=True)

        # Slice to top_n if desired, preserving 1.0 sum via 'Other' if truncated
        result_rows: list[dict[str, Any]] = []
        if top_n is not None and len(contributors) > top_n:
            top_slice = contributors[:top_n]
            other_slice = contributors[top_n:]
            other_cur = sum(x["current"] for x in other_slice)
            other_prev = sum(x["previous"] for x in other_slice)
            other_diff = sum(x["change"] for x in other_slice)
            other_pct = (other_diff / other_prev * 100.0) if other_prev != 0.0 else None
            other_share = round(other_diff / total_change, 4) if total_change != 0.0 else 0.0
            other_p_share = round(other_prev / total_prev_dim, 4) if total_prev_dim != 0.0 else 0.0

            result_rows = top_slice + [{
                "label": "Other",
                "current": round(other_cur, 2),
                "previous": round(other_prev, 2),
                "change": round(other_diff, 2),
                "percent_change": round(other_pct, 2) if other_pct is not None else 0.0,
                "pct_change": round(other_pct, 2) if other_pct is not None else None,
                "share_of_total_change": other_share,
                "previous_share": other_p_share,
                "formatted_current": format_money(other_cur),
                "formatted_previous": format_money(other_prev),
                "formatted_change": format_money(other_diff),
                "formatted_pct_change": format_percent(other_pct),
                "formatted_share": format_percent(abs(other_share) * 100),
            }]
        else:
            result_rows = contributors

        return {
            "result": {
                "metric": metric_def.id,
                "dimension": dim_def.id,
                "dimension_label": dim_def.label,
                "period": period_label,
                "compare_to": compare_to,
                "total_change": round(total_change, 2),
                "contributors": result_rows,
                "all_contributors": contributors,
            },
            "evidence": evidence,
        }

    def trend(
        self,
        metric: str,
        grain: str,
        period: str | dict[str, Any],
        filters: dict[str, Any] | list[str] | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        metric_def = self._resolve_metric(metric, role=role)
        validated_filters = self._normalize_and_validate_filters(filters, role=role)
        (cur_start, cur_end), _, period_label = self._resolve_periods(period)

        grain_clean = str(grain).strip().lower()
        if grain_clean not in {"day", "week", "month"}:
            raise AnalysisValidationError(
                f"Unknown grain '{grain}'. Allowed: day, week, month.",
                suggestions=["day", "week", "month"],
                code="unknown_grain",
            )

        if grain_clean == "day":
            date_expr = f'strftime(CAST("{metric_def.date_column}" AS DATE), \'%Y-%m-%d\')'
        elif grain_clean == "week":
            date_expr = f'strftime(date_trunc(\'week\', CAST("{metric_def.date_column}" AS DATE)), \'%Y-%m-%d\')'
        else:
            date_expr = f'strftime(date_trunc(\'month\', CAST("{metric_def.date_column}" AS DATE)), \'%Y-%m\')'

        filter_sql_parts: list[str] = []
        filter_params: list[Any] = []
        for dim_id, vals in validated_filters.items():
            d = self.catalog.get_dimension(dim_id)
            if d:
                placeholders = ", ".join("?" for _ in vals)
                filter_sql_parts.append(f'"{d.column}" IN ({placeholders})')
                filter_params.extend(vals)
        filter_where = (" AND " + " AND ".join(filter_sql_parts)) if filter_sql_parts else ""

        sql = (
            f'SELECT {date_expr} AS pt, {metric_def.sql_expression} AS val '
            f'FROM "{metric_def.base_table}" '
            f'WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
            f'  AND CAST("{metric_def.date_column}" AS DATE) <= ?{filter_where} '
            f'GROUP BY pt '
            f'ORDER BY pt ASC '
            f'LIMIT {_MAX_QUERY_ROWS}'
        )
        params = [str(cur_start), str(cur_end)] + filter_params

        evidence = [{
            "sql": sql,
            "parameters": params,
            "period": {"start": str(cur_start), "end": str(cur_end)},
            "filters": validated_filters,
        }]

        with self._get_connection() as con:
            rows = con.execute(sql, params).fetchall()

        points = [{"period": str(r[0]), "value": round(float(r[1] or 0.0), 2)} for r in rows if r[0] is not None]

        summary: dict[str, Any] = {}
        if points:
            highest_pt = max(points, key=lambda p: p["value"])
            lowest_pt = min(points, key=lambda p: p["value"])
            first_pt = points[0]
            last_pt = points[-1]

            fmt_func = format_money if metric_def.format == "currency" else (format_count if metric_def.format == "count" else str)

            highest = {
                "period": highest_pt["period"],
                "value": highest_pt["value"],
                "formatted": fmt_func(highest_pt["value"]),
            }
            lowest = {
                "period": lowest_pt["period"],
                "value": lowest_pt["value"],
                "formatted": fmt_func(lowest_pt["value"]),
            }

            if len(points) >= 2:
                prev_pt = points[-2]
                last_diff = round(last_pt["value"] - prev_pt["value"], 2)
                last_pct = round((last_diff / prev_pt["value"] * 100.0), 2) if prev_pt["value"] != 0 else 0.0

                first_diff = round(last_pt["value"] - first_pt["value"], 2)
                first_pct = round((first_diff / first_pt["value"] * 100.0), 2) if first_pt["value"] != 0 else 0.0

                last_vs_prev = {
                    "last_period": last_pt["period"],
                    "previous_period": prev_pt["period"],
                    "absolute_change": last_diff,
                    "percent_change": last_pct,
                    "formatted_absolute_change": fmt_func(last_diff),
                    "formatted_percent_change": format_percent(last_pct),
                }

                first_to_last = {
                    "first_period": first_pt["period"],
                    "last_period": last_pt["period"],
                    "absolute_change": first_diff,
                    "percent_change": first_pct,
                    "formatted_absolute_change": fmt_func(first_diff),
                    "formatted_percent_change": format_percent(first_pct),
                }
            else:
                last_vs_prev = None
                first_to_last = None
                last_diff = 0.0
                last_pct = 0.0
                first_pct = 0.0

            summary = {
                "highest": highest,
                "lowest": lowest,
                "highest_point": highest,
                "lowest_point": lowest,
                "last_vs_previous": last_vs_prev,
                "first_to_last": first_to_last,
                "last_point_versus_previous_absolute": last_diff,
                "last_point_versus_previous_percent": last_pct,
                "first_to_last_percent_change": first_pct,
            }

        return {
            "result": {
                "metric": metric_def.id,
                "label": metric_def.label,
                "grain": grain_clean,
                "period": period_label,
                "points": points,
                "summary": summary,
            },
            "evidence": evidence,
        }

    def investigate(
        self,
        metric: str,
        period: str | dict[str, Any],
        compare_to: str = "previous_period",
        filters: dict[str, Any] | list[str] | None = None,
        max_depth: int = 3,
        role: str | None = None,
    ) -> dict[str, Any]:
        metric_def = self._resolve_metric(metric, role=role)
        current_filters = self._normalize_and_validate_filters(filters, role=role)
        (cur_start, cur_end), (prev_start, prev_end), period_label = self._resolve_periods(period, compare_to)

        all_evidence: list[dict[str, Any]] = []
        query_count = 0

        # Step 1: Baseline comparison
        comp_res = self.compare_periods(
            metric=metric_def.id,
            period=period,
            compare_to=compare_to,
            filters=current_filters,
            role=role,
        )
        baseline = comp_res["result"]
        all_evidence.extend(comp_res["evidence"])
        query_count += len(comp_res["evidence"])

        total_change = baseline["absolute_change"]
        if abs(total_change) < 0.01:
            return {
                "result": {
                    "metric": metric_def.id,
                    "label": metric_def.label,
                    "period": baseline["period"],
                    "compare_to": compare_to,
                    "baseline": baseline,
                    "mixed_change": False,
                    "steps": [],
                    "tree": [],
                    "total_change_explained_by_top_3": [0.0],
                    "concentration": "broadly spread",
                    "top_dimensions": [],
                    "top_segments": [],
                    "steepest_segments": [],
                    "steepest_risers": [],
                    "steepest_decliners": [],
                    "top_contributors": [],
                },
                "evidence": all_evidence,
            }

        candidate_dimensions = [
            d.id for d in self.catalog.list_dimensions()
            if d.id not in current_filters
        ]

        steps: list[dict[str, Any]] = []
        tree: list[dict[str, Any]] = []
        level_top3_shares: list[float] = []
        top_dimensions_data: list[dict[str, Any]] = []
        top_segments_data: list[dict[str, Any]] = []
        steepest_segments_data: list[dict[str, Any]] = []
        mixed_change: bool = False

        active_filters = {k: list(v) for k, v in current_filters.items()}

        def _score_dimension(contribs: list[dict[str, Any]]) -> tuple[float, float, float]:
            n = len(contribs)
            if n < 3:
                return -1.0, 0.0, 0.0
            top1_share = contribs[0].get("share_of_total_change", 0.0)
            top2_share = top1_share + (contribs[1].get("share_of_total_change", 0.0) if n > 1 else 0.0)
            abs_top2_share = abs(top2_share)
            equal_split = 2.0 / float(n)
            score = abs_top2_share / equal_split if equal_split > 0 else 0.0
            abs_tot_chg = sum(abs(c["change"]) for c in contribs)
            return score, abs_top2_share, abs_tot_chg

        for depth in range(1, max_depth + 1):
            if not candidate_dimensions or query_count >= _MAX_QUERIES_PER_CALL:
                break

            evaluated: list[dict[str, Any]] = []

            for dim_id in candidate_dimensions:
                if query_count + 2 > _MAX_QUERIES_PER_CALL:
                    break

                contrib_res = self.find_contributors(
                    metric=metric_def.id,
                    dimension=dim_id,
                    period=period,
                    compare_to=compare_to,
                    filters=active_filters,
                    top_n=None,
                    role=role,
                )
                all_evidence.extend(contrib_res["evidence"])
                query_count += len(contrib_res["evidence"])

                contributors = contrib_res["result"]["contributors"]
                if not contributors:
                    continue

                score, top2_share, abs_tot_chg = _score_dimension(contributors)
                if score < 0:
                    continue

                dim_obj = self.catalog.get_dimension(dim_id)
                evaluated.append({
                    "dimension": dim_id,
                    "dimension_label": dim_obj.label if dim_obj else dim_id,
                    "score": score,
                    "top2_share": top2_share,
                    "abs_total_change": abs_tot_chg,
                    "contributors": contributors,
                })

            if not evaluated:
                break

            # Pick dimensions by score; break ties by larger absolute change
            evaluated.sort(key=lambda x: (x["score"], x["abs_total_change"]), reverse=True)

            # At depth 1: record the TOP 2 dimensions
            if depth == 1:
                all_eval_contribs = [c for d_info in evaluated for c in d_info["contributors"]]
                max_abs_contrib_dollar = max((abs(c.get("change", 0.0)) for c in all_eval_contribs), default=0.0)
                max_abs_contrib_pct = max((abs(c.get("pct_change", 0.0) or 0.0) for c in all_eval_contribs), default=0.0)

                abs_tot_dollar = abs(total_change)
                abs_tot_pct = abs(baseline.get("percent_change", 0.0) or 0.0)

                is_mixed_dollar = (max_abs_contrib_dollar > 0 and abs_tot_dollar < 0.25 * max_abs_contrib_dollar)
                is_mixed_pct = (max_abs_contrib_pct > 0 and abs_tot_pct < 0.25 * max_abs_contrib_pct)
                mixed_change = bool(is_mixed_dollar or is_mixed_pct)

                for d_info in evaluated[:2]:
                    d_risers = compute_steepest_risers(
                        d_info["contributors"],
                        min_previous_share=0.05,
                        top_n=3,
                    )
                    d_decliners = compute_steepest_decliners(
                        d_info["contributors"],
                        min_previous_share=0.05,
                        top_n=3,
                    )
                    if mixed_change:
                        for item in d_risers + d_decliners:
                            item["share"] = None
                            item["share_of_total_change"] = None
                            item["formatted_share"] = None

                    top_dimensions_data.append({
                        "dimension": d_info["dimension"],
                        "dimension_label": d_info["dimension_label"],
                        "score": round(d_info["score"], 4),
                        "top2_share": None if mixed_change else round(d_info["top2_share"], 4),
                        "contributors": [
                            {
                                "label": c["label"],
                                "current": c["current"],
                                "previous": c["previous"],
                                "change": c["change"],
                                "percent_change": c["percent_change"],
                                "pct_change": c.get("pct_change"),
                                "previous_share": c.get("previous_share"),
                                "share": None if mixed_change else c["share_of_total_change"],
                                "share_of_total_change": None if mixed_change else c["share_of_total_change"],
                                "formatted_current": c.get("formatted_current"),
                                "formatted_previous": c.get("formatted_previous"),
                                "formatted_change": c.get("formatted_change"),
                                "formatted_pct_change": c.get("formatted_pct_change"),
                                "formatted_share": None if mixed_change else c.get("formatted_share"),
                            }
                            for c in d_info["contributors"][:3]
                        ],
                        "steepest_risers": d_risers,
                        "steepest_decliners": d_decliners,
                    })

                # Compute top_segments and steepest_segments between the top 2 dimensions using ONE extra query
                if len(top_dimensions_data) >= 2 and query_count < _MAX_QUERIES_PER_CALL:
                    dim_a = self.catalog.get_dimension(top_dimensions_data[0]["dimension"])
                    dim_b = self.catalog.get_dimension(top_dimensions_data[1]["dimension"])
                    if dim_a and dim_b:
                        filter_sql_parts = []
                        filter_params = []
                        for f_id, vals in active_filters.items():
                            d = self.catalog.get_dimension(f_id)
                            if d:
                                placeholders = ", ".join("?" for _ in vals)
                                filter_sql_parts.append(f'"{d.column}" IN ({placeholders})')
                                filter_params.extend(vals)
                        f_where = (" AND " + " AND ".join(filter_sql_parts)) if filter_sql_parts else ""

                        sql_seg = (
                            f'WITH cur AS ('
                            f'  SELECT "{dim_a.column}" AS dim_a, "{dim_b.column}" AS dim_b, {metric_def.sql_expression} AS val '
                            f'  FROM "{metric_def.base_table}" '
                            f'  WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
                            f'    AND CAST("{metric_def.date_column}" AS DATE) <= ?{f_where} '
                            f'  GROUP BY "{dim_a.column}", "{dim_b.column}"'
                            f'), '
                            f'prev AS ('
                            f'  SELECT "{dim_a.column}" AS dim_a, "{dim_b.column}" AS dim_b, {metric_def.sql_expression} AS val '
                            f'  FROM "{metric_def.base_table}" '
                            f'  WHERE CAST("{metric_def.date_column}" AS DATE) >= ? '
                            f'    AND CAST("{metric_def.date_column}" AS DATE) <= ?{f_where} '
                            f'  GROUP BY "{dim_a.column}", "{dim_b.column}"'
                            f') '
                            f'SELECT '
                            f'  COALESCE(cur.dim_a, prev.dim_a) AS dim_a, '
                            f'  COALESCE(cur.dim_b, prev.dim_b) AS dim_b, '
                            f'  COALESCE(cur.val, 0.0) AS cur_val, '
                            f'  COALESCE(prev.val, 0.0) AS prev_val '
                            f'FROM cur FULL OUTER JOIN prev ON cur.dim_a = prev.dim_a AND cur.dim_b = prev.dim_b'
                        )
                        seg_params = [str(cur_start), str(cur_end)] + filter_params + [str(prev_start), str(prev_end)] + filter_params

                        all_evidence.append({
                            "sql": sql_seg,
                            "parameters": seg_params,
                            "period": {"current": [str(cur_start), str(cur_end)], "previous": [str(prev_start), str(prev_end)]},
                            "filters": active_filters,
                        })
                        query_count += 1

                        with self._get_connection() as con:
                            seg_rows = con.execute(sql_seg, seg_params).fetchall()

                        parsed_segments = []
                        baseline_prev_val = float(baseline.get("previous_value", 0.0) or 0.0)
                        for s_row in seg_rows:
                            va = str(s_row[0]) if s_row[0] is not None else "Unknown"
                            vb = str(s_row[1]) if s_row[1] is not None else "Unknown"
                            c_v = float(s_row[2] or 0.0)
                            p_v = float(s_row[3] or 0.0)
                            d_v = c_v - p_v
                            pct_v = (d_v / p_v * 100.0) if p_v != 0.0 else None
                            share_v = None if mixed_change else (round(d_v / total_change, 4) if total_change != 0.0 else 0.0)
                            prev_share_v = round(p_v / baseline_prev_val, 4) if baseline_prev_val != 0.0 else 0.0
                            parsed_segments.append({
                                "segment": f"{va} x {vb}",
                                "dimension_a": dim_a.id,
                                "dimension_b": dim_b.id,
                                "value_a": va,
                                "value_b": vb,
                                "current": round(c_v, 2),
                                "previous": round(p_v, 2),
                                "change": round(d_v, 2),
                                "percent_change": round(pct_v, 2) if pct_v is not None else 0.0,
                                "pct_change": round(pct_v, 2) if pct_v is not None else None,
                                "share": share_v,
                                "share_of_total_change": share_v,
                                "previous_share": prev_share_v,
                                "formatted_current": format_money(c_v),
                                "formatted_previous": format_money(p_v),
                                "formatted_change": format_money(d_v),
                                "formatted_pct_change": format_percent(pct_v),
                                "formatted_share": None if mixed_change else format_percent(abs(share_v) * 100),
                            })

                        parsed_segments_by_abs = sorted(parsed_segments, key=lambda s: abs(s["change"]), reverse=True)
                        top_segments_data = parsed_segments_by_abs[:3]

                        steepest_seg_risers = compute_steepest_risers(
                            parsed_segments,
                            min_previous_share=0.02,
                            top_n=3,
                        )
                        steepest_seg_decliners = compute_steepest_decliners(
                            parsed_segments,
                            min_previous_share=0.02,
                            top_n=3,
                        )
                        if total_change < 0:
                            steepest_segments_data = steepest_seg_decliners or steepest_seg_risers
                        else:
                            steepest_segments_data = steepest_seg_risers or steepest_seg_decliners

            best_entry = evaluated[0]
            best_dim_id = best_entry["dimension"]
            best_contributors = best_entry["contributors"]
            top_val = best_contributors[0]

            # Top-3 share for concentration calculation
            top3 = best_contributors[:3]
            top3_abs = sum(abs(x["change"]) for x in top3)
            tot_dim_abs = sum(abs(x["change"]) for x in best_contributors)
            dim_top3_share = (top3_abs / tot_dim_abs) if tot_dim_abs > 0 else 0.0
            level_top3_shares.append(round(dim_top3_share, 4))

            steps.append({
                "depth": depth,
                "dimension": best_dim_id,
                "dimension_label": best_entry["dimension_label"],
                "score": round(best_entry["score"], 4),
                "top3_share": None if mixed_change else round(dim_top3_share, 4),
                "top_driver": top_val["label"],
                "driver_change": top_val["change"],
                "driver_share": None if mixed_change else top_val["share_of_total_change"],
            })

            tree_contribs = []
            for c in best_contributors[:5]:
                c_copy = dict(c)
                if mixed_change:
                    c_copy["share"] = None
                    c_copy["share_of_total_change"] = None
                    c_copy["formatted_share"] = None
                else:
                    c_copy["share"] = c.get("share_of_total_change")
                tree_contribs.append(c_copy)

            tree.append({
                "depth": depth,
                "dimension": best_dim_id,
                "dimension_label": best_entry["dimension_label"],
                "score": round(best_entry["score"], 4),
                "top3_share": None if mixed_change else round(dim_top3_share, 4),
                "contributors": tree_contribs,
                "drilled_into": top_val["label"],
            })

            active_filters[best_dim_id] = [top_val["label"]]
            candidate_dimensions.remove(best_dim_id)

        first_level_share = level_top3_shares[0] if level_top3_shares else 0.0
        concentration = "concentrated" if first_level_share >= 0.60 else "broadly spread"

        headline_contributors = tree[0]["contributors"] if tree else []

        all_dim_risers: list[dict[str, Any]] = []
        all_dim_decliners: list[dict[str, Any]] = []
        for td in top_dimensions_data:
            for s in td.get("steepest_risers", []):
                if s not in all_dim_risers:
                    all_dim_risers.append(s)
            for s in td.get("steepest_decliners", []):
                if s not in all_dim_decliners:
                    all_dim_decliners.append(s)

        res_dict = {
            "metric": metric_def.id,
            "label": metric_def.label,
            "period": baseline["period"],
            "compare_to": compare_to,
            "baseline": baseline,
            "mixed_change": mixed_change,
            "steps": steps,
            "tree": tree,
            "total_change_explained_by_top_3": level_top3_shares,
            "concentration": concentration,
            "top_dimensions": top_dimensions_data,
            "top_segments": top_segments_data,
            "steepest_segments": steepest_segments_data,
            "steepest_risers": all_dim_risers,
            "steepest_decliners": all_dim_decliners,
            "top_contributors": headline_contributors,
        }

        return {
            "result": res_dict,
            "evidence": all_evidence,
        }


# Global engine singleton
_ENGINE: AnalysisEngine | None = None


def get_engine() -> AnalysisEngine:
    global _ENGINE
    if _ENGINE is None:
        try:
            from app.apps import get_active_db_path
            _ENGINE = AnalysisEngine(catalog=get_catalog(), db_path=get_active_db_path())
        except Exception:
            _ENGINE = AnalysisEngine(catalog=get_catalog())
    return _ENGINE


def compare_periods(
    metric: str,
    period: str | dict[str, Any],
    compare_to: str = "previous_period",
    filters: dict[str, Any] | list[str] | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    return get_engine().compare_periods(metric, period, compare_to, filters, role=role)


def find_contributors(
    metric: str,
    dimension: str,
    period: str | dict[str, Any],
    compare_to: str = "previous_period",
    filters: dict[str, Any] | list[str] | None = None,
    top_n: int = 5,
    role: str | None = None,
) -> dict[str, Any]:
    return get_engine().find_contributors(metric, dimension, period, compare_to, filters, top_n=top_n, role=role)


def trend(
    metric: str,
    grain: str,
    period: str | dict[str, Any],
    filters: dict[str, Any] | list[str] | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    return get_engine().trend(metric, grain, period, filters, role=role)


def investigate(
    metric: str,
    period: str | dict[str, Any],
    compare_to: str = "previous_period",
    filters: dict[str, Any] | list[str] | None = None,
    max_depth: int = 3,
    role: str | None = None,
) -> dict[str, Any]:
    return get_engine().investigate(metric, period, compare_to, filters, max_depth=max_depth, role=role)
