import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_rate_guard_and_velocity():
    # 1. Test Period Velocity Rate
    res = client.get("/api/widget-data?page_id=regional_sales_trend&widget_id=kpi_trend_velocity&date_range=this_quarter")
    assert res.status_code == 200, res.text
    rows = res.json()["rows"]
    assert len(rows) == 1
    val = rows[0]["value"]
    # Should be sane percentage (11.99%), not raw quantity (67373)
    assert 0 <= val <= 100, f"Expected sane velocity rate, got {val}"
    print(f"PASS: Period Velocity Rate is sane: {val}%")

    # 2. Test Top SKU revenue neighbour
    res_sku = client.get("/api/widget-data?page_id=revenue_by_region_and_product&widget_id=kpi_top_sku_region&date_range=this_quarter")
    assert res_sku.status_code == 200, res_sku.text
    sku_rows = res_sku.json()["rows"]
    chg = sku_rows[0]["change_pct"]
    # Should compare to previous top SKU, not all SKUs (-85.8%)
    assert chg > -50, f"Expected sane top SKU change, got {chg}"
    print(f"PASS: Top Regional SKU change is sane: {chg}%")

def test_noticed_insights():
    res = client.get("/api/noticed")
    assert res.status_code == 200
    data = res.json()
    insights = data.get("insights", [])
    assert 1 <= len(insights) <= 5
    for item in insights:
        assert "title" in item and "question" in item
    print(f"PASS: Noticed insights returned {len(insights)} items")

if __name__ == "__main__":
    test_rate_guard_and_velocity()
    test_noticed_insights()
    print("ALL UI FIX TESTS PASS")
