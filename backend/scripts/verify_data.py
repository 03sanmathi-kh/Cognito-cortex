from __future__ import annotations

import duckdb
from datetime import date, timedelta
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from app.timeutil import get_as_of

DB_PATH = BACKEND_ROOT.parent / "data" / "business.duckdb"


def quarter_start(day: date) -> date:
    month = ((day.month - 1) // 3) * 3 + 1
    return date(day.year, month, 1)


def month_add(day: date, months: int) -> date:
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def as_date_str(value):
    return str(value).split(" ")[0]


def main():
    conn = duckdb.connect(str(DB_PATH))
    tables = ["regions", "products", "customers", "orders", "order_items", "inventory", "expenses", "targets"]

    print("Row counts by table:")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"- {table}: {count}")

    print("\nDate ranges:")
    order_range = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    inventory_range = conn.execute("SELECT MIN(snapshot_date), MAX(snapshot_date) FROM inventory").fetchone()
    print(f"- orders: {as_date_str(order_range[0])} to {as_date_str(order_range[1])}")
    print(f"- inventory: {as_date_str(inventory_range[0])} to {as_date_str(inventory_range[1])}")

    as_of = get_as_of()
    current_q_start = quarter_start(as_of)
    last_full_q_start = current_q_start
    last_full_q_end = as_of
    prev_q_start = month_add(last_full_q_start, -3)
    last_q_start_str = last_full_q_start.isoformat()
    prev_q_start_str = prev_q_start.isoformat()
    curr_q_end_exclusive_str = (last_full_q_end + timedelta(days=1)).isoformat()

    total_last_q = conn.execute(
        f"""
        SELECT COALESCE(SUM(oi.revenue), 0)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.region = 'South'
          AND o.order_date >= '{last_q_start_str}'
          AND o.order_date < '{curr_q_end_exclusive_str}'
        """
    ).fetchone()[0]

    total_prev_q = conn.execute(
        f"""
        SELECT COALESCE(SUM(oi.revenue), 0)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.region = 'South'
          AND o.order_date >= '{prev_q_start_str}'
          AND o.order_date < '{last_q_start_str}'
        """
    ).fetchone()[0]

    print("\nSouth revenue latest quarter vs previous quarter:")
    print(f"- latest quarter: ${total_last_q:,.2f}")
    print(f"- previous quarter: ${total_prev_q:,.2f}")
    print(f"- change: {((total_last_q - total_prev_q) / total_prev_q * 100):.2f}%")

    category_query = f"""
        SELECT p.category,
               SUM(oi.revenue) AS revenue
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        JOIN products p ON p.product_id = oi.product_id
        WHERE o.region = 'South'
          AND o.order_date >= '{last_q_start_str}'
          AND o.order_date < '{curr_q_end_exclusive_str}'
        GROUP BY p.category
        ORDER BY revenue DESC
    """
    channel_query = f"""
        SELECT o.channel,
               SUM(oi.revenue) AS revenue
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.region = 'South'
          AND o.order_date >= '{last_q_start_str}'
          AND o.order_date < '{curr_q_end_exclusive_str}'
        GROUP BY o.channel
        ORDER BY revenue DESC
    """

    prev_category_query = f"""
        SELECT p.category,
               SUM(oi.revenue) AS revenue
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        JOIN products p ON p.product_id = oi.product_id
        WHERE o.region = 'South'
          AND o.order_date >= '{prev_q_start_str}'
          AND o.order_date < '{last_q_start_str}'
        GROUP BY p.category
        ORDER BY revenue DESC
    """
    prev_channel_query = f"""
        SELECT o.channel,
               SUM(oi.revenue) AS revenue
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.region = 'South'
          AND o.order_date >= '{prev_q_start_str}'
          AND o.order_date < '{last_q_start_str}'
        GROUP BY o.channel
        ORDER BY revenue DESC
    """

    last_category = {row[0]: row[1] for row in conn.execute(category_query).fetchall()}
    prev_category = {row[0]: row[1] for row in conn.execute(prev_category_query).fetchall()}
    last_channel = {row[0]: row[1] for row in conn.execute(channel_query).fetchall()}
    prev_channel = {row[0]: row[1] for row in conn.execute(prev_channel_query).fetchall()}

    print("\nBy category (South, latest quarter):")
    for category in sorted(last_category):
        old = prev_category.get(category, 0)
        change = ((last_category[category] - old) / old * 100) if old else 0
        print(f"- {category}: ${last_category[category]:,.2f} | change vs previous quarter: {change:.2f}%")

    print("\nBy channel (South, latest quarter):")
    for channel in sorted(last_channel):
        old = prev_channel.get(channel, 0)
        change = ((last_channel[channel] - old) / old * 100) if old else 0
        print(f"- {channel}: ${last_channel[channel]:,.2f} | change vs previous quarter: {change:.2f}%")

    south_drop_pct = (1 - (total_last_q / total_prev_q)) if total_prev_q else 0
    beverage_drop_pct = (1 - (last_category.get("Beverages", 0) / prev_category.get("Beverages", 0))) if prev_category.get("Beverages", 0) else 0
    partner_drop_pct = (1 - (last_channel.get("Partner", 0) / prev_channel.get("Partner", 0))) if prev_channel.get("Partner", 0) else 0

    print("\nStory 1 validation:")
    print(f"- South total revenue drop: {south_drop_pct * 100:.2f}%")
    print(f"- South Beverages drop: {beverage_drop_pct * 100:.2f}%")
    print(f"- South Partner channel drop: {partner_drop_pct * 100:.2f}%")
    ok = 0.15 <= south_drop_pct <= 0.30 and 0.25 <= beverage_drop_pct <= 0.50 and 0.25 <= partner_drop_pct <= 0.60
    print(f"- Expected pattern present: {'YES' if ok else 'NO'}")

    # Additional region sanity check for the same period
    region_query = f"""
        SELECT o.region,
               SUM(oi.revenue) AS revenue
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.order_date >= '{last_q_start_str}'
          AND o.order_date < '{curr_q_end_exclusive_str}'
        GROUP BY o.region
        ORDER BY revenue DESC
    """
    prev_region_query = f"""
        SELECT o.region,
               SUM(oi.revenue) AS revenue
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.order_date >= '{prev_q_start_str}'
          AND o.order_date < '{last_q_start_str}'
        GROUP BY o.region
        ORDER BY revenue DESC
    """
    region_last = {row[0]: row[1] for row in conn.execute(region_query).fetchall()}
    region_prev = {row[0]: row[1] for row in conn.execute(prev_region_query).fetchall()}
    print("\nLatest-quarter region revenue snapshot:")
    for region in sorted(region_last):
        old = region_prev.get(region, 0)
        change = ((region_last[region] - old) / old * 100) if old else 0
        print(f"- {region}: {change:.2f}% vs previous quarter")

    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
