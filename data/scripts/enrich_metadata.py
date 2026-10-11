from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "app_metadata.json"
DB_PATH = ROOT / "business.duckdb"

NEW_DIRECTORIES = [
    {
        "id": "customers",
        "title": "Customers",
        "icon": "Users",
        "subdirectories": [
            {"id": "segments", "title": "Segments"},
            {"id": "retention", "title": "Retention"},
        ],
    },
    {
        "id": "inventory",
        "title": "Inventory",
        "icon": "Boxes",
        "subdirectories": [
            {"id": "stock", "title": "Stock"},
            {"id": "suppliers", "title": "Suppliers"},
        ],
    },
    {
        "id": "admin",
        "title": "Admin",
        "icon": "ShieldCheck",
        "subdirectories": [
            {"id": "users", "title": "Users"},
            {"id": "audit", "title": "Audit"},
        ],
    },
]


def widget(page_id: str, widget_id: str, kind: str, title: str, *, measures=None, columns=None):
    payload = {
        "id": widget_id,
        "type": kind,
        "title": title,
        "data_view": f"v_{page_id}_{widget_id}",
    }
    if measures:
        payload["measures"] = measures
    if columns:
        payload["columns"] = columns
    return payload


NEW_PAGES = [
    {
        "id": "customer_segments_overview",
        "title": "Customer Segments Overview",
        "description": "Evaluate customer distribution across acquisition and lifecycle segments to tune targeting strategy and retention investments.",
        "directory": "customers",
        "subdirectory": "segments",
        "route": "/customers/segments/customer-segments-overview",
        "keywords": ["customer mix", "segment distribution", "audience portfolio", "customer groups", "segment share"],
        "widgets": [
            widget("customer_segments_overview", "kpi_total_customers", "kpi", "Total Active Customers", measures=["active_customers", "customer_growth_pct"]),
            widget("customer_segments_overview", "chart_segment_mix", "pie_chart", "Segment Mix", measures=["segment_share_pct"], columns=["segment"]),
            widget("customer_segments_overview", "grid_segment_table", "grid", "Customer Segment Details", columns=["segment", "customer_count", "avg_order_value", "retention_pct"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": None},
        ],
        "date_range_options": ["last_30_days", "this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "customer_count", "label": "Customers (Desc)"},
            {"field": "segment", "label": "Segment Name"},
        ],
        "default_sort": {"field": "customer_count", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "customer_revenue_by_segment",
        "title": "Customer Revenue by Segment",
        "description": "Compare gross revenue contribution by customer segment to identify the highest-value customers and the most promising growth cohorts.",
        "directory": "customers",
        "subdirectory": "segments",
        "route": "/customers/segments/customer-revenue-by-segment",
        "keywords": ["segment revenue", "customer value", "high-value customers", "segment sales", "revenue by audience", "total customer contribution"],
        "widgets": [
            widget("customer_revenue_by_segment", "kpi_segment_revenue", "kpi", "Segment Revenue Total", measures=["revenue_total", "revenue_growth_pct"]),
            widget("customer_revenue_by_segment", "chart_segment_revenue", "bar_chart", "Segment Revenue by Region", measures=["revenue"], columns=["segment", "region"]),
            widget("customer_revenue_by_segment", "grid_segment_summary", "grid", "Segment Revenue Details", columns=["segment", "customer_count", "gross_revenue", "avg_order_value"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["last_30_days", "this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "gross_revenue", "label": "Revenue (Desc)"},
            {"field": "segment", "label": "Segment Name"},
        ],
        "default_sort": {"field": "gross_revenue", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "customer_retention_trend",
        "title": "Customer Retention Trend",
        "description": "Track retention changes over time and identify the periods where customer loyalty begins to weaken or rebound.",
        "directory": "customers",
        "subdirectory": "retention",
        "route": "/customers/retention/customer-retention-trend",
        "keywords": ["retention trend", "loyalty curve", "customer churn", "renewal trend", "repeat customer health"],
        "widgets": [
            widget("customer_retention_trend", "chart_retention_timeline", "line_chart", "Retention Over Time", measures=["retention_pct"], columns=["date", "segment"]),
            widget("customer_retention_trend", "kpi_retention_rate", "kpi", "Current Retention Rate", measures=["retention_pct", "churn_delta_pct"]),
            widget("customer_retention_trend", "grid_retention_table", "grid", "Retention Metrics by Segment", columns=["segment", "retention_pct", "churn_rate", "repeat_rate"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": None},
        ],
        "date_range_options": ["last_30_days", "this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "retention_pct", "label": "Retention % (Desc)"},
            {"field": "segment", "label": "Segment Name"},
        ],
        "default_sort": {"field": "retention_pct", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "repeat_purchase_rate",
        "title": "Repeat Purchase Rate",
        "description": "Measure the share of customers returning for a second purchase and reveal which segments are driving loyalty growth.",
        "directory": "customers",
        "subdirectory": "retention",
        "route": "/customers/retention/repeat-purchase-rate",
        "keywords": ["repeat purchases", "second order rate", "loyalty rate", "purchase frequency", "repeat customer conversions"],
        "widgets": [
            widget("repeat_purchase_rate", "kpi_repeat_rate", "kpi", "Repeat Purchase Rate", measures=["repeat_purchase_pct", "repeat_growth_pct"]),
            widget("repeat_purchase_rate", "chart_repeat_by_segment", "bar_chart", "Repeat Purchase by Segment", measures=["repeat_purchase_pct"], columns=["segment"]),
            widget("repeat_purchase_rate", "grid_purchase_frequency", "grid", "Purchase Frequency Table", columns=["segment", "customer_count", "repeat_purchase_pct", "avg_orders_per_customer"]),
        ],
        "filters": [
            {"name": "region", "type": "select", "allowed_values": ["North", "South", "East", "West"], "default": "North"},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": "Online"},
        ],
        "date_range_options": ["last_30_days", "this_month", "last_month", "this_quarter", "last_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "repeat_purchase_pct", "label": "Repeat Rate (Desc)"},
            {"field": "customer_count", "label": "Customers (Desc)"},
        ],
        "default_sort": {"field": "repeat_purchase_pct", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "churn_risk_by_region",
        "title": "Churn Risk by Region",
        "description": "Find geographic pockets with rising churn risk so customer success teams can target retention interventions earlier.",
        "directory": "customers",
        "subdirectory": "retention",
        "route": "/customers/retention/churn-risk-by-region",
        "keywords": ["at-risk customers", "churn hotspots", "regional attrition", "customer risk by territory", "retention alerts"],
        "widgets": [
            widget("churn_risk_by_region", "kpi_risk_customers", "kpi", "High-Risk Customers", measures=["high_risk_customers", "risk_rate_pct"]),
            widget("churn_risk_by_region", "chart_risk_map", "bar_chart", "Churn Risk by Region", measures=["risk_rate_pct"], columns=["region"]),
            widget("churn_risk_by_region", "grid_risk_table", "grid", "Risk Detail Lookup", columns=["region", "high_risk_customers", "risk_rate_pct", "retention_action"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": None},
        ],
        "date_range_options": ["last_30_days", "this_month", "last_month", "this_quarter", "last_quarter"],
        "default_date_range": "last_30_days",
        "sort_options": [
            {"field": "risk_rate_pct", "label": "Risk % (Desc)"},
            {"field": "region", "label": "Region Name"},
        ],
        "default_sort": {"field": "risk_rate_pct", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "customer_lifetime_value",
        "title": "Customer Lifetime Value",
        "description": "Benchmark each customer cohort by long-term value to prioritize retention spend and acquisition efficiency.",
        "directory": "customers",
        "subdirectory": "segments",
        "route": "/customers/segments/customer-lifetime-value",
        "keywords": ["customer value", "lifetime value", "lifetime revenue", "cohort profitability", "long-term worth"],
        "widgets": [
            widget("customer_lifetime_value", "kpi_clv", "kpi", "Average Lifetime Value", measures=["avg_clv_usd", "clv_growth_pct"]),
            widget("customer_lifetime_value", "chart_clv_by_segment", "bar_chart", "CLV by Segment", measures=["avg_clv_usd"], columns=["segment"]),
            widget("customer_lifetime_value", "grid_clv_table", "grid", "Cohort Value Insights", columns=["segment", "customer_count", "avg_clv_usd", "avg_order_value"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": "Online"},
        ],
        "date_range_options": ["this_quarter", "last_quarter", "this_year", "custom"],
        "default_date_range": "this_year",
        "sort_options": [
            {"field": "avg_clv_usd", "label": "Lifetime Value (Desc)"},
            {"field": "segment", "label": "Segment Name"},
        ],
        "default_sort": {"field": "avg_clv_usd", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "inventory_stock_by_region",
        "title": "Inventory Stock by Region",
        "description": "Monitor fulfillment stock coverage and inventory availability across each region to prevent stockouts and optimize balancing.",
        "directory": "inventory",
        "subdirectory": "stock",
        "route": "/inventory/stock/inventory-stock-by-region",
        "keywords": ["stock by region", "inventory coverage", "territory stock levels", "regional stock health", "warehouse availability"],
        "widgets": [
            widget("inventory_stock_by_region", "kpi_total_units_on_hand", "kpi", "Units on Hand", measures=["units_on_hand", "inventory_turnover_pct"]),
            widget("inventory_stock_by_region", "chart_stock_by_region", "bar_chart", "Inventory by Region", measures=["units_on_hand"], columns=["region"]),
            widget("inventory_stock_by_region", "grid_stock_summary", "grid", "Regional Stock Table", columns=["region", "units_on_hand", "days_of_cover", "stockout_risk"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["last_7_days", "last_30_days", "this_month", "this_quarter"],
        "default_date_range": "this_month",
        "sort_options": [
            {"field": "units_on_hand", "label": "Units on Hand (Desc)"},
            {"field": "region", "label": "Region Name"},
        ],
        "default_sort": {"field": "units_on_hand", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "inventory_value_by_category",
        "title": "Inventory Value by Category",
        "description": "Review current inventory value by category to balance working capital and ensure high-margin stock is protected.",
        "directory": "inventory",
        "subdirectory": "stock",
        "route": "/inventory/stock/inventory-value-by-category",
        "keywords": ["inventory value", "category asset value", "stock valuation", "working capital inventory", "warehouse asset mix"],
        "widgets": [
            widget("inventory_value_by_category", "kpi_inventory_value", "kpi", "Total Inventory Value", measures=["inventory_value_usd", "margin_coverage_pct"]),
            widget("inventory_value_by_category", "chart_value_by_category", "bar_chart", "Stock Value by Category", measures=["inventory_value_usd"], columns=["category"]),
            widget("inventory_value_by_category", "grid_value_table", "grid", "Inventory Valuation Detail", columns=["category", "product_name", "units_on_hand", "inventory_value_usd"]),
        ],
        "filters": [
            {"name": "category", "type": "multi_select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": ["Packaged Foods", "Beverages", "Household", "Personal Care"]},
            {"name": "region", "type": "select", "allowed_values": ["North", "South", "East", "West"], "default": None},
        ],
        "date_range_options": ["this_month", "last_month", "this_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "inventory_value_usd", "label": "Value (Desc)"},
            {"field": "category", "label": "Category Name"},
        ],
        "default_sort": {"field": "inventory_value_usd", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "supplier_performance",
        "title": "Supplier Performance",
        "description": "Assess supplier fill rates, delivery reliability, and service scores to protect supply continuity and vendor quality.",
        "directory": "inventory",
        "subdirectory": "suppliers",
        "route": "/inventory/suppliers/supplier-performance",
        "keywords": ["supplier scorecard", "vendor reliability", "fill rate", "on-time delivery", "supplier health"],
        "widgets": [
            widget("supplier_performance", "kpi_on_time_delivery", "kpi", "On-Time Delivery Rate", measures=["otd_pct", "fill_rate_pct"]),
            widget("supplier_performance", "chart_supplier_scores", "bar_chart", "Supplier Score Comparison", measures=["score"], columns=["supplier"]),
            widget("supplier_performance", "grid_supplier_table", "grid", "Supplier Detail Table", columns=["supplier", "otd_pct", "fill_rate_pct", "avg_lead_time_days", "status"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["last_30_days", "this_month", "last_month", "this_quarter"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "fill_rate_pct", "label": "Fill Rate (Desc)"},
            {"field": "supplier", "label": "Supplier Name"},
        ],
        "default_sort": {"field": "fill_rate_pct", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "low_stock_alerts",
        "title": "Low Stock Alerts",
        "description": "Prioritize replenishment actions for products at risk of stockout or service disruption across the network.",
        "directory": "inventory",
        "subdirectory": "stock",
        "route": "/inventory/stock/low-stock-alerts",
        "keywords": ["stockout alerts", "replenishment urgency", "critical inventory", "low supply coverage", "stock risk"],
        "widgets": [
            widget("low_stock_alerts", "kpi_alert_count", "kpi", "Critical SKUs", measures=["alert_count", "stockout_risk_pct"]),
            widget("low_stock_alerts", "chart_alert_volume", "bar_chart", "Alert Volume by Region", measures=["alert_count"], columns=["region"]),
            widget("low_stock_alerts", "grid_alert_list", "grid", "At-Risk Stock Detail", columns=["product_name", "region", "units_on_hand", "days_of_cover", "priority"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["today", "last_7_days", "last_30_days", "this_month"],
        "default_date_range": "today",
        "sort_options": [
            {"field": "days_of_cover", "label": "Days Coverage (Asc)"},
            {"field": "region", "label": "Region Name"},
        ],
        "default_sort": {"field": "days_of_cover", "order": "asc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "stock_turnover_by_product",
        "title": "Stock Turnover by Product",
        "description": "Review how quickly each product turns over so demand-heavy SKUs can be prioritized and slower movers can be rationalized.",
        "directory": "inventory",
        "subdirectory": "stock",
        "route": "/inventory/stock/stock-turnover-by-product",
        "keywords": ["stock turnover", "inventory velocity", "sku velocity", "product throughput", "fast movers"],
        "widgets": [
            widget("stock_turnover_by_product", "kpi_turnover_rate", "kpi", "Average Turnover Rate", measures=["turnover_ratio", "avg_days_inventory"]),
            widget("stock_turnover_by_product", "chart_turnover_leaderboard", "bar_chart", "Fastest Moving SKUs", measures=["turnover_ratio"], columns=["product_name"]),
            widget("stock_turnover_by_product", "grid_turnover_table", "grid", "Product Turnover Details", columns=["product_name", "category", "turnover_ratio", "avg_days_inventory", "units_sold"]),
        ],
        "filters": [
            {"name": "category", "type": "multi_select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": ["Packaged Foods", "Beverages", "Household", "Personal Care"]},
            {"name": "region", "type": "select", "allowed_values": ["North", "South", "East", "West"], "default": None},
        ],
        "date_range_options": ["this_month", "last_month", "this_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "turnover_ratio", "label": "Turnover (Desc)"},
            {"field": "product_name", "label": "Product Name"},
        ],
        "default_sort": {"field": "turnover_ratio", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "purchase_order_backlog",
        "title": "Purchase Order Backlog",
        "description": "Track outstanding purchase orders and timing exposure to ensure supply plans stay in step with demand needs.",
        "directory": "inventory",
        "subdirectory": "suppliers",
        "route": "/inventory/suppliers/purchase-order-backlog",
        "keywords": ["purchase order backlog", "open PO queue", "supplier orders", "outstanding inventory orders", "stock replenishment pipeline"],
        "widgets": [
            widget("purchase_order_backlog", "kpi_open_po_value", "kpi", "Open PO Value", measures=["po_value_usd", "po_count"]),
            widget("purchase_order_backlog", "chart_po_timing", "line_chart", "Outstanding Orders Over Time", measures=["po_value_usd"], columns=["date"]),
            widget("purchase_order_backlog", "grid_po_table", "grid", "PO Backlog Detail", columns=["supplier", "product_name", "po_value_usd", "eta_date", "status"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "supplier", "type": "select", "allowed_values": ["Northline Foods", "Harbor Goods", "Summit Supply", "Blue Harbor Logistics"], "default": None},
        ],
        "date_range_options": ["this_month", "last_month", "this_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "po_value_usd", "label": "PO Value (Desc)"},
            {"field": "eta_date", "label": "ETA Date"},
        ],
        "default_sort": {"field": "po_value_usd", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "inventory_aging_summary",
        "title": "Inventory Aging Summary",
        "description": "Identify stale inventory and aging stock so markdown decisions can be made before products become stranded assets.",
        "directory": "inventory",
        "subdirectory": "stock",
        "route": "/inventory/stock/inventory-aging-summary",
        "keywords": ["inventory aging", "slow movers", "stale stock", "aged inventory", "obsolescence risk"],
        "widgets": [
            widget("inventory_aging_summary", "kpi_aging_value", "kpi", "Aged Inventory Value", measures=["aged_value_usd", "aged_pct"]),
            widget("inventory_aging_summary", "chart_age_bucket", "bar_chart", "Aging Buckets", measures=["units"], columns=["age_bucket"]),
            widget("inventory_aging_summary", "grid_aging_table", "grid", "Aging Detail", columns=["product_name", "category", "days_in_stock", "units_on_hand", "value_usd"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["this_month", "last_month", "this_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "aged_value_usd", "label": "Aged Value (Desc)"},
            {"field": "days_in_stock", "label": "Days in Stock (Desc)"},
        ],
        "default_sort": {"field": "aged_value_usd", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "user_access_overview",
        "title": "User Access Overview",
        "description": "Review account access levels and permission coverage to confirm the right teams can see the right operational data.",
        "directory": "admin",
        "subdirectory": "users",
        "route": "/admin/users/user-access-overview",
        "keywords": ["user permissions", "access matrix", "role coverage", "user activity", "security review"],
        "widgets": [
            widget("user_access_overview", "kpi_total_users", "kpi", "Total Active Users", measures=["active_users", "sso_coverage_pct"]),
            widget("user_access_overview", "chart_access_mix", "pie_chart", "Role Access Mix", measures=["user_count"], columns=["role"]),
            widget("user_access_overview", "grid_access_table", "grid", "User Access Table", columns=["user_name", "role", "team", "last_login", "status"]),
        ],
        "filters": [
            {"name": "role", "type": "select", "allowed_values": ["admin", "regional_manager", "analyst"], "default": "analyst"},
            {"name": "team", "type": "select", "allowed_values": ["Sales", "Finance", "Operations", "Customer Success"], "default": None},
        ],
        "date_range_options": ["last_30_days", "this_month", "this_quarter", "this_year"],
        "default_date_range": "this_month",
        "sort_options": [
            {"field": "user_count", "label": "Users (Desc)"},
            {"field": "role", "label": "Role"},
        ],
        "default_sort": {"field": "user_count", "order": "desc"},
        "allowed_roles": ["admin"],
    },
    {
        "id": "audit_log_activity",
        "title": "Audit Log Activity",
        "description": "Inspect recent administrative actions, configuration changes, and anomaly indicators across core operational workflows.",
        "directory": "admin",
        "subdirectory": "audit",
        "route": "/admin/audit/audit-log-activity",
        "keywords": ["audit trail", "admin actions", "security events", "change log", "access surveillance"],
        "widgets": [
            widget("audit_log_activity", "kpi_failed_events", "kpi", "Failed Events", measures=["failed_events", "risk_score"]),
            widget("audit_log_activity", "chart_activity_timeline", "line_chart", "Audit Events Over Time", measures=["event_count"], columns=["date"]),
            widget("audit_log_activity", "grid_audit_table", "grid", "Audit Event Details", columns=["event_time", "user_name", "action", "entity", "result"]),
        ],
        "filters": [
            {"name": "event_type", "type": "select", "allowed_values": ["create", "update", "delete", "export", "login"], "default": None},
            {"name": "team", "type": "select", "allowed_values": ["Sales", "Finance", "Operations", "Customer Success"], "default": None},
        ],
        "date_range_options": ["today", "last_7_days", "last_30_days", "this_month", "this_quarter"],
        "default_date_range": "last_7_days",
        "sort_options": [
            {"field": "event_time", "label": "Event Time (Desc)"},
            {"field": "user_name", "label": "User Name"},
        ],
        "default_sort": {"field": "event_time", "order": "desc"},
        "allowed_roles": ["admin"],
    },
    {
        "id": "system_role_matrix",
        "title": "System Role Matrix",
        "description": "Ensure every team and permission set is aligned to the right operational capabilities and access boundaries.",
        "directory": "admin",
        "subdirectory": "users",
        "route": "/admin/users/system-role-matrix",
        "keywords": ["role matrix", "access policy", "permission map", "security matrix", "privilege assignment"],
        "widgets": [
            widget("system_role_matrix", "kpi_secure_roles", "kpi", "Secured Roles", measures=["roles_configured", "privilege_coverage_pct"]),
            widget("system_role_matrix", "chart_role_coverage", "bar_chart", "Role Coverage by Team", measures=["role_count"], columns=["team"]),
            widget("system_role_matrix", "grid_role_matrix", "grid", "Permission Matrix", columns=["role", "team", "module_access", "sensitive_actions", "approval_required"]),
        ],
        "filters": [
            {"name": "role", "type": "multi_select", "allowed_values": ["admin", "regional_manager", "analyst"], "default": ["admin", "regional_manager", "analyst"]},
            {"name": "team", "type": "select", "allowed_values": ["Sales", "Finance", "Operations", "Customer Success"], "default": None},
        ],
        "date_range_options": ["this_month", "this_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "role", "label": "Role"},
            {"field": "team", "label": "Team Name"},
        ],
        "default_sort": {"field": "role", "order": "asc"},
        "allowed_roles": ["admin"],
    },
    {
        "id": "expense_variance_by_region",
        "title": "Expense Variance by Region",
        "description": "Compare actual expense performance against approved budgets to catch under- or over-spend patterns in individual regions.",
        "directory": "finance",
        "subdirectory": "expenses",
        "route": "/finance/expenses/expense-variance-by-region",
        "keywords": ["expense variance", "budget variance", "regional spend", "opex by region", "budget deviation"],
        "widgets": [
            widget("expense_variance_by_region", "kpi_variance_usd", "kpi", "Actual vs Budget Variance", measures=["variance_usd", "variance_pct"]),
            widget("expense_variance_by_region", "chart_variance_by_region", "bar_chart", "Expense Variance by Region", measures=["variance_usd"], columns=["region"]),
            widget("expense_variance_by_region", "grid_variance_detail", "grid", "Regional Expense Detail", columns=["region", "budget_amount", "actual_spent", "variance_usd", "variance_pct"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["this_month", "last_month", "this_quarter", "last_quarter"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "variance_usd", "label": "Variance (Desc)"},
            {"field": "region", "label": "Region Name"},
        ],
        "default_sort": {"field": "variance_usd", "order": "desc"},
        "allowed_roles": ["admin", "analyst"],
    },
    {
        "id": "margin_protection_index",
        "title": "Margin Protection Index",
        "description": "Review margin retention strength across categories and regions to guard against pricing and procurement erosion.",
        "directory": "finance",
        "subdirectory": "margins",
        "route": "/finance/margins/margin-protection-index",
        "keywords": ["margin protection", "pricing resilience", "profit risk", "margin safeguard", "gross margin guardrail"],
        "widgets": [
            widget("margin_protection_index", "kpi_margin_index", "kpi", "Margin Protection Score", measures=["margin_index", "margin_gap_pct"]),
            widget("margin_protection_index", "chart_margin_index", "line_chart", "Margin Index Over Time", measures=["margin_index"], columns=["date"]),
            widget("margin_protection_index", "grid_margin_table", "grid", "Margin Protection Detail", columns=["region", "category", "margin_index", "gross_profit", "loss_risk"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "category", "type": "select", "allowed_values": ["Packaged Foods", "Beverages", "Household", "Personal Care"], "default": None},
        ],
        "date_range_options": ["this_month", "last_month", "this_quarter", "this_year"],
        "default_date_range": "this_quarter",
        "sort_options": [
            {"field": "margin_index", "label": "Margin Index (Desc)"},
            {"field": "category", "label": "Category Name"},
        ],
        "default_sort": {"field": "margin_index", "order": "desc"},
        "allowed_roles": ["admin", "analyst"],
    },
    {
        "id": "shipping_performance_by_region",
        "title": "Shipping Performance by Region",
        "description": "Track order fulfillment reliability and carrier delivery performance to flag service degradation in each region.",
        "directory": "operations",
        "subdirectory": "fulfillment",
        "route": "/operations/fulfillment/shipping-performance-by-region",
        "keywords": ["shipping performance", "carrier SLA", "delivery reliability", "regional logistics", "shipment punctuality"],
        "widgets": [
            widget("shipping_performance_by_region", "kpi_on_time_delivery", "kpi", "On-Time Shipment Rate", measures=["on_time_pct", "delay_pct"]),
            widget("shipping_performance_by_region", "chart_shipping_by_region", "bar_chart", "Regional Shipping Reliability", measures=["on_time_pct"], columns=["region"]),
            widget("shipping_performance_by_region", "grid_shipping_table", "grid", "Shipping Detail", columns=["region", "carrier", "on_time_pct", "avg_delivery_days", "total_shipments"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": None},
        ],
        "date_range_options": ["last_7_days", "last_30_days", "this_month", "this_quarter"],
        "default_date_range": "this_month",
        "sort_options": [
            {"field": "on_time_pct", "label": "On-Time % (Desc)"},
            {"field": "region", "label": "Region Name"},
        ],
        "default_sort": {"field": "on_time_pct", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
    {
        "id": "warehouse_capacity_utilization",
        "title": "Warehouse Capacity Utilization",
        "description": "Measure how much facility capacity is being used to spot expansion needs and reduce overflow handling inefficiencies.",
        "directory": "operations",
        "subdirectory": "orders",
        "route": "/operations/orders/warehouse-capacity-utilization",
        "keywords": ["warehouse utilization", "facility load", "capacity planning", "space usage", "warehouse throughput"],
        "widgets": [
            widget("warehouse_capacity_utilization", "kpi_utilization_pct", "kpi", "Average Capacity Use", measures=["utilization_pct", "free_space_pct"]),
            widget("warehouse_capacity_utilization", "chart_capacity_by_region", "bar_chart", "Capacity Utilization by Region", measures=["utilization_pct"], columns=["region"]),
            widget("warehouse_capacity_utilization", "grid_capacity_table", "grid", "Facility Capacity Detail", columns=["region", "warehouse_name", "utilization_pct", "free_space_pct", "peak_volume"]),
        ],
        "filters": [
            {"name": "region", "type": "multi_select", "allowed_values": ["North", "South", "East", "West"], "default": ["North", "South", "East", "West"]},
            {"name": "channel", "type": "select", "allowed_values": ["Online", "Retail", "Partner"], "default": None},
        ],
        "date_range_options": ["this_week", "last_30_days", "this_month", "this_quarter"],
        "default_date_range": "this_month",
        "sort_options": [
            {"field": "utilization_pct", "label": "Utilization % (Desc)"},
            {"field": "region", "label": "Region Name"},
        ],
        "default_sort": {"field": "utilization_pct", "order": "desc"},
        "allowed_roles": ["admin", "regional_manager", "analyst"],
    },
]


def ensure_new_directories(doc):
    existing = {item["id"]: item for item in doc.get("directories", [])}
    for directory in NEW_DIRECTORIES:
        target = existing.get(directory["id"])
        if target is None:
            doc["directories"].append(directory)
            continue
        target_subs = {item["id"] for item in target.setdefault("subdirectories", [])}
        for sub in directory["subdirectories"]:
            if sub["id"] not in target_subs:
                target["subdirectories"].append(sub)


def compute_region_scoped(page):
    filters = page.get("filters", [])
    if any(filter_item.get("name") == "region" for filter_item in filters):
        return True
    for widget in page.get("widgets", []):
        columns = widget.get("columns", [])
        if any(isinstance(column, str) and "region" in column.lower() for column in columns):
            return True
    return False


def decorate_page(page):
    actions = [
        {"id": "reset_filters", "label": "Reset filters", "requires_confirmation": False},
        {"id": "export_csv", "label": "Export CSV", "requires_confirmation": True},
    ]
    if page.get("directory") == "admin" or page.get("allowed_roles") == ["admin"] or set(page.get("allowed_roles", [])) == {"admin"}:
        actions.append({"id": "save_view", "label": "Save view", "requires_confirmation": True})
    page["region_scoped"] = compute_region_scoped(page)
    page["actions"] = actions
    return page


def main():
    with META_PATH.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)

    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Business database does not exist: {DB_PATH}")
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        date_range = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    if not date_range or date_range[0] is None or date_range[1] is None:
        raise RuntimeError(f"No order dates are available in {DB_PATH}")
    doc.setdefault("dimensions", {})["date_range"] = {
        "start": date_range[0].date().isoformat(),
        "end": date_range[1].date().isoformat(),
    }

    ensure_new_directories(doc)

    existing_ids = {page["id"] for page in doc.get("pages", [])}
    existing_routes = {page["route"] for page in doc.get("pages", [])}

    new_pages = []
    for page in NEW_PAGES:
        if page["id"] not in existing_ids and page["route"] not in existing_routes:
            new_pages.append(page)

    for page in new_pages:
        doc["pages"].append(decorate_page(page))

    for page in doc.get("pages", []):
        if "region_scoped" not in page:
            page["region_scoped"] = compute_region_scoped(page)
        if "actions" not in page:
            decorate_page(page)

    with META_PATH.open("w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"Data file updated: {META_PATH}")
    print(f"Directories present: {len(doc['directories'])}")
    print(f"Pages present: {len(doc['pages'])}")
    print(f"New pages added: {len(new_pages)}")


if __name__ == "__main__":
    main()
