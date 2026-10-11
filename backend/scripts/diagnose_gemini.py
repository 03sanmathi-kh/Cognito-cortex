from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

env_path = find_dotenv(usecwd=True)
if not env_path:
    env_path = str(ROOT / ".env")
load_dotenv(env_path, override=True)

from app.agent import _AGENT_TOOLS
from app.llm import convert_tools

api_key = os.getenv("GEMINI_API_KEY", "").strip()
model = os.getenv("GEMINI_MODEL", "").strip()

print(f"Loaded .env path: {env_path}")
print(f"Configured model: {model}")
if api_key:
    masked_key = f"{api_key[:4]}...{api_key[-2:]} (len={len(api_key)})"
    print(f"API key: {masked_key}")
else:
    print("API key: <EMPTY>")


def extract_retry_delay(data: dict[str, Any]) -> str | None:
    error_obj = data.get("error", {})
    details = error_obj.get("details", [])
    for detail in details:
        if isinstance(detail, dict) and detail.get("@type", "").endswith("RetryInfo"):
            return str(detail.get("retryDelay"))
    return None


def execute_call(label: str, payload: dict[str, Any]) -> None:
    print(f"\n--- Call {label} ---")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
        status_code = resp.status_code
        print(f"HTTP Status: {status_code}")
        try:
            body = resp.json()
        except Exception:
            body = {"raw_text": resp.text[:500]}

        if 200 <= status_code < 300:
            candidates = body.get("candidates", [])
            parts = (candidates[0].get("content", {}).get("parts", [])) if candidates else []
            print(f"Success! Response parts: {json.dumps(parts)[:300]}")
        else:
            error_obj = body.get("error", {})
            error_status = error_obj.get("status", "<none>")
            error_message = error_obj.get("message", body.get("raw_text", "<none>"))
            print(f"error.status: {error_status}")
            print(f"error.message: {error_message}")
            retry_delay = extract_retry_delay(body)
            if retry_delay:
                print(f"retryDelay: {retry_delay}")
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                print(f"Retry-After header: {retry_after}")
    except Exception as exc:
        print(f"Exception during request: {type(exc).__name__}: {exc}")


def main() -> None:
    if not api_key or not model:
        print("ERROR: GEMINI_API_KEY or GEMINI_MODEL not set.")
        return

    # Call a: plain text request "Reply with OK" with no tools
    payload_a = {
        "contents": [{"role": "user", "parts": [{"text": "Reply with OK"}]}]
    }
    execute_call("a (plain text 'Reply with OK')", payload_a)

    # Call b: the same request with ONE simple function declaration
    simple_tool = [{
        "functionDeclarations": [{
            "name": "say_hello",
            "description": "Say hello to someone",
            "parameters": {
                "type": "OBJECT",
                "properties": {"name": {"type": "STRING", "description": "The person's name"}},
                "required": ["name"],
            },
        }]
    }]
    payload_b = {
        "contents": [{"role": "user", "parts": [{"text": "Reply with OK"}]}],
        "tools": simple_tool,
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
    }
    execute_call("b (with ONE simple function declaration)", payload_b)

    # Call c: the same as (b) but using our real converted tool schemas from the agent
    real_tools = [{"functionDeclarations": convert_tools(_AGENT_TOOLS)}]
    payload_c = {
        "contents": [{"role": "user", "parts": [{"text": "Reply with OK"}]}],
        "tools": real_tools,
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
    }
    execute_call("c (with real converted tool schemas from agent)", payload_c)


if __name__ == "__main__":
    main()
