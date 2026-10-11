from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
CLINIC_DIR = ROOT / "data" / "apps" / "clinic"
CLINIC_DIR.mkdir(parents=True, exist_ok=True)

# Fixed as-of date: 2026-09-30
AS_OF = date(2026, 9, 30)
START_DATE = date(2025, 10, 1)  # 12 months of rows

DEPARTMENTS = ["Cardiology", "Dermatology", "Pediatrics", "Orthopedics", "General Medicine"]
DOCTORS = {
    "Cardiology": "Dr. Sharma",
    "Dermatology": "Dr. Rao",
    "Pediatrics": "Dr. Patel",
    "Orthopedics": "Dr. Mehta",
    "General Medicine": "Dr. Nair",
}
DOCTOR_NAMES = list(DOCTORS.values())
STATUSES = ["Completed", "Cancelled", "No-Show"]
VISIT_TYPES = ["New", "Follow-up", "Emergency"]
AGE_GROUPS = ["Child", "Adult", "Senior"]

FEES = {
    "Cardiology": 200.0,
    "Dermatology": 150.0,
    "Pediatrics": 120.0,
    "Orthopedics": 180.0,
    "General Medicine": 100.0,
}


def generate_database() -> None:
    db_path = CLINIC_DIR / "clinic.duckdb"
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    con.execute("""
        CREATE TABLE appointments (
            appointment_id VARCHAR PRIMARY KEY,
            appointment_date DATE,
            department VARCHAR,
            doctor VARCHAR,
            status VARCHAR,
            visit_type VARCHAR,
            patient_type VARCHAR,
            age_group VARCHAR,
            fee DOUBLE,
            wait_minutes INTEGER
        )
    """)

    random.seed(42)
    records = []
    app_counter = 1000

    # Date ranges:
    # Q2: 2026-04-01 to 2026-06-30
    # Q3: 2026-07-01 to 2026-09-30
    q2_start = date(2026, 4, 1)
    q2_end = date(2026, 6, 30)
    q3_start = date(2026, 7, 1)
    q3_end = date(2026, 9, 30)

    # 1. Generate regular baseline appointments for all dates (for other departments and non-Q2/Q3 Ortho)
    current = START_DATE
    while current <= AS_OF:
        is_q2 = q2_start <= current <= q2_end
        is_q3 = q3_start <= current <= q3_end

        # Non-ortho departments
        for dept in ["Cardiology", "Dermatology", "Pediatrics", "General Medicine"]:
            # 2 to 4 appointments per dept per day
            daily_count = random.randint(2, 4)
            for _ in range(daily_count):
                app_counter += 1
                doc = DOCTORS[dept]
                status_weights = [0.75, 0.15, 0.10]
                status = random.choices(STATUSES, weights=status_weights)[0]
                v_type = random.choices(VISIT_TYPES, weights=[0.4, 0.5, 0.1])[0]
                if dept == "Pediatrics":
                    age = random.choices(AGE_GROUPS, weights=[0.85, 0.12, 0.03])[0]
                else:
                    age = random.choices(AGE_GROUPS, weights=[0.1, 0.6, 0.3])[0]
                fee = FEES[dept]
                wait = random.randint(10, 35) if status == "Completed" else random.randint(5, 15)
                records.append((
                    f"APT-{app_counter}",
                    current.isoformat(),
                    dept,
                    doc,
                    status,
                    v_type,
                    v_type,
                    age,
                    fee,
                    wait,
                ))

        # Orthopedics outside Q2 and Q3
        if not is_q2 and not is_q3:
            daily_count = random.randint(1, 2)
            for _ in range(daily_count):
                app_counter += 1
                dept = "Orthopedics"
                doc = DOCTORS[dept]
                status = random.choices(STATUSES, weights=[0.75, 0.15, 0.10])[0]
                v_type = random.choices(VISIT_TYPES, weights=[0.35, 0.50, 0.15])[0]
                age = random.choices(AGE_GROUPS, weights=[0.15, 0.55, 0.30])[0]
                fee = FEES[dept]
                wait = random.randint(12, 40) if status == "Completed" else random.randint(5, 15)
                records.append((
                    f"APT-{app_counter}",
                    current.isoformat(),
                    dept,
                    doc,
                    status,
                    v_type,
                    v_type,
                    age,
                    fee,
                    wait,
                ))

        current += timedelta(days=1)

    # 2. Plant the exact story for Orthopedics in Q2 and Q3:
    # Q2: Exactly 110 appointments
    # - Follow-up: 60 (48 Completed, 7 Cancelled, 5 No-Show)
    # - New: 35 (30 Completed, 3 Cancelled, 2 No-Show)
    # - Emergency: 15 (13 Completed, 1 Cancelled, 1 No-Show)
    # Age groups: Adult: 55, Senior: 35, Child: 20
    q2_ortho_items = []
    for _ in range(48):
        q2_ortho_items.append(("Follow-up", "Completed"))
    for _ in range(7):
        q2_ortho_items.append(("Follow-up", "Cancelled"))
    for _ in range(5):
        q2_ortho_items.append(("Follow-up", "No-Show"))
    for _ in range(30):
        q2_ortho_items.append(("New", "Completed"))
    for _ in range(3):
        q2_ortho_items.append(("New", "Cancelled"))
    for _ in range(2):
        q2_ortho_items.append(("New", "No-Show"))
    for _ in range(13):
        q2_ortho_items.append(("Emergency", "Completed"))
    for _ in range(1):
        q2_ortho_items.append(("Emergency", "Cancelled"))
    for _ in range(1):
        q2_ortho_items.append(("Emergency", "No-Show"))

    # Exactly 110 items
    assert len(q2_ortho_items) == 110

    q2_ages = ["Adult"] * 55 + ["Senior"] * 35 + ["Child"] * 20
    random.seed(101)
    random.shuffle(q2_ortho_items)
    random.shuffle(q2_ages)

    # Spread over Q2 days (91 days: 2026-04-01 to 2026-06-30)
    q2_days = [(q2_start + timedelta(days=i)) for i in range((q2_end - q2_start).days + 1)]
    for idx, (v_type, status) in enumerate(q2_ortho_items):
        app_counter += 1
        apt_date = q2_days[idx % len(q2_days)]
        age = q2_ages[idx]
        fee = FEES["Orthopedics"]
        wait = random.randint(12, 35) if status == "Completed" else random.randint(5, 15)
        records.append((
            f"APT-{app_counter}",
            apt_date.isoformat(),
            "Orthopedics",
            DOCTORS["Orthopedics"],
            status,
            v_type,
            v_type,
            age,
            fee,
            wait,
        ))

    # Q3: Exactly 88 appointments (-20.0% vs Q2 110)
    # - Follow-up: 38 (10 Completed, 16 Cancelled, 12 No-Show) -> severe drop in completed, rise in cancellations & no-shows!
    # - New: 35 (30 Completed, 3 Cancelled, 2 No-Show)
    # - Emergency: 15 (13 Completed, 1 Cancelled, 1 No-Show)
    # Age groups: Adult: 44, Senior: 28, Child: 16 (-20% uniformly)
    q3_ortho_items = []
    for _ in range(10):
        q3_ortho_items.append(("Follow-up", "Completed"))
    for _ in range(16):
        q3_ortho_items.append(("Follow-up", "Cancelled"))
    for _ in range(12):
        q3_ortho_items.append(("Follow-up", "No-Show"))
    for _ in range(30):
        q3_ortho_items.append(("New", "Completed"))
    for _ in range(3):
        q3_ortho_items.append(("New", "Cancelled"))
    for _ in range(2):
        q3_ortho_items.append(("New", "No-Show"))
    for _ in range(13):
        q3_ortho_items.append(("Emergency", "Completed"))
    for _ in range(1):
        q3_ortho_items.append(("Emergency", "Cancelled"))
    for _ in range(1):
        q3_ortho_items.append(("Emergency", "No-Show"))

    # Exactly 88 items
    assert len(q3_ortho_items) == 88

    q3_ages = ["Adult"] * 44 + ["Senior"] * 28 + ["Child"] * 16
    random.seed(202)
    random.shuffle(q3_ortho_items)
    random.shuffle(q3_ages)

    # Spread over Q3 days (92 days: 2026-07-01 to 2026-09-30)
    q3_days = [(q3_start + timedelta(days=i)) for i in range((q3_end - q3_start).days + 1)]
    for idx, (v_type, status) in enumerate(q3_ortho_items):
        app_counter += 1
        apt_date = q3_days[idx % len(q3_days)]
        age = q3_ages[idx]
        fee = FEES["Orthopedics"]
        wait = random.randint(12, 35) if status == "Completed" else random.randint(5, 15)
        records.append((
            f"APT-{app_counter}",
            apt_date.isoformat(),
            "Orthopedics",
            DOCTORS["Orthopedics"],
            status,
            v_type,
            v_type,
            age,
            fee,
            wait,
        ))

    con.executemany("INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", records)

    # Base views for widgets
    con.execute("CREATE VIEW v_appointments AS SELECT * FROM appointments")
    con.close()
    print(f"Generated clinic.duckdb with {len(records)} records at {db_path}")


def generate_metadata() -> None:
    metadata = {
        "app": {
            "id": "clinic",
            "name": "Clinic Appointments",
            "description": "Clinic appointments, patient flow, and schedule management",
            "currency": "USD"
        },
        "as_of": "2026-09-30",
        "roles": [
            {"id": "admin", "display_name": "Clinic Administrator"},
            {"id": "doctor", "display_name": "Physician"},
            {"id": "receptionist", "display_name": "Front Desk"}
        ],
        "dimensions": {
            "date_range": {"start": "2025-10-01", "end": "2026-09-30"},
            "departments": DEPARTMENTS,
            "doctors": DOCTOR_NAMES,
            "statuses": STATUSES,
            "visit_types": VISIT_TYPES,
            "age_groups": AGE_GROUPS
        },
        "directories": [
            {
                "id": "overview",
                "title": "Overview",
                "subdirectories": [
                    {"id": "general", "title": "General"}
                ]
            },
            {
                "id": "departments",
                "title": "Departments",
                "subdirectories": [
                    {"id": "clinical", "title": "Clinical"}
                ]
            },
            {
                "id": "operations",
                "title": "Operations",
                "subdirectories": [
                    {"id": "performance", "title": "Performance"}
                ]
            }
        ],
        "pages": [
            # Section 1: Overview (5 pages)
            {
                "id": "clinic_overview",
                "title": "Clinic Overview",
                "route": "/clinic/overview",
                "directory": "overview",
                "subdirectory": "general",
                "description": "Executive summary of clinic appointments, completion rates, and operational throughput.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "status", "label": "Status", "type": "single_select", "allowed_values": STATUSES, "default": None},
                    {"name": "visit_type", "label": "Visit Type", "type": "single_select", "allowed_values": VISIT_TYPES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"},
                    {"field": "fee", "direction": "desc", "label": "Fee (Highest)"}
                ],
                "widgets": [
                    {"id": "kpi_total_appointments", "title": "Total Appointments", "type": "kpi", "measures": ["appointments"]},
                    {"id": "bar_dept_distribution", "title": "Appointments by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_appointments_ledger", "title": "Recent Appointments Ledger", "type": "grid", "columns": ["appointment_date", "department", "doctor", "visit_type", "status", "fee"]}
                ]
            },
            {
                "id": "appointments_trend",
                "title": "Appointments Trend",
                "route": "/clinic/appointments-trend",
                "directory": "overview",
                "subdirectory": "general",
                "description": "Longitudinal volume trends of clinic appointments over daily and monthly intervals.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_year",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "visit_type", "label": "Visit Type", "type": "single_select", "allowed_values": VISIT_TYPES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "asc", "label": "Date (Chronological)"}
                ],
                "widgets": [
                    {"id": "line_daily_appointments", "title": "Appointment Volume Over Time", "type": "line_chart", "columns": ["appointment_date", "fee"]},
                    {"id": "bar_monthly_trend", "title": "Monthly Appointment Trend", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_trend_details", "title": "Appointment Timeline Records", "type": "grid", "columns": ["appointment_date", "department", "doctor", "status"]}
                ]
            },
            {
                "id": "status_breakdown",
                "title": "Status Breakdown",
                "route": "/clinic/status-breakdown",
                "directory": "overview",
                "subdirectory": "general",
                "description": "Comprehensive breakdown of completed, cancelled, and no-show consultations.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "status", "label": "Status", "type": "single_select", "allowed_values": STATUSES, "default": None},
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "pie_status_split", "title": "Appointment Status Distribution", "type": "pie_chart", "columns": ["status", "fee"]},
                    {"id": "bar_status_by_dept", "title": "Status by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_status_log", "title": "Status Resolution Log", "type": "grid", "columns": ["appointment_date", "doctor", "status", "visit_type"]}
                ]
            },
            {
                "id": "no_show_analysis",
                "title": "No-show Analysis",
                "route": "/clinic/no-show-analysis",
                "directory": "overview",
                "subdirectory": "general",
                "description": "Patient absenteeism metrics, no-show rate indicators, and impact on clinic capacity.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "doctor", "label": "Doctor", "type": "single_select", "allowed_values": DOCTOR_NAMES, "default": None},
                    {"name": "visit_type", "label": "Visit Type", "type": "single_select", "allowed_values": VISIT_TYPES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "kpi_no_show_rate", "title": "No-show Rate", "type": "kpi", "measures": ["no_show_rate"]},
                    {"id": "bar_noshow_by_dept", "title": "No-shows by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_noshow_records", "title": "No-show Incidents", "type": "grid", "columns": ["appointment_date", "department", "doctor", "visit_type", "age_group"]}
                ]
            },
            {
                "id": "cancellations_page",
                "title": "Cancellations",
                "route": "/clinic/cancellations",
                "directory": "overview",
                "subdirectory": "general",
                "description": "Patient cancellation tracking, notice lead time, and departmental cancellation rates.",
                "allowed_roles": ["admin", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "visit_type", "label": "Visit Type", "type": "single_select", "allowed_values": VISIT_TYPES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "kpi_cancellation_rate", "title": "Cancellation Rate", "type": "kpi", "measures": ["cancellation_rate"]},
                    {"id": "bar_cancellations_by_dept", "title": "Cancellations by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_cancelled_appointments", "title": "Cancelled Appointments Ledger", "type": "grid", "columns": ["appointment_date", "department", "doctor", "visit_type", "fee"]}
                ]
            },

            # Section 2: Departments (5 pages)
            {
                "id": "appointments_by_department",
                "title": "Appointments by Department",
                "route": "/clinic/by-department",
                "directory": "departments",
                "subdirectory": "clinical",
                "description": "Comparative consultation count, scheduling density, and intake volume by department.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "bar_dept_appointments_count", "title": "Volume by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "pie_dept_share_all", "title": "Department Intake Share", "type": "pie_chart", "columns": ["department", "fee"]},
                    {"id": "grid_dept_appointments_list", "title": "Department Appointments", "type": "grid", "columns": ["appointment_date", "department", "doctor", "status"]}
                ]
            },
            {
                "id": "appointments_by_doctor",
                "title": "Appointments by Doctor",
                "route": "/clinic/by-doctor",
                "directory": "departments",
                "subdirectory": "clinical",
                "description": "Physician consultation volume, patient load, and appointment assignments.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "doctor", "label": "Doctor", "type": "single_select", "allowed_values": DOCTOR_NAMES, "default": None},
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "bar_doctor_patient_count", "title": "Appointments per Physician", "type": "bar_chart", "columns": ["doctor", "fee"]},
                    {"id": "pie_doctor_share", "title": "Physician Volume Share", "type": "pie_chart", "columns": ["doctor", "fee"]},
                    {"id": "grid_doctor_appointments", "title": "Physician Appointments Roster", "type": "grid", "columns": ["appointment_date", "doctor", "department", "visit_type", "status"]}
                ]
            },
            {
                "id": "doctor_workload",
                "title": "Doctor Workload",
                "route": "/clinic/doctor-workload",
                "directory": "departments",
                "subdirectory": "clinical",
                "description": "Physician clinical burden, completed consult hours, and caseload balance.",
                "allowed_roles": ["admin", "doctor"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "doctor", "label": "Doctor", "type": "single_select", "allowed_values": DOCTOR_NAMES, "default": None}
                ],
                "sort_options": [
                    {"field": "wait_minutes", "direction": "desc", "label": "Wait Minutes (Highest)"}
                ],
                "widgets": [
                    {"id": "bar_doctor_workload_consults", "title": "Consultations by Doctor", "type": "bar_chart", "columns": ["doctor", "fee"]},
                    {"id": "grid_doctor_workload_table", "title": "Physician Caseload Details", "type": "grid", "columns": ["doctor", "appointment_date", "visit_type", "status", "wait_minutes"]}
                ]
            },
            {
                "id": "department_comparison",
                "title": "Department Comparison",
                "route": "/clinic/department-comparison",
                "directory": "departments",
                "subdirectory": "clinical",
                "description": "Multi-department operational comparison across volume, cancellations, and waiting duration.",
                "allowed_roles": ["admin", "doctor"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "status", "label": "Status", "type": "single_select", "allowed_values": STATUSES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "bar_dept_compare_vol", "title": "Department Relative Volume", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "pie_dept_compare_share", "title": "Intake Share Comparison", "type": "pie_chart", "columns": ["department", "fee"]},
                    {"id": "grid_dept_comparison_summary", "title": "Comparative Department Roster", "type": "grid", "columns": ["department", "doctor", "status", "fee", "wait_minutes"]}
                ]
            },
            {
                "id": "daily_schedule",
                "title": "Daily Schedule",
                "route": "/clinic/daily-schedule",
                "directory": "departments",
                "subdirectory": "clinical",
                "description": "Real-time daily appointment queue, room assignments, and patient check-in status.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "doctor", "label": "Doctor", "type": "single_select", "allowed_values": DOCTOR_NAMES, "default": None},
                    {"name": "status", "label": "Status", "type": "single_select", "allowed_values": STATUSES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "asc", "label": "Date (Earliest)"}
                ],
                "widgets": [
                    {"id": "bar_schedule_by_dept", "title": "Daily Schedule by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_daily_schedule_queue", "title": "Daily Patient Queue", "type": "grid", "columns": ["appointment_id", "appointment_date", "doctor", "department", "status", "wait_minutes"]}
                ]
            },

            # Section 3: Operations (5 pages)
            {
                "id": "visit_types_page",
                "title": "Visit Types",
                "route": "/clinic/visit-types",
                "directory": "operations",
                "subdirectory": "performance",
                "description": "Analysis of appointment categories: New patient intake, Follow-up consultations, and Emergency cases.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "visit_type", "label": "Visit Type", "type": "single_select", "allowed_values": VISIT_TYPES, "default": None},
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "pie_visittype_split", "title": "Visit Type Distribution", "type": "pie_chart", "columns": ["visit_type", "fee"]},
                    {"id": "bar_visittype_by_dept", "title": "Visit Types across Departments", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_visittype_records", "title": "Visit Type Ledger", "type": "grid", "columns": ["appointment_date", "visit_type", "department", "doctor", "status"]}
                ]
            },
            {
                "id": "age_groups_page",
                "title": "Age Groups",
                "route": "/clinic/age-groups",
                "directory": "operations",
                "subdirectory": "performance",
                "description": "Demographic breakdown across pediatric (Child), adult, and geriatric (Senior) patient populations.",
                "allowed_roles": ["admin", "doctor"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "age_group", "label": "Age Group", "type": "single_select", "allowed_values": AGE_GROUPS, "default": None},
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "pie_agegroup_distribution", "title": "Patient Demographics by Age Group", "type": "pie_chart", "columns": ["age_group", "fee"]},
                    {"id": "bar_agegroup_dept", "title": "Age Group by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_agegroup_records", "title": "Demographic Intake Records", "type": "grid", "columns": ["appointment_date", "age_group", "department", "visit_type", "doctor"]}
                ]
            },
            {
                "id": "wait_times_page",
                "title": "Wait Times",
                "route": "/clinic/wait-times",
                "directory": "operations",
                "subdirectory": "performance",
                "description": "Patient waiting room duration metrics, clinic throughput efficiency, and service delays.",
                "allowed_roles": ["admin", "receptionist", "doctor"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "doctor", "label": "Doctor", "type": "single_select", "allowed_values": DOCTOR_NAMES, "default": None}
                ],
                "sort_options": [
                    {"field": "wait_minutes", "direction": "desc", "label": "Wait Minutes (Longest)"}
                ],
                "widgets": [
                    {"id": "kpi_avg_wait_time", "title": "Average Wait Time (Minutes)", "type": "kpi", "measures": ["avg_wait_minutes"]},
                    {"id": "bar_waittime_dept", "title": "Wait Times by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_waittime_ledger", "title": "Wait Time Audit Log", "type": "grid", "columns": ["appointment_date", "department", "doctor", "wait_minutes", "status"]}
                ]
            },
            {
                "id": "fee_collection_page",
                "title": "Fee Collection",
                "route": "/clinic/fee-collection",
                "directory": "operations",
                "subdirectory": "performance",
                "description": "Consultation fee collection tracking, payment status, and financial receipts by clinical department.",
                "allowed_roles": ["admin"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "visit_type", "label": "Visit Type", "type": "single_select", "allowed_values": VISIT_TYPES, "default": None}
                ],
                "sort_options": [
                    {"field": "fee", "direction": "desc", "label": "Fee (Highest)"}
                ],
                "widgets": [
                    {"id": "kpi_fee_collected", "title": "Total Fees Collected", "type": "kpi", "measures": ["fee_collected"]},
                    {"id": "bar_fee_by_dept", "title": "Fee Collections by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "grid_fee_collection_log", "title": "Fee Receipts Ledger", "type": "grid", "columns": ["appointment_date", "department", "doctor", "fee", "status"]}
                ]
            },
            {
                "id": "followup_tracker",
                "title": "Follow-up Tracker",
                "route": "/clinic/followup-tracker",
                "directory": "operations",
                "subdirectory": "performance",
                "description": "Care continuity monitor for patient follow-up appointments, retention rates, and re-attendance.",
                "allowed_roles": ["admin", "doctor", "receptionist"],
                "default_date_range": "this_quarter",
                "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
                "filters": [
                    {"name": "department", "label": "Department", "type": "single_select", "allowed_values": DEPARTMENTS, "default": None},
                    {"name": "doctor", "label": "Doctor", "type": "single_select", "allowed_values": DOCTOR_NAMES, "default": None},
                    {"name": "status", "label": "Status", "type": "single_select", "allowed_values": STATUSES, "default": None}
                ],
                "sort_options": [
                    {"field": "appointment_date", "direction": "desc", "label": "Date (Newest)"}
                ],
                "widgets": [
                    {"id": "bar_followup_departments", "title": "Follow-ups by Department", "type": "bar_chart", "columns": ["department", "fee"]},
                    {"id": "pie_followup_status", "title": "Follow-up Status Resolution", "type": "pie_chart", "columns": ["status", "fee"]},
                    {"id": "grid_followup_patients", "title": "Follow-up Patient Queue", "type": "grid", "columns": ["appointment_date", "department", "doctor", "status", "age_group"]}
                ]
            }
        ]
    }

    meta_path = CLINIC_DIR / "app_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated clinic metadata with {len(metadata['pages'])} pages at {meta_path}")


def generate_views_manifest() -> None:
    meta_path = CLINIC_DIR / "app_metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    views = []
    for page in meta["pages"]:
        page_id = page["id"]
        for widget in page["widgets"]:
            widget_id = widget["id"]
            views.append({
                "page_id": page_id,
                "widget_id": widget_id,
                "data_view": "v_appointments",
                "date_column": "appointment_date",
                "columns": [
                    "appointment_id",
                    "appointment_date",
                    "department",
                    "doctor",
                    "status",
                    "visit_type",
                    "patient_type",
                    "age_group",
                    "fee",
                    "wait_minutes",
                ]
            })

    views_path = CLINIC_DIR / "views_manifest.json"
    views_path.write_text(json.dumps(views, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated clinic views manifest with {len(views)} widgets at {views_path}")


def generate_analysis_catalog() -> None:
    catalog = {
        "metrics": [
            {
                "id": "appointments",
                "label": "Appointments",
                "description": "Total number of scheduled and completed clinic appointments.",
                "base_table": "appointments",
                "date_column": "appointment_date",
                "sql_expression": "COUNT(*)",
                "format": "count",
                "home_page": "clinic_overview",
                "page_ids": ["clinic_overview", "appointments_trend", "appointments_by_department"]
            },
            {
                "id": "no_show_rate",
                "label": "No-show Rate",
                "description": "Percentage of appointments where the patient did not attend.",
                "base_table": "appointments",
                "date_column": "appointment_date",
                "sql_expression": "ROUND(100.0 * COUNT(CASE WHEN status = 'No-Show' THEN 1 END) / NULLIF(COUNT(*), 0), 1)",
                "format": "percent",
                "home_page": "no_show_analysis",
                "page_ids": ["no_show_analysis", "status_breakdown"]
            },
            {
                "id": "cancellation_rate",
                "label": "Cancellation Rate",
                "description": "Percentage of clinic appointments cancelled.",
                "base_table": "appointments",
                "date_column": "appointment_date",
                "sql_expression": "ROUND(100.0 * COUNT(CASE WHEN status = 'Cancelled' THEN 1 END) / NULLIF(COUNT(*), 0), 1)",
                "format": "percent",
                "home_page": "cancellations_page",
                "page_ids": ["cancellations_page", "status_breakdown"]
            },
            {
                "id": "avg_wait_minutes",
                "label": "Average Wait Minutes",
                "description": "Average patient wait time in minutes.",
                "base_table": "appointments",
                "date_column": "appointment_date",
                "sql_expression": "ROUND(AVG(wait_minutes), 1)",
                "format": "count",
                "home_page": "wait_times_page",
                "page_ids": ["wait_times_page"]
            },
            {
                "id": "fee_collected",
                "label": "Fee Collected",
                "description": "Total fees collected from completed appointments.",
                "base_table": "appointments",
                "date_column": "appointment_date",
                "sql_expression": "SUM(CASE WHEN status = 'Completed' THEN fee ELSE 0.0 END)",
                "format": "currency",
                "home_page": "fee_collection_page",
                "page_ids": ["fee_collection_page"]
            }
        ],
        "dimensions": [
            {
                "id": "department",
                "label": "Department",
                "column": "department",
                "table": "appointments",
                "description": "Clinical department"
            },
            {
                "id": "doctor",
                "label": "Doctor",
                "column": "doctor",
                "table": "appointments",
                "description": "Consulting doctor"
            },
            {
                "id": "status",
                "label": "Status",
                "column": "status",
                "table": "appointments",
                "description": "Appointment status"
            },
            {
                "id": "visit_type",
                "label": "Visit Type",
                "column": "visit_type",
                "table": "appointments",
                "description": "Visit category (New, Follow-up, Emergency)"
            },
            {
                "id": "age_group",
                "label": "Age Group",
                "column": "age_group",
                "table": "appointments",
                "description": "Patient age bracket (Child, Adult, Senior)"
            }
        ]
    }
    cat_path = CLINIC_DIR / "analysis_catalog.json"
    cat_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated clinic analysis catalog with {len(catalog['metrics'])} metrics and {len(catalog['dimensions'])} dimensions at {cat_path}")


if __name__ == "__main__":
    generate_database()
    generate_metadata()
    generate_views_manifest()
    generate_analysis_catalog()
