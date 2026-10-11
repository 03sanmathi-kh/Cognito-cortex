from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data" / "analysis_catalog.json"
DB_PATH = ROOT / "data" / "business.duckdb"


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    label: str
    description: str
    base_table: str
    date_column: str
    sql_expression: str
    format: str  # "currency", "count", "percent"
    ratio_of: list[str] | None = None
    page_ids: list[str] = field(default_factory=list)
    home_page: str | None = None


@dataclass(frozen=True)
class DimensionDefinition:
    id: str
    label: str
    column: str
    table: str
    description: str


class AnalysisCatalog:
    def __init__(
        self,
        metrics: dict[str, MetricDefinition],
        dimensions: dict[str, DimensionDefinition],
    ) -> None:
        self.metrics = metrics
        self.dimensions = dimensions

    def get_metric(self, metric_id: str) -> MetricDefinition | None:
        return self.metrics.get(metric_id)

    def get_dimension(self, dimension_id: str) -> DimensionDefinition | None:
        return self.dimensions.get(dimension_id)

    def list_metrics(self) -> list[MetricDefinition]:
        return list(self.metrics.values())

    def list_dimensions(self) -> list[DimensionDefinition]:
        return list(self.dimensions.values())


_CACHED_CATALOG: AnalysisCatalog | None = None


def load_catalog(
    catalog_path: Path | None = None,
    db_path: Path | None = None,
    validate: bool = True,
) -> AnalysisCatalog:
    cpath = catalog_path or CATALOG_PATH
    dpath = db_path or DB_PATH

    if not cpath.exists():
        raise FileNotFoundError(f"Analysis catalog file not found: {cpath}")

    with cpath.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    metrics_raw = data.get("metrics", [])
    dimensions_raw = data.get("dimensions", [])

    metrics: dict[str, MetricDefinition] = {}
    for item in metrics_raw:
        metric = MetricDefinition(
            id=item["id"],
            label=item["label"],
            description=item.get("description", ""),
            base_table=item["base_table"],
            date_column=item["date_column"],
            sql_expression=item["sql_expression"],
            format=item.get("format", "number"),
            ratio_of=item.get("ratio_of"),
            page_ids=item.get("page_ids", []),
            home_page=item.get("home_page") or (item.get("page_ids", [None])[0] if item.get("page_ids") else None),
        )
        metrics[metric.id] = metric

    dimensions: dict[str, DimensionDefinition] = {}
    for item in dimensions_raw:
        dim = DimensionDefinition(
            id=item["id"],
            label=item["label"],
            column=item["column"],
            table=item["table"],
            description=item.get("description", ""),
        )
        dimensions[dim.id] = dim

    if validate and dpath.exists():
        _validate_catalog(metrics, dimensions, dpath)

    return AnalysisCatalog(metrics=metrics, dimensions=dimensions)


def _validate_catalog(
    metrics: dict[str, MetricDefinition],
    dimensions: dict[str, DimensionDefinition],
    db_path: Path,
) -> None:
    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to open DuckDB for catalog validation: {exc}") from exc

    try:
        # Validate each metric
        for metric_id, metric in metrics.items():
            # 1. Base table and date column
            try:
                con.execute(f'SELECT "{metric.date_column}" FROM "{metric.base_table}" WHERE 1=0')
            except Exception as exc:
                raise ValueError(
                    f"Catalog validation failed for metric '{metric_id}': "
                    f"date column '{metric.date_column}' on table '{metric.base_table}' error: {exc}"
                ) from exc

            # 2. SQL aggregate expression
            try:
                con.execute(f'SELECT {metric.sql_expression} FROM "{metric.base_table}" WHERE 1=0')
            except Exception as exc:
                raise ValueError(
                    f"Catalog validation failed for metric '{metric_id}': "
                    f"SQL expression '{metric.sql_expression}' on table '{metric.base_table}' error: {exc}"
                ) from exc

        # Validate each dimension
        for dim_id, dim in dimensions.items():
            try:
                con.execute(f'SELECT "{dim.column}" FROM "{dim.table}" WHERE 1=0')
            except Exception as exc:
                raise ValueError(
                    f"Catalog validation failed for dimension '{dim_id}': "
                    f"column '{dim.column}' on table '{dim.table}' error: {exc}"
                ) from exc
    finally:
        con.close()


def get_catalog() -> AnalysisCatalog:
    global _CACHED_CATALOG
    if _CACHED_CATALOG is None:
        try:
            from app.apps import get_active_catalog_path, get_active_db_path
            cpath = get_active_catalog_path()
            dpath = get_active_db_path()
            if cpath.exists():
                _CACHED_CATALOG = load_catalog(cpath, dpath, validate=False)
            else:
                _CACHED_CATALOG = load_catalog()
        except Exception:
            _CACHED_CATALOG = load_catalog()
    return _CACHED_CATALOG


def get_metric(metric_id: str) -> MetricDefinition | None:
    return get_catalog().get_metric(metric_id)


def get_dimension(dimension_id: str) -> DimensionDefinition | None:
    return get_catalog().get_dimension(dimension_id)


def list_metrics() -> list[MetricDefinition]:
    return get_catalog().list_metrics()


def list_dimensions() -> list[DimensionDefinition]:
    return get_catalog().list_dimensions()
