from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
METADATA_PATH = DATA_DIR / "app_metadata.json"
DB_PATH = DATA_DIR / "business.duckdb"


def load_metadata():
    with METADATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_view_columns(conn, view_name: str):
    try:
        rows = conn.execute(f'SELECT column_name FROM information_schema.columns WHERE table_name = \"{view_name}\"').fetchall()
        return [row[0] for row in rows]
    except Exception:
        try:
            rows = conn.execute(f'PRAGMA table_info(\"{view_name}\")').fetchall()
            return [row[1] for row in rows]
        except Exception:
            return []


def main():
    metadata = load_metadata()
    conn = duckdb.connect(str(DB_PATH))
    failures = []
    total_widgets = 0

    for page in metadata["pages"]:
        for widget in page.get("widgets", []):
            total_widgets += 1
            data_view = widget.get("data_view")
            if not data_view:
                failures.append((page["id"], widget["id"], "missing_data_view"))
                continue

            view_exists = conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ?",
                [data_view],
            ).fetchone()[0]
            if not view_exists:
                failures.append((page["id"], widget["id"], "missing_view"))
                continue

            try:
                row_count = conn.execute(f'SELECT COUNT(*) FROM "{data_view}"').fetchone()[0]
            except Exception:
                failures.append((page["id"], widget["id"], "invalid_view_query"))
                continue

            if row_count <= 0:
                failures.append((page["id"], widget["id"], "empty_view"))
                continue

            columns = set(get_view_columns(conn, data_view))
            for filter_obj in page.get("filters", []):
                filter_name = filter_obj.get("name")
                if not filter_name:
                    continue
                if filter_name not in columns:
                    failures.append((page["id"], widget["id"], f"missing_filter_column:{filter_name}"))

            if page.get("date_range_options"):
                date_ok = any(name in columns for name in ["order_date", "snapshot_date", "month", "signup_date"])
                if not date_ok:
                    failures.append((page["id"], widget["id"], "missing_date_column"))

    print(f"Validated widgets: {total_widgets}")
    print(f"Failures: {len(failures)}")
    if failures:
        print("\nFailure details:")
        for page_id, widget_id, reason in failures:
            print(f"- {page_id} / {widget_id}: {reason}")
        conn.close()
        return 1
    else:
        print("PASS: all widget views validated successfully.")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
