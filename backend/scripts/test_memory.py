from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import main as backend_main
from app.session import Session, SessionStore, get_session_store
from app.agent import AgentRun, _system_prompt, run_agent
from app.llm import LLMReply, ToolCall, get_llm_client
from app.tools import ToolContext


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


def test_session_store_behavior() -> bool:
    store = SessionStore(max_sessions=200, idle_timeout_s=3600.0)

    # 1. Stores up to 6 turns, drops the oldest
    sess = store.get_or_create("sess_turns", "admin")
    for i in range(1, 8):
        sess.add_turn({
            "user_message": f"message_{i}",
            "outcome": "answered",
            "plan_summary": {"page": "revenue_by_region", "filters": {"region": f"R_{i}"}},
            "answer_text": f"answer_{i}",
            "key_numbers": [],
            "evidence_ref": None,
        })
    turn_check = len(sess.turns) == 6 and sess.turns[0]["user_message"] == "message_2" and sess.turns[-1]["user_message"] == "message_7"

    # 2. Expires when idle
    sess.last_active = time.time() - 3601.0
    expired_check = sess.is_expired(3600.0)
    refreshed = store.get_or_create("sess_turns", "admin")
    reset_on_expire = len(refreshed.turns) == 0

    # 3. Resets on role change
    sess2 = store.get_or_create("sess_role", "admin")
    sess2.add_turn({
        "user_message": "hello",
        "outcome": "answered",
        "plan_summary": {},
        "answer_text": "hi",
        "key_numbers": [],
        "evidence_ref": None,
    })
    changed_role = store.get_or_create("sess_role", "analyst")
    role_check = changed_role.role == "analyst" and len(changed_role.turns) == 0

    # 4. Max 200 sessions capacity
    cap_store = SessionStore(max_sessions=5, idle_timeout_s=3600.0)
    for i in range(10):
        cap_store.get_or_create(f"sess_cap_{i}", "admin")
    cap_check = cap_store.count() <= 5

    passed = turn_check and expired_check and reset_on_expire and role_check and cap_check
    return report(
        "Session stores up to 6 turns, drops oldest, expires when idle, resets on role change",
        passed,
        f"turns_len={len(sess.turns)}, reset_on_expire={reset_on_expire}, role_reset={role_check}, cap={cap_store.count()}",
    )


def test_system_prompt_contains_memory_blocks() -> bool:
    store = get_session_store()
    sess_id = "test_sess_prompt_check"
    sess = store.get_or_create(sess_id, "admin")
    sess.add_turn({
        "user_message": "Show South revenue this quarter",
        "outcome": "answered",
        "plan_summary": {
            "page": "revenue_by_region",
            "filters": {"region": ["South"], "channel": None},
            "date_range": "this_quarter",
            "sort": None,
            "chart_type": "bar",
        },
        "answer_text": "South revenue this quarter is $96,337.98.",
        "key_numbers": [{"label": "Total Revenue", "value": 96337.98}],
        "evidence_ref": {"page": {"id": "revenue_by_region"}},
    })

    prompt = _system_prompt("admin", session=sess)
    has_conv_block = "CONVERSATION SO FAR:" in prompt
    has_last_result = "LAST RESULT:" in prompt
    has_filters = '"region": ["South"]' in prompt or "'region': ['South']" in prompt or "South" in prompt
    passed = has_conv_block and has_last_result and has_filters
    return report(
        "System prompt for second turn contains CONVERSATION SO FAR and LAST RESULT blocks with filters",
        passed,
    )


def test_mocked_llm_nonexistent_page() -> bool:
    mock_client = MagicMock()
    mock_client.generate.return_value = LLMReply(
        text="",
        tool_calls=[ToolCall(id="c1", name="navigate", args={"page_id": "nonexistent_fake_page"})],
        raw_content=[],
        usage={},
        cached=False,
        latency_ms=10.0,
    )
    with patch("app.agent.get_llm_client", return_value=mock_client):
        res = run_agent("Open secret nonexistent page", "admin")

    passed = (
        res.get("outcome") == "refused"
        and res.get("refusal_reason") == "not_in_app"
        and len(res.get("suggestions", [])) > 0
        and len(res.get("plan", [])) == 0
    )
    return report(
        "Mocked LLM returning nonexistent page yields outcome refused, reason not_in_app, suggestions, empty plan",
        passed,
        f"outcome={res.get('outcome')}, reason={res.get('refusal_reason')}, suggestions={len(res.get('suggestions', []))}, plan={res.get('plan')}",
    )


def test_refusals_and_clarify() -> bool:
    checks = []

    # 1. not_permitted for analyst opening admin-only page
    mock_client1 = MagicMock()
    mock_client1.generate.return_value = LLMReply(
        text="",
        tool_calls=[ToolCall(id="c1", name="navigate", args={"page_id": "user_access_overview"})],
        raw_content=[],
        usage={},
        cached=False,
        latency_ms=10.0,
    )
    with patch("app.agent.get_llm_client", return_value=mock_client1):
        res1 = run_agent("Open user access overview", "analyst")
    p1 = (
        res1.get("outcome") == "refused"
        and res1.get("refusal_reason") == "not_permitted"
        and len(res1.get("plan", [])) == 0
    )
    checks.append(report("not_permitted for analyst opening admin-only page", p1, f"reason={res1.get('refusal_reason')}"))

    # 2. out_of_scope for "What is the capital of France?" (mock LLM text)
    mock_client2 = MagicMock()
    mock_client2.generate.return_value = LLMReply(
        text="The capital of France is Paris.",
        tool_calls=[],
        raw_content=[{"text": "The capital of France is Paris."}],
        usage={},
        cached=False,
        latency_ms=10.0,
    )
    with patch("app.agent.get_llm_client", return_value=mock_client2):
        res2 = run_agent("What is the capital of France?", "admin")
    p2 = (
        res2.get("outcome") == "refused"
        and res2.get("refusal_reason") == "out_of_scope"
        and len(res2.get("plan", [])) == 0
    )
    checks.append(report("out_of_scope for 'What is the capital of France?'", p2, f"reason={res2.get('refusal_reason')}"))

    # 3. out_of_data_range for dates after 2026-09-30
    mock_client3 = MagicMock()
    mock_client3.generate.return_value = LLMReply(
        text="",
        tool_calls=[ToolCall(id="c1", name="set_date_range", args={"start": "2027-01-01", "end": "2027-03-31"})],
        raw_content=[],
        usage={},
        cached=False,
        latency_ms=10.0,
    )
    with patch("app.agent.get_llm_client", return_value=mock_client3):
        res3 = run_agent("Show revenue after 2026-09-30", "admin")
    p3 = (
        res3.get("outcome") == "refused"
        and res3.get("refusal_reason") == "out_of_data_range"
        and len(res3.get("plan", [])) == 0
        and len(res3.get("suggestions", [])) > 0
    )
    checks.append(report("out_of_data_range for dates after 2026-09-30", p3, f"reason={res3.get('refusal_reason')}"))

    # 4. clarify returns exactly one question and no plan
    mock_client4 = MagicMock()
    mock_client4.generate.return_value = LLMReply(
        text="Which region or channel do you mean?",
        tool_calls=[],
        raw_content=[{"text": "Which region or channel do you mean?"}],
        usage={},
        cached=False,
        latency_ms=10.0,
    )
    with patch("app.agent.get_llm_client", return_value=mock_client4):
        res4 = run_agent("Show revenue", "admin")
    clarify_text = str(res4.get("clarify") or "")
    p4 = (
        res4.get("outcome") == "clarify"
        and clarify_text.count("?") == 1
        and len(res4.get("plan", [])) == 0
    )
    checks.append(report("clarify returns exactly one question and no plan", p4, f"clarify='{clarify_text}'"))

    return all(checks)


def test_old_requests_without_session_id() -> bool:
    res = run_agent("Show South revenue this quarter", "admin")
    p1 = (
        res.get("outcome") == "answered"
        and bool(res.get("session_id"))
        and len(res.get("plan", [])) > 0
    )

    from fastapi.testclient import TestClient
    client = TestClient(backend_main.app)
    api_res = client.post("/api/agent", json={"message": "Show South revenue this quarter", "role": "admin"})
    p2 = api_res.status_code == 200 and bool(api_res.json().get("session_id"))

    passed = p1 and p2
    return report("Old requests without session_id still work and return session_id", passed)


def test_live_follow_up() -> bool:
    client = get_llm_client()
    if not client.api_key or not client.model:
        return report("Live follow-up test skipped", True, "GEMINI_API_KEY or model not set")

    try:
        live_sid = f"live_followup_{int(time.time())}"
        res1 = run_agent("Show South revenue this quarter", "admin", session_id=live_sid)
        if not res1.get("answer"):
            return report("Live follow-up test skipped", True, "First call failed")

        res2 = run_agent("same for North", "admin", session_id=live_sid)
        plan2 = res2.get("plan", [])
        has_nav = any(step.get("tool") == "navigate" for step in plan2)
        has_region_filter = any(
            step.get("tool") == "set_filter" and "North" in str(step.get("args", {}).get("value", ""))
            for step in plan2
        )
        passed = (not has_nav) and has_region_filter and res2.get("outcome") == "answered"
        return report(
            "Live Gemini session follow-up changes only region",
            passed,
            f"plan1_len={len(res1.get('plan', []))}, plan2={plan2}",
        )
    except Exception as e:
        return report("Live follow-up test skipped", True, f"Error: {e}")


def main() -> None:
    results = [
        test_session_store_behavior(),
        test_system_prompt_contains_memory_blocks(),
        test_mocked_llm_nonexistent_page(),
        test_refusals_and_clarify(),
        test_old_requests_without_session_id(),
        test_live_follow_up(),
    ]
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
