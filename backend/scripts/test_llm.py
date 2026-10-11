from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app import llm
from app.agent import _AGENT_TOOLS, run_agent
from app import agent as agent_module
import main as backend_main


def report(name: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {name}{': ' + detail if detail else ''}")
    return passed


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any], headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeHTTP:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.responses.pop(0)


def _success_payload(parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "candidates": [{"content": {"role": "model", "parts": parts or [{"text": "ok"}]}}],
        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
    }


def test_schema_conversion() -> bool:
    converted = llm.convert_tools(_AGENT_TOOLS)
    declarations = {item["name"]: item for item in converted}

    def valid_schema(schema: dict[str, Any]) -> bool:
        if "additionalProperties" in schema or not schema.get("type"):
            return False
        if schema["type"] == "OBJECT":
            return all(valid_schema(value) for value in schema.get("properties", {}).values())
        if schema["type"] == "ARRAY":
            return valid_schema(schema["items"])
        return True

    passed = all(valid_schema(item["parameters"]) for item in converted)
    return report("Gemini schemas have concrete types and no additionalProperties", passed)


def test_restricted_tool_schemas() -> bool:
    schemas = {
        tool["name"]: tool["input_schema"]["properties"]
        for tool in _AGENT_TOOLS
    }
    passed = (
        set(schemas["run_query"]) == {"page_id"}
        and set(schemas["make_chart"]) == {"type"}
        and schemas["set_filter"]["value"].get("type") == "string"
    )
    return report("agent query/chart schemas exclude model filters and chart data", passed)


def test_status_endpoint() -> bool:
    response = backend_main.app
    from fastapi.testclient import TestClient

    payload_response = TestClient(response).get("/api/llm/status")
    payload = payload_response.json()
    required = {
        "provider",
        "model",
        "key_configured",
        "cache_enabled",
        "cache_hits",
        "cache_misses",
        "max_rpm",
    }
    passed = (
        payload_response.status_code == 200
        and set(payload) == required
        and "api_key" not in payload
        and "GEMINI_API_KEY" not in payload
    )
    return report("LLM status endpoint reports safe configuration only", passed)


def test_cache() -> bool:
    fake_http = FakeHTTP([FakeResponse(200, _success_payload())])
    with tempfile.TemporaryDirectory() as temporary:
        client = llm.LLMClient(
            http_client=fake_http,
            cache_dir=Path(temporary),
            model="test-model",
            api_key="test-api-key",
            max_rpm=10000,
            call_timeout_s=2,
        )
        history = [{"role": "user", "text": "hello"}]
        first = client.generate("system", history, [])
        second = client.generate("system", history, [])
    passed = (
        len(fake_http.calls) == 1
        and not first.cached
        and second.cached
        and client.cache_misses == 1
        and client.cache_hits == 1
        and second.text == "ok"
    )
    return report("identical Gemini request returns a disk-cached reply", passed)


def test_retry() -> bool:
    fake_http = FakeHTTP([
        FakeResponse(429, {"error": {"message": "busy"}}, {"Retry-After": "0"}),
        FakeResponse(200, _success_payload()),
    ])
    sleeps: list[float] = []
    original_sleep = llm.time.sleep
    try:
        llm.time.sleep = lambda seconds: sleeps.append(seconds)
        client = llm.LLMClient(
            http_client=fake_http,
            cache_enabled=False,
            model="test-model",
            api_key="test-api-key",
            max_rpm=10000,
            call_timeout_s=2,
        )
        reply = client.generate("system", [{"role": "user", "text": "hello"}], [])
    finally:
        llm.time.sleep = original_sleep
    passed = len(fake_http.calls) == 2 and not reply.cached and sleeps == [0.0]
    return report("Gemini 429 is retried before success", passed)


def test_rate_limiter() -> bool:
    clock = [100.0]
    sleeps: list[float] = []
    original_monotonic = llm.time.monotonic
    original_sleep = llm.time.sleep
    try:
        llm.time.monotonic = lambda: clock[0]

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        llm.time.sleep = fake_sleep
        limiter = llm._RollingRateLimiter(1)
        limiter.acquire(61)
        first = limiter._calls[-1]
        limiter.acquire(61)
        second = limiter._calls[-1]
    finally:
        llm.time.monotonic = original_monotonic
        llm.time.sleep = original_sleep
    passed = len(sleeps) == 1 and sleeps[0] >= 60 and second - first >= 60
    return report("rolling rate limiter spaces calls by one minute at 1 RPM", passed)


def test_multi_function_response_and_raw_history() -> bool:
    parts = [
        {"functionCall": {"name": "navigate", "args": {"page_id": "revenue_by_region"}}},
        {"functionCall": {"name": "run_query", "args": {"page_id": "revenue_by_region"}}},
    ]
    fake_http = FakeHTTP([FakeResponse(200, _success_payload(parts))])
    client = llm.LLMClient(
        http_client=fake_http,
        model="test-model",
        api_key="test-api-key",
        cache_enabled=False,
        max_rpm=10000,
    )
    reply = client.generate("system", [{"role": "user", "text": "go"}], [])
    # Verify the history formatter preserves signed/provider-specific parts verbatim.
    raw_parts = [{"text": "continue", "thoughtSignature": "opaque-signature"}]
    content = client._gemini_contents([{
        "role": "assistant",
        "text": "continue",
        "tool_calls": reply.tool_calls,
        "raw": raw_parts,
    }])
    results = client._gemini_contents([{
        "role": "tool",
        "results": [
            {"id": "one", "name": "navigate", "output": {"ok": True}},
            {"id": "two", "name": "run_query", "output": {"rows": []}},
        ],
    }])
    passed = len(reply.tool_calls) == 2 and content[0]["role"] == "model" and content[0]["parts"] is raw_parts and [
        part["functionResponse"]["name"] for part in results[0]["parts"]
    ] == ["navigate", "run_query"]
    return report("assistant raw parts and ordered function responses are preserved", passed)


def test_live_gemini() -> bool:
    client = llm.get_llm_client()
    if not client.api_key or not client.model:
        missing = []
        if not client.api_key:
            missing.append("GEMINI_API_KEY")
        if not client.model:
            missing.append("GEMINI_MODEL")
        return report("live Gemini checks skipped", True, f"missing in .env: {', '.join(missing)}")

    try:
        client.generate("ping", [{"role": "user", "text": "ping"}], [], bypass_cache=True)
    except (llm.LLMUnavailable, llm.LLMRateLimited, llm.LLMBadResponse) as error:
        return report(
            "live Gemini checks skipped",
            True,
            f"Gemini API unavailable with credentials in .env ({error})",
        )

    first = run_agent("Show South revenue this quarter", "admin")
    after_first_hits = client.cache_hits
    after_first_misses = client.cache_misses
    second = run_agent("Show South revenue this quarter", "admin")
    cache_delta = client.cache_hits - after_first_hits
    answer_matches = second.get("answer") == first.get("answer")
    passed = (
        bool(first.get("plan"))
        and first.get("evidence", {}).get("page", {}).get("id") == "revenue_by_region"
        and bool(first.get("answer"))
        and answer_matches
        and cache_delta > 0
    )
    print(f"Live plan: {first.get('plan')}")
    print(f"Live answer: {first.get('answer')}")
    print(f"Live evidence: {first.get('evidence')}")
    check_one = report(
        "live Gemini South revenue request and repeated-call cache hit",
        passed,
        f"cache_enabled={client.cache_enabled}, cache_hits_after_first={after_first_hits}, "
        f"cache_hits_after_second={client.cache_hits}, cache_misses_after_first={after_first_misses}, "
        f"cache_misses_after_second={client.cache_misses}, answers_match={answer_matches}, "
        f"agent_uses_same_client={agent_module.get_llm_client() is client}",
    )

    payroll = run_agent("Open Payroll Forecast", "admin")
    has_navigate = any(step.get("tool") == "navigate" for step in payroll.get("plan", []))
    error = payroll.get("error") or {}
    suggestions = error.get("suggestions", [])
    check_two = report(
        "live Gemini rejects nonexistent Payroll Forecast with suggestions",
        not has_navigate and bool(suggestions),
        f"plan={payroll.get('plan')}, suggestions={suggestions}",
    )
    return check_one and check_two


def main() -> None:
    checks = [
        test_schema_conversion(),
        test_restricted_tool_schemas(),
        test_status_endpoint(),
        test_cache(),
        test_retry(),
        test_rate_limiter(),
        test_multi_function_response_and_raw_history(),
        test_live_gemini(),
    ]
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
