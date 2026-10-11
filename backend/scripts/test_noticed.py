from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from main import app
from app.apps import select_app


def test_noticed_endpoint() -> bool:
    client = TestClient(app)

    # 1. Test sales app (meridian)
    select_app("meridian")
    res_sales = client.get("/api/noticed")
    if res_sales.status_code != 200:
        print(f"FAIL: sales /api/noticed returned status {res_sales.status_code}")
        return False

    data_sales = res_sales.json()
    sales_metric_ok = data_sales.get("metric") == "revenue"
    sales_segment_ok = str(data_sales.get("segment")).lower() == "south"
    sales_drop_ok = data_sales.get("direction") == "drop" or (data_sales.get("percent_change") or 0) < 0
    sales_fmt_ok = bool(data_sales.get("formatted_change") and data_sales.get("formatted_pct_change"))

    if not (sales_metric_ok and sales_segment_ok and sales_drop_ok and sales_fmt_ok):
        print(f"FAIL: Sales app noticed mismatch: {data_sales}")
        return False
    print(f"PASS: Sales app noticed South revenue drop: {data_sales.get('headline')}, change={data_sales.get('formatted_change')}")

    # 2. Test clinic app
    client.post("/api/apps/select", json={"app_id": "clinic"})
    res_clinic = client.get("/api/noticed")
    if res_clinic.status_code != 200:
        print(f"FAIL: clinic /api/noticed returned status {res_clinic.status_code}")
        select_app("meridian")
        return False

    data_clinic = res_clinic.json()
    clinic_metric_ok = data_clinic.get("metric") == "appointments"
    clinic_segment_ok = str(data_clinic.get("segment")).lower() == "orthopedics"
    clinic_drop_ok = data_clinic.get("direction") == "drop" or (data_clinic.get("percent_change") or 0) < 0
    clinic_fmt_ok = bool(data_clinic.get("formatted_change") and data_clinic.get("formatted_pct_change"))

    # Restore meridian
    client.post("/api/apps/select", json={"app_id": "meridian"})

    if not (clinic_metric_ok and clinic_segment_ok and clinic_drop_ok and clinic_fmt_ok):
        print(f"FAIL: Clinic app noticed mismatch: {data_clinic}")
        return False
    print(f"PASS: Clinic app noticed Orthopedics appointments drop: {data_clinic.get('headline')}, change={data_clinic.get('formatted_change')}")

    return True


if __name__ == "__main__":
    passed = test_noticed_endpoint()
    if passed:
        print("ALL NOTICED TESTS PASSED")
        sys.exit(0)
    else:
        print("NOTICED TESTS FAILED")
        sys.exit(1)
