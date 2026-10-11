from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
METADATA_PATH = DATA_DIR / "app_metadata.json"
DB_PATH = DATA_DIR / "business.duckdb"
MANIFEST_PATH = DATA_DIR / "views_manifest.json"

BASE_VIEW_ORDER = [
    "base_sales",
    "base_inventory",
    "base_expenses",
    "base_targets",
    "base_customers",
]


def load_metadata():
    with METADATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def drop_view(conn, view_name: str):
    conn.execute(f'DROP VIEW IF EXISTS "{view_name}"')


def create_base_views(conn):
    drop_view(conn, "base_sales")
    conn.execute(
        '''
        CREATE VIEW base_sales AS
        SELECT
            o.order_id AS order_id,
            o.order_date AS order_date,
            o.region AS region,
            o.channel AS channel,
            p.category AS category,
            p.product_id AS product_id,
            p.product_name AS product_name,
            o.customer_id AS customer_id,
            c.segment AS role,
            c.segment AS segment,
            o.status AS status,
            o.status AS event_type,
            oi.quantity AS quantity,
            oi.discount_pct AS discount_pct,
            oi.revenue AS revenue,
            oi.cost AS cost,
            CASE p.category
                WHEN 'Packaged Foods' THEN 'Northline Foods'
                WHEN 'Beverages' THEN 'Riverbend Beverage'
                WHEN 'Household' THEN 'Evergreen Supply'
                WHEN 'Personal Care' THEN 'Hearth & Halo'
                ELSE 'Core Supplier'
            END AS supplier,
            CONCAT(o.region, ' Team') AS team
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        JOIN products p ON p.product_id = oi.product_id
        LEFT JOIN customers c ON c.customer_id = o.customer_id
        '''
    )

    drop_view(conn, "base_inventory")
    conn.execute(
        '''
        CREATE VIEW base_inventory AS
        SELECT
            i.snapshot_date AS snapshot_date,
            i.region AS region,
            CASE i.region
                WHEN 'North' THEN 'Retail'
                WHEN 'South' THEN 'Online'
                WHEN 'East' THEN 'Partner'
                ELSE 'Retail'
            END AS channel,
            p.category AS category,
            p.product_id AS product_id,
            p.product_name AS product_name,
            i.stock_on_hand AS stock_on_hand,
            i.reorder_level AS reorder_level,
            CASE p.category
                WHEN 'Packaged Foods' THEN 'Northline Foods'
                WHEN 'Beverages' THEN 'Riverbend Beverage'
                WHEN 'Household' THEN 'Evergreen Supply'
                WHEN 'Personal Care' THEN 'Hearth & Halo'
                ELSE 'Core Supplier'
            END AS supplier,
            CONCAT(i.region, ' Ops') AS team,
            CASE
                WHEN i.stock_on_hand < i.reorder_level THEN 'low_stock'
                ELSE 'healthy_stock'
            END AS event_type,
            CASE
                WHEN i.region = 'North' THEN 'Operations Lead'
                WHEN i.region = 'South' THEN 'Inventory Lead'
                WHEN i.region = 'East' THEN 'Fulfillment Lead'
                ELSE 'Warehouse Lead'
            END AS role
        FROM inventory i
        JOIN products p ON p.product_id = i.product_id
        '''
    )

    drop_view(conn, "base_expenses")
    conn.execute(
        '''
        CREATE VIEW base_expenses AS
        SELECT
            e.month AS month,
            e.region AS region,
            CASE e.region
                WHEN 'North' THEN 'Retail'
                WHEN 'South' THEN 'Partner'
                WHEN 'East' THEN 'Online'
                ELSE 'Retail'
            END AS channel,
            CASE e.expense_type
                WHEN 'Logistics' THEN 'Operations'
                WHEN 'Payroll' THEN 'People'
                WHEN 'Marketing' THEN 'Sales'
                WHEN 'Facilities' THEN 'Facilities'
                ELSE 'Operations'
            END AS category,
            e.expense_type AS event_type,
            e.expense_type AS expense_type,
            e.amount AS amount,
            CASE e.region
                WHEN 'North' THEN 'Northline Foods'
                WHEN 'South' THEN 'Evergreen Supply'
                WHEN 'East' THEN 'Riverbend Beverage'
                ELSE 'Core Supplier'
            END AS supplier,
            CONCAT(e.region, ' Finance') AS team,
            CASE
                WHEN e.region = 'North' THEN 'Finance Lead'
                WHEN e.region = 'South' THEN 'Cost Lead'
                WHEN e.region = 'East' THEN 'Risk Lead'
                ELSE 'Finance Lead'
            END AS role
        FROM expenses e
        '''
    )

    drop_view(conn, "base_targets")
    conn.execute(
        '''
        CREATE VIEW base_targets AS
        SELECT
            t.month AS month,
            t.region AS region,
            CASE t.region
                WHEN 'North' THEN 'Retail'
                WHEN 'South' THEN 'Partner'
                WHEN 'East' THEN 'Online'
                ELSE 'Retail'
            END AS channel,
            t.category AS category,
            t.revenue_target AS revenue_target,
            CASE t.category
                WHEN 'Packaged Foods' THEN 'Northline Foods'
                WHEN 'Beverages' THEN 'Riverbend Beverage'
                WHEN 'Household' THEN 'Evergreen Supply'
                WHEN 'Personal Care' THEN 'Hearth & Halo'
                ELSE 'Core Supplier'
            END AS supplier,
            CONCAT(t.region, ' Targets') AS team,
            CASE
                WHEN t.region = 'North' THEN 'Sales Lead'
                WHEN t.region = 'South' THEN 'Regional Lead'
                WHEN t.region = 'East' THEN 'Channel Lead'
                ELSE 'Sales Lead'
            END AS role,
            'target' AS event_type
        FROM targets t
        '''
    )

    drop_view(conn, "base_customers")
    conn.execute(
        '''
        CREATE VIEW base_customers AS
        SELECT
            c.signup_date AS signup_date,
            c.region AS region,
            CASE c.region
                WHEN 'North' THEN 'Retail'
                WHEN 'South' THEN 'Online'
                WHEN 'East' THEN 'Partner'
                ELSE 'Retail'
            END AS channel,
            CASE c.segment
                WHEN 'Enterprise' THEN 'Packaged Foods'
                WHEN 'SMB' THEN 'Household'
                ELSE 'Beverages'
            END AS category,
            c.customer_id AS customer_id,
            c.customer_name AS customer_name,
            c.segment AS role,
            c.segment AS segment,
            c.segment AS event_type,
            CASE c.region
                WHEN 'North' THEN 'Northline Foods'
                WHEN 'South' THEN 'Evergreen Supply'
                WHEN 'East' THEN 'Riverbend Beverage'
                ELSE 'Core Supplier'
            END AS supplier,
            CONCAT(c.region, ' Customer Team') AS team
        FROM customers c
        '''
    )


def choose_base(page_id: str, widget: dict[str, object]) -> str:
    text = f"{page_id} {widget.get('id', '')} {widget.get('title', '')}".lower()
    if any(token in text for token in ["inventory", "stock", "warehouse", "supplier", "capacity", "aging", "po", "turnover", "alert"]):
        return "base_inventory"
    if any(token in text for token in ["expense", "opex", "freight", "shipping", "variance", "margin", "profit", "loss", "cost"]):
        return "base_expenses"
    if any(token in text for token in ["target", "quota", "attainment", "pacing"]):
        return "base_targets"
    if any(token in text for token in ["customer", "segment", "retention", "lifetime", "repeat", "churn", "user", "audit", "role"]):
        return "base_customers"
    return "base_sales"


def choose_date_column(base: str) -> str:
    mapping = {
        "base_sales": "order_date",
        "base_inventory": "snapshot_date",
        "base_expenses": "month",
        "base_targets": "month",
        "base_customers": "signup_date",
    }
    return mapping.get(base, "order_date")


def build_manifest_columns(page: dict, widget: dict, base: str, date_column: str):
    selected = []
    for name in page.get("filters", []):
        selected.append(name["name"])
    if date_column not in selected:
        selected.insert(0, date_column)
    for name in widget.get("columns", []) or []:
        selected.append(name)
    if base == "base_sales":
        for name in ["product_name", "customer_id", "quantity", "revenue", "cost", "status"]:
            selected.append(name)
    elif base == "base_inventory":
        for name in ["product_name", "stock_on_hand", "reorder_level"]:
            selected.append(name)
    elif base == "base_expenses":
        for name in ["expense_type", "amount"]:
            selected.append(name)
    elif base == "base_targets":
        for name in ["category", "revenue_target"]:
            selected.append(name)
    elif base == "base_customers":
        for name in ["customer_name", "segment", "customer_id"]:
            selected.append(name)
    return list(dict.fromkeys(selected))


def build_widget_select(base: str, page: dict, widget: dict, data_view: str):
    date_column = choose_date_column(base)
    filter_names = [entry["name"] for entry in page.get("filters", [])]
    valid_columns = {
        "order_date",
        "region",
        "channel",
        "category",
        "role",
        "segment",
        "status",
        "event_type",
        "supplier",
        "team",
        "customer_id",
        "customer_name",
        "product_id",
        "product_name",
        "quantity",
        "revenue",
        "cost",
        "amount",
        "revenue_target",
        "stock_on_hand",
        "reorder_level",
        "expense_type",
        "snapshot_date",
        "month",
        "signup_date",
    }
    selected = []
    if date_column:
        selected.append(f'{date_column} AS "{date_column}"')
    for filter_name in filter_names:
        if filter_name in valid_columns:
            selected.append(f'"{filter_name}" AS "{filter_name}"')
    if base == "base_sales":
        for extra in ["product_name", "customer_id", "quantity", "revenue", "cost", "status", "role", "segment"]:
            if extra in valid_columns and extra not in {item.split(" AS ")[0].strip('"') for item in selected}:
                selected.append(f'"{extra}" AS "{extra}"')
    elif base == "base_inventory":
        for extra in ["product_name", "stock_on_hand", "reorder_level", "supplier", "team", "category"]:
            if extra in valid_columns and extra not in {item.split(" AS ")[0].strip('"') for item in selected}:
                selected.append(f'"{extra}" AS "{extra}"')
    elif base == "base_expenses":
        for extra in ["expense_type", "amount", "supplier", "team", "category"]:
            if extra in valid_columns and extra not in {item.split(" AS ")[0].strip('"') for item in selected}:
                selected.append(f'"{extra}" AS "{extra}"')
    elif base == "base_targets":
        for extra in ["category", "revenue_target", "supplier", "team"]:
            if extra in valid_columns and extra not in {item.split(" AS ")[0].strip('"') for item in selected}:
                selected.append(f'"{extra}" AS "{extra}"')
    elif base == "base_customers":
        for extra in ["customer_name", "segment", "customer_id", "supplier", "team", "category"]:
            if extra in valid_columns and extra not in {item.split(" AS ")[0].strip('"') for item in selected}:
                selected.append(f'"{extra}" AS "{extra}"')
    return f'SELECT {", ".join(selected)} FROM "{base}"'


def create_widget_views(conn, metadata):
    manifest = []
    unmapped = []
    for page in metadata["pages"]:
        page_id = page["id"]
        for widget in page.get("widgets", []):
            data_view = widget.get("data_view")
            base = choose_base(page_id, widget)
            if not data_view:
                unmapped.append({"page_id": page_id, "widget_id": widget.get("id"), "reason": "missing_data_view"})
                continue
            date_column = choose_date_column(base)
            drop_view(conn, data_view)
            select_sql = build_widget_select(base, page, widget, data_view)
            conn.execute(f'CREATE VIEW "{data_view}" AS {select_sql}')
            manifest.append(
                {
                    "page_id": page_id,
                    "widget_id": widget["id"],
                    "data_view": data_view,
                    "base": base,
                    "columns": build_manifest_columns(page, widget, base, date_column),
                    "filterable_columns": [entry["name"] for entry in page.get("filters", [])],
                    "date_column": date_column,
                }
            )
    return manifest, unmapped


def main():
    metadata = load_metadata()
    conn = duckdb.connect(str(DB_PATH))
    create_base_views(conn)
    manifest, unmapped = create_widget_views(conn, metadata)
    with MANIFEST_PATH.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    print(f"Created {len(manifest)} widget views.")
    if unmapped:
        print("Unmapped widgets:")
        for item in unmapped:
            print(f"- {item['page_id']} / {item['widget_id']}: {item['reason']}")
    else:
        print("Unmapped widgets: none")

    conn.close()


if __name__ == "__main__":
    main()
