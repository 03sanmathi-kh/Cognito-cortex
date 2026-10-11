from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import main as backend_main
from app import agent as agent_module
from app.agent import AgentRun, run_agent
from app.llm import LLMReply, ToolCall
from app.tools import ToolContext


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def test_agent_run_initial_context() -> bool:
    context = ToolContext("admin")
    ui_context = {
        "page_id": "revenue_by_region",
        "route": "/sales/regional/revenue-by-region",
        "filters": {"region": "South"},
        "date_range": {"preset": "this_quarter", "start": "2026-07-01", "end": "2026-09-30"},
        "sort": None,
        "role": "admin",
    }
    run = AgentRun(context, ui_context=ui_context)
    passed = (
        run.page is not None
        and run.page.get("id") == "revenue_by_region"
        and run.filters.get("region") in ("South", ["South"])
        and run.date_range == "this_quarter"
        and len(run.plan) == 0
    )
    return report(
        "AgentRun built with ui_context region=South on revenue_by_region starts with that filter and page",
        passed,
        f"page={run.page.get('id') if run.page else None}, filters={run.filters}, plan={run.plan}",
    )


def test_invalid_ui_context_dropped_silently() -> bool:
    context = ToolContext("admin")
    # 1. Fake page is silently dropped
    run_fake_page = AgentRun(context, ui_context={"page_id": "fake_nonexistent_page"})
    page_dropped = run_fake_page.page is None and len(run_fake_page.plan) == 0

    # 2. On valid page, unknown filter name and invalid filter value are dropped
    ui_context_bad_filters = {
        "page_id": "revenue_by_region",
        "filters": {
            "fake_filter_xyz": "value",
            "region": "InvalidRegionNonexistent",
        },
        "date_range": "unsupported_fake_preset",
        "sort": "fake_sort_field",
    }
    run_bad_filters = AgentRun(context, ui_context=ui_context_bad_filters)
    filters_cleaned = (
        run_bad_filters.page is not None
        and run_bad_filters.page.get("id") == "revenue_by_region"
        and "fake_filter_xyz" not in run_bad_filters.filters
        and run_bad_filters.filters.get("region") != "InvalidRegionNonexistent"
        and run_bad_filters.filters.get("region") != ["InvalidRegionNonexistent"]
        and run_bad_filters.date_range != "unsupported_fake_preset"
        and run_bad_filters.sort_field != "fake_sort_field"
        and len(run_bad_filters.plan) == 0
    )
    passed = page_dropped and filters_cleaned
    return report("Invalid ui_context values (fake filter, fake page) are dropped without error", passed)


def test_no_change_adds_no_navigate_or_filter_step() -> bool:
    context = ToolContext("admin")
    ui_context = {
        "page_id": "revenue_by_region",
        "filters": {"region": "South"},
        "date_range": {"preset": "this_quarter", "start": "2026-07-01", "end": "2026-09-30"},
    }
    run = AgentRun(context, ui_context=ui_context)
    # Model calls navigate to the page it is already on
    run.navigate("revenue_by_region")
    # Model calls set_filter to the value it already has
    run.set_filter("region", "South")
    # Model calls set_date_range to the range it already has
    run.set_date_range("2026-07-01", "2026-09-30")

    no_nav_or_filter = not any(step.get("tool") in ("navigate", "set_filter", "set_date_range") for step in run.plan)
    passed = no_nav_or_filter and len(run.plan) == 0
    return report(
        "A request that needs no change adds NO navigate or set_filter step",
        passed,
        f"plan={run.plan}",
    )


def test_role_cannot_be_raised_through_ui_context() -> bool:
    # An analyst tries to access an admin-only page via ui_context claiming role="admin"
    context = ToolContext("analyst")
    ui_context = {
        "page_id": "user_access_overview",  # admin-only page
        "role": "admin",
    }
    run = AgentRun(context, ui_context=ui_context)
    # The page must be dropped because analyst cannot access user_access_overview
    passed = (
        run.page is None
        and run.context.role == "analyst"
        and len(run.plan) == 0
    )
    return report(
        "A role cannot be raised through ui_context (the page must still pass the role check)",
        passed,
        f"page={run.page.get('id') if run.page else None}, role={run.context.role}",
    )


def test_old_requests_no_ui_context() -> bool:
    # Verify run_agent works offline when LLM performs tool sequence
    def mock_generate(*args, **kwargs):
        history = args[1] if len(args) > 1 else kwargs.get("history", [])
        if not any(h.get("role") == "tool" for h in history):
            return LLMReply(
                text="",
                tool_calls=[ToolCall(id="call_1", name="navigate", args={"page_id": "revenue_by_region"})],
                raw_content=[],
                usage={},
                cached=False,
                latency_ms=10.0,
            )
        return LLMReply(
            text="All revenue data retrieved.",
            tool_calls=[],
            raw_content=[{"text": "All revenue data retrieved."}],
            usage={},
            cached=False,
            latency_ms=10.0,
        )

    mock_client = MagicMock()
    mock_client.generate.side_effect = mock_generate
    with patch("app.agent.get_llm_client", return_value=mock_client):
        # 1. Request with ui_context=None
        res1 = run_agent("Show South revenue this quarter", "admin", ui_context=None)
        passed1 = bool(res1.get("answer")) and len(res1.get("plan", [])) == 1

        # 2. Request without passing ui_context parameter at all
        res2 = run_agent("Show South revenue this quarter", "admin")
        passed2 = bool(res2.get("answer")) and len(res2.get("plan", [])) == 1

        # 3. Verify endpoint handles request without ui_context
        from fastapi.testclient import TestClient
        client = TestClient(backend_main.app)
        api_res = client.post("/api/agent", json={"message": "Show South revenue this quarter", "role": "admin"})
        passed3 = api_res.status_code == 200 and bool(api_res.json().get("answer"))

    passed = passed1 and passed2 and passed3
    return report("Old requests with no ui_context still work", passed)


def main() -> None:
    checks = [
        test_agent_run_initial_context(),
        test_invalid_ui_context_dropped_silently(),
        test_no_change_adds_no_navigate_or_filter_step(),
        test_role_cannot_be_raised_through_ui_context(),
        test_old_requests_no_ui_context(),
    ]
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
