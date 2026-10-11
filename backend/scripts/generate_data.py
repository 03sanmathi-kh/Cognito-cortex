from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
from app.timeutil import get_as_of

DATA_DIR = ROOT / "data"
METADATA_PATH = DATA_DIR / "app_metadata.json"
DB_PATH = DATA_DIR / "business.duckdb"
AS_OF = pd.Timestamp(get_as_of().isoformat())
START_DATE = AS_OF - pd.DateOffset(years=2)

rng = np.random.default_rng(42)


def load_metadata():
    with METADATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_dimension_values():
    metadata = load_metadata()
    regions = metadata["dimensions"]["regions"]
    channels = metadata["dimensions"]["channels"]
    categories_raw = metadata["dimensions"]["categories"]

    if isinstance(categories_raw, list) and categories_raw and isinstance(categories_raw[0], dict):
        categories = [item["name"] for item in categories_raw]
    else:
        categories = list(categories_raw)

    return regions, channels, categories


def build_default_products(categories):
    default_map = {
        "Packaged Foods": [
            "Granola Crunch Cereal",
            "Organic Pasta Sauce",
            "Artisan Roasted Nuts",
        ],
        "Beverages": [
            "Sparkling Spring Water",
            "Cold Brew Coffee",
            "Citrus Electrolyte Tea",
        ],
        "Household": [
            "Eco Dish Soap",
            "Multi-Surface Spray",
            "Recycled Paper Towels",
        ],
        "Personal Care": [
            "Hydrating Herbal Lotion",
            "Botanical Body Wash",
            "Bamboo Toothbrush",
        ],
    }
    products = []
    for category in categories:
        names = default_map.get(category, [f"{category} Item {i}" for i in range(1, 4)])
        if len(names) < 3:
            names = names + [f"{category} Item {i}" for i in range(len(names) + 1, 4)]
        products.extend([(category, names[i]) for i in range(3)])
    return products


def product_catalog(regions, channels, categories):
    metadata = load_metadata()
    category_lookup = {}
    for item in metadata["dimensions"]["categories"]:
        if isinstance(item, dict):
            category_lookup[item["name"]] = item.get("products", [])

    product_rows = []
    price_map = {
        "Packaged Foods": 8.5,
        "Beverages": 4.25,
        "Household": 10.5,
        "Personal Care": 13.5,
    }
    product_names = []
    for category in categories:
        names = category_lookup.get(category, [])
        if len(names) >= 3:
            chosen = names[:3]
        else:
            chosen = build_default_products([category])[0:3]
        for idx, product_name in enumerate(chosen, start=1):
            product_id = f"P{len(product_names) + 1:04d}"
            unit_price = round(price_map.get(category, 10) * (1 + rng.uniform(-0.08, 0.18)), 2)
            unit_cost = round(unit_price * rng.uniform(0.52, 0.72), 2)
            product_rows.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "category": category,
                    "unit_price": unit_price,
                    "unit_cost": unit_cost,
                }
            )
            product_names.append(product_name)

    if len(product_rows) != 12:
        fallback_rows = []
        for category in categories:
            for idx in range(1, 4):
                product_id = f"P{len(fallback_rows) + 1:04d}"
                product_name = f"{category} Essential {idx}"
                unit_price = round(price_map.get(category, 10) * (1 + rng.uniform(-0.08, 0.18)), 2)
                unit_cost = round(unit_price * rng.uniform(0.52, 0.72), 2)
                fallback_rows.append(
                    {
                        "product_id": product_id,
                        "product_name": product_name,
                        "category": category,
                        "unit_price": unit_price,
                        "unit_cost": unit_cost,
                    }
                )
        return pd.DataFrame(fallback_rows)

    return pd.DataFrame(product_rows)


def region_weights(regions):
    weights = {
        "North": 0.92,
        "South": 0.88,
        "East": 0.85,
        "West": 1.15,
    }
    region_list = list(regions)
    total = sum(weights.get(region, 1.0) for region in region_list)
    return {region: weights.get(region, 1.0) / total for region in region_list}


def generate_customers(regions, categories):
    region_probs = region_weights(regions)
    total_customers = 2500
    customer_rows = []
    segment_probs = [0.18, 0.42, 0.40]
    segments = ["Enterprise", "SMB", "Retail"]
    n_regions = len(regions)
    start_date = START_DATE
    end_date = AS_OF

    for idx in range(1, total_customers + 1):
        region = rng.choice(regions, p=[region_probs[r] for r in regions])
        segment = rng.choice(segments, p=segment_probs)
        signup_offset_days = int(rng.integers(0, (end_date - start_date).days + 1))
        signup_date = (start_date + pd.Timedelta(days=signup_offset_days)).date()
        customer_rows.append(
            {
                "customer_id": f"CUST_{idx:05d}",
                "customer_name": f"Customer {idx:05d}",
                "region": region,
                "segment": segment,
                "signup_date": signup_date,
            }
        )

    customers = pd.DataFrame(customer_rows)
    customers["signup_date"] = pd.to_datetime(customers["signup_date"])
    return customers


def generate_orders(customers_df, regions, channels):
    dates = pd.date_range(end=AS_OF, start=START_DATE, freq="D")
    region_probs = region_weights(regions)
    channel_probs = {
        "North": {"Online": 0.45, "Retail": 0.35, "Partner": 0.20},
        "South": {"Online": 0.38, "Retail": 0.32, "Partner": 0.30},
        "East": {"Online": 0.42, "Retail": 0.39, "Partner": 0.19},
        "West": {"Online": 0.46, "Retail": 0.30, "Partner": 0.24},
    }
    day_of_year = np.arange(len(dates))
    yearly_seasonality = 1 + 0.04 * np.sin((day_of_year / 365.0) * 2 * np.pi + 1.5)
    weekly_pattern = np.where(dates.dayofweek >= 5, 0.95, 1.01)
    trend = 1 + 0.018 * (np.arange(len(dates)) / len(dates))
    counts = np.clip(np.rint(68 * yearly_seasonality * weekly_pattern * trend), 50, 92).astype(int)

    rows = []
    order_counter = 1
    total_orders = int(counts.sum())
    customer_ids = customers_df["customer_id"].tolist()
    for day, count in zip(dates, counts):
        for _ in range(count):
            region = rng.choice(regions, p=[region_probs[r] for r in regions])
            channel = rng.choice(channels, p=[channel_probs[region][c] for c in channels])
            customer_id = rng.choice(customer_ids)
            status = rng.choice(["completed", "returned", "cancelled"], p=[0.86, 0.09, 0.05])
            rows.append(
                {
                    "order_id": f"ORD_{order_counter:07d}",
                    "order_date": day.date(),
                    "customer_id": customer_id,
                    "region": region,
                    "channel": channel,
                    "status": status,
                }
            )
            order_counter += 1

    orders = pd.DataFrame(rows)
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    return orders


def build_order_items(orders_df, products_df):
    id_map = products_df.set_index("product_id").to_dict("index")
    order_items = []
    promo_product = "P010" if "P010" in id_map else products_df[products_df["category"] == "Household"]["product_id"].tolist()[0]
    promo_start = AS_OF - pd.DateOffset(days=29)
    for _, order in orders_df.iterrows():
        item_count = int(rng.integers(1, 5))
        for _ in range(item_count):
            product_id = rng.choice(products_df["product_id"].tolist())
            product = id_map[product_id]
            quantity = int(rng.integers(1, 8))
            base_discount = float(rng.uniform(0.04, 0.17))
            if order["order_date"] >= promo_start and product_id == promo_product:
                quantity = int(round(quantity * 1.6))
                base_discount = 0.18
            row = {
                "order_id": order["order_id"],
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": float(product["unit_price"]),
                "discount_pct": round(base_discount, 4),
                "revenue": 0.0,
                "cost": 0.0,
            }
            row["revenue"] = round(float(row["quantity"]) * float(row["unit_price"]) * (1 - row["discount_pct"]), 2)
            row["cost"] = round(float(row["quantity"]) * float(product["unit_cost"]), 2)
            order_items.append(row)

    order_items_df = pd.DataFrame(order_items)
    return order_items_df


def generate_inventory(products_df, regions):
    weekly_dates = pd.date_range(start=START_DATE, end=AS_OF, freq="W-MON")
    inventory_rows = []
    west_product = "P010"
    for snapshot_date in weekly_dates:
        for region in regions:
            for _, product in products_df.iterrows():
                region_factor = {"North": 1.0, "South": 0.96, "East": 0.9, "West": 1.12}[region]
                product_factor = 1.0 + (int(product["product_id"].replace("P", "")) % 5) * 0.08
                stock_on_hand = max(
                    20,
                    int(round(120 * region_factor * product_factor * (1 + 0.15 * np.sin(snapshot_date.dayofyear / 15)))),
                )
                reorder_level = max(25, int(round(stock_on_hand * 0.6)))
                if region == "West" and product["product_id"] == west_product and snapshot_date >= AS_OF - pd.DateOffset(weeks=4):
                    stock_on_hand = max(5, int(reorder_level * 0.7))
                inventory_rows.append(
                    {
                        "snapshot_date": snapshot_date.date(),
                        "region": region,
                        "product_id": product["product_id"],
                        "stock_on_hand": stock_on_hand,
                        "reorder_level": reorder_level,
                    }
                )
    inventory = pd.DataFrame(inventory_rows)
    inventory["snapshot_date"] = pd.to_datetime(inventory["snapshot_date"])
    return inventory


def generate_expenses(regions):
    months = pd.date_range(start=START_DATE, end=AS_OF, freq="MS")
    current_quarter_start = pd.Timestamp(
        year=AS_OF.year,
        month=((AS_OF.month - 1) // 3) * 3 + 1,
        day=1,
    )
    expense_types = ["Logistics", "Payroll", "Marketing", "Facilities"]
    rows = []
    region_multiplier = {"North": 1.02, "South": 0.97, "East": 1.05, "West": 1.18}
    for month in months:
        for region in regions:
            for expense_type in expense_types:
                base = {
                    "Logistics": 42000,
                    "Payroll": 67000,
                    "Marketing": 35000,
                    "Facilities": 28000,
                }[expense_type]
                seasonal = 1 + 0.12 * np.sin((month.month / 12.0) * 2 * np.pi)
                amount = round(base * region_multiplier[region] * seasonal, 2)
                if region == "East" and expense_type == "Marketing" and month >= current_quarter_start:
                    amount *= 1.38
                rows.append(
                    {
                        "month": month.strftime("%Y-%m-01"),
                        "region": region,
                        "expense_type": expense_type,
                        "amount": round(amount, 2),
                    }
                )
    expenses = pd.DataFrame(rows)
    expenses["month"] = pd.to_datetime(expenses["month"])
    return expenses


def generate_targets(regions, categories):
    months = pd.date_range(start=START_DATE, end=AS_OF, freq="MS")
    rows = []
    region_multiplier = {"North": 1.0, "South": 0.92, "East": 0.98, "West": 1.12}
    category_weight = {
        "Packaged Foods": 1.05,
        "Beverages": 0.9,
        "Household": 0.95,
        "Personal Care": 1.1,
    }
    for month in months:
        for region in regions:
            for category in categories:
                seasonal = 1 + 0.22 * np.sin((month.month / 12.0) * 2 * np.pi)
                amount = 92000 * region_multiplier[region] * category_weight[category] * seasonal * (1 + 0.1 * (month.year - 2024))
                rows.append(
                    {
                        "month": month.strftime("%Y-%m-01"),
                        "region": region,
                        "category": category,
                        "revenue_target": round(amount, 2),
                    }
                )
    targets = pd.DataFrame(rows)
    targets["month"] = pd.to_datetime(targets["month"])
    return targets


def write_table(conn, table_name, df):
    df = df.copy()
    conn.register(f"{table_name}_tmp", df)
    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {table_name}_tmp")


def main():
    regions, channels, categories = get_dimension_values()
    products_df = product_catalog(regions, channels, categories)
    customers_df = generate_customers(regions, categories)
    orders_df = generate_orders(customers_df, regions, channels)
    order_items_df = build_order_items(orders_df, products_df)

    merged_items = order_items_df.merge(orders_df[["order_id", "region", "channel", "order_date"]], on="order_id", how="left")
    product_lookup = products_df.set_index("product_id")["category"].to_dict()
    merged_items["category"] = merged_items["product_id"].map(product_lookup)

    current_q_start = pd.Timestamp(year=AS_OF.year, month=((AS_OF.month - 1) // 3) * 3 + 1, day=1)
    current_q_end = AS_OF
    previous_q_start = current_q_start - pd.DateOffset(months=3)
    previous_q_end = current_q_start - pd.Timedelta(days=1)

    south_current_q_mask = (
        (merged_items["region"] == "South")
        & (merged_items["order_date"] >= current_q_start)
        & (merged_items["order_date"] <= current_q_end)
    )
    bev_mask = south_current_q_mask & (merged_items["category"] == "Beverages")
    partner_mask = south_current_q_mask & (merged_items["channel"] == "Partner")

    for region in regions:
        current_mask = (merged_items["region"] == region) & (merged_items["order_date"] >= current_q_start) & (merged_items["order_date"] <= current_q_end)
        previous_mask = (merged_items["region"] == region) & (merged_items["order_date"] >= previous_q_start) & (merged_items["order_date"] <= previous_q_end)
        current_total = merged_items.loc[current_mask, "revenue"].sum()
        previous_total = merged_items.loc[previous_mask, "revenue"].sum()
        if previous_total > 0:
            current_ratio = current_total / previous_total
        else:
            current_ratio = 1.0

        target_ratio = {"North": 1.06, "South": 0.80, "East": 1.05, "West": 1.04}.get(region, 1.0)
        if region == "South":
            scale = target_ratio / current_ratio if current_ratio > 0 else 1.0
            merged_items.loc[current_mask, "revenue"] *= scale
            merged_items.loc[bev_mask, "revenue"] *= (0.65 / 0.80)
            merged_items.loc[partner_mask, "revenue"] *= (0.60 / 0.80)
            merged_items.loc[south_current_q_mask, "cost"] *= 0.82
        else:
            scale = target_ratio / current_ratio if current_ratio > 0 else 1.0
            merged_items.loc[current_mask, "revenue"] *= scale

    promo_product = products_df[products_df["category"] == "Household"]["product_id"].iloc[0]
    promo_start = AS_OF - pd.DateOffset(days=29)
    promo_mask = (merged_items["product_id"] == promo_product) & (merged_items["order_date"] >= promo_start)
    merged_items.loc[promo_mask, "quantity"] = (merged_items.loc[promo_mask, "quantity"] * 1.6).round().astype(int)
    merged_items.loc[promo_mask, "discount_pct"] = (merged_items.loc[promo_mask, "discount_pct"] + 0.08).clip(upper=0.32)
    merged_items.loc[promo_mask, "revenue"] = (
        merged_items.loc[promo_mask, "quantity"] * merged_items.loc[promo_mask, "unit_price"] * (1 - merged_items.loc[promo_mask, "discount_pct"])
    ).round(2)

    inventory_df = generate_inventory(products_df, regions)
    expenses_df = generate_expenses(regions)
    targets_df = generate_targets(regions, categories)

    west_product = products_df[products_df["category"] == "Household"]["product_id"].iloc[0]
    latest_snapshots = inventory_df[inventory_df["snapshot_date"] >= (AS_OF - pd.DateOffset(weeks=4))].copy()
    latest_snapshots["stock_on_hand"] = latest_snapshots["stock_on_hand"].astype(int)
    latest_snapshots_mask = (
        (latest_snapshots["region"] == "West")
        & (latest_snapshots["product_id"] == west_product)
    )
    latest_snapshots.loc[latest_snapshots_mask, "stock_on_hand"] = (latest_snapshots.loc[latest_snapshots_mask, "reorder_level"] * 0.7).astype(int)
    inventory_df.update(latest_snapshots)

    east_marketing = (expenses_df["region"] == "East") & (expenses_df["expense_type"] == "Marketing")
    expenses_df.loc[east_marketing & (expenses_df["month"] >= current_q_start) & (expenses_df["month"] <= current_q_end), "amount"] *= 1.35

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = duckdb.connect(str(DB_PATH))
    conn.execute("CREATE TABLE regions AS SELECT * FROM (SELECT 'North' AS region UNION ALL SELECT 'South' UNION ALL SELECT 'East' UNION ALL SELECT 'West')")
    write_table(conn, "products", products_df)
    write_table(conn, "customers", customers_df)
    write_table(conn, "orders", orders_df)
    write_table(conn, "order_items", merged_items[["order_id", "product_id", "quantity", "unit_price", "discount_pct", "revenue", "cost"]])
    write_table(conn, "inventory", inventory_df)
    write_table(conn, "expenses", expenses_df)
    write_table(conn, "targets", targets_df)
    conn.close()

    print(f"Created database: {DB_PATH}")
    print(f"Products: {len(products_df)}")
    print(f"Customers: {len(customers_df)}")
    print(f"Orders: {len(orders_df)}")
    print(f"Order items: {len(merged_items)}")
    print(f"Inventory snapshots: {len(inventory_df)}")
    print(f"Expenses rows: {len(expenses_df)}")
    print(f"Targets rows: {len(targets_df)}")


if __name__ == "__main__":
    main()
