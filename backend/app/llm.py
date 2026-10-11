from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = ""
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_SCHEMA_TYPES = {"OBJECT", "ARRAY", "STRING", "NUMBER", "INTEGER", "BOOLEAN"}


class LLMError(Exception):
    """Base class for language model failures."""


class LLMConfigError(LLMError):
    """Raised when provider configuration is incomplete or unsupported."""


class LLMRateLimited(LLMError):
    """Raised after Gemini rate-limit retries are exhausted."""


class LLMUnavailable(LLMError):
    """Raised when Gemini cannot be reached or does not accept a request."""


class LLMBadResponse(LLMError):
    """Raised when Gemini returns a response in an unsupported shape."""


@dataclass(frozen=True)
class ToolCall:
    """Provider-neutral function invocation."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMReply:
    """Normalized model response with provider content retained for replay."""

    text: str
    tool_calls: list[ToolCall]
    raw_content: Any
    usage: dict[str, Any]
    cached: bool
    latency_ms: float


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, ToolCall):
        return asdict(value)
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Unsupported value in LLM request: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _convert_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a neutral JSON schema to Gemini's supported schema subset."""
    raw_type = str(schema.get("type", "STRING")).upper()
    gemini_type = raw_type if raw_type in _SCHEMA_TYPES else "STRING"
    converted: dict[str, Any] = {"type": gemini_type}

    for key in ("description", "enum", "format", "nullable"):
        if key in schema:
            converted[key] = schema[key]
    if gemini_type == "OBJECT":
        converted["properties"] = {
            str(name): _convert_schema(value if isinstance(value, dict) else {})
            for name, value in schema.get("properties", {}).items()
        }
        if schema.get("required"):
            converted["required"] = list(schema["required"])
    elif gemini_type == "ARRAY":
        items = schema.get("items")
        converted["items"] = _convert_schema(items if isinstance(items, dict) else {})
    return converted


def convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert neutral function declarations to Gemini declarations."""
    declarations = []
    for tool in tools:
        declarations.append({
            "name": str(tool["name"]),
            "description": str(tool.get("description", "")),
            "parameters": _convert_schema(tool.get("input_schema", {})),
        })
    return declarations


class _RollingRateLimiter:
    """Thread-safe rolling-window request limiter."""

    def __init__(self, max_rpm: int):
        self.max_rpm = max(1, max_rpm)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.max_rpm:
                    self._calls.append(now)
                    return
                wait_s = max(0.0, 60 - (now - self._calls[0]))
                remaining = deadline - now
                if remaining <= 0 or wait_s > remaining:
                    raise LLMUnavailable("The Gemini request rate limiter timed out waiting for capacity.")
                time.sleep(min(wait_s, remaining))


def _retry_delay(response: Any, attempt: int) -> float:
    retry_after = getattr(response, "headers", {}).get("Retry-After")
    if retry_after:
        try:
            return min(20.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    try:
        body = response.json()
        details = body.get("error", {}).get("details", [])
        for detail in details:
            if detail.get("@type", "").endswith("RetryInfo"):
                match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
                if match:
                    return min(20.0, float(match.group(1)))
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return min(20.0, (0.5 * (2 ** attempt)) + random.uniform(0.0, 0.25))


def _format_gemini_error(status_code: int, response: Any) -> str:
    """Format Google's error response safely without leaking credentials."""
    status_str = ""
    message_str = ""
    try:
        body = response.json()
        error_obj = body.get("error", {})
        status_str = str(error_obj.get("status", "")).strip()
        message_str = str(error_obj.get("message", "")).strip()
    except Exception:
        message_str = getattr(response, "text", "")[:300].strip()

    if status_str and message_str:
        return f"Gemini {status_code} {status_str}: {message_str}"
    if message_str:
        return f"Gemini {status_code}: {message_str}"
    return f"Gemini HTTP {status_code}"


class LLMClient:
    """Provider-agnostic LLM interface currently backed by Gemini REST."""

    def __init__(
        self,
        *,
        http_client: Any | None = None,
        cache_dir: Path | None = None,
        max_rpm: int | None = None,
        call_timeout_s: float | None = None,
        cache_enabled: bool | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        api_key: str | None = None,
    ):
        self.provider = (provider if provider is not None else os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
        self.model = (model if model is not None else os.getenv("GEMINI_MODEL", DEFAULT_MODEL)).strip()
        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        try:
            self.temperature = temperature if temperature is not None else float(os.getenv("LLM_TEMPERATURE", "0.1"))
            self.max_rpm = max_rpm if max_rpm is not None else int(os.getenv("LLM_MAX_RPM", "10"))
            self.call_timeout_s = call_timeout_s if call_timeout_s is not None else float(os.getenv("LLM_CALL_TIMEOUT_S", "25"))
        except ValueError as error:
            raise LLMConfigError("Set valid numeric LLM_TEMPERATURE, LLM_MAX_RPM, and LLM_CALL_TIMEOUT_S values in .env.") from error
        self.cache_enabled = cache_enabled if cache_enabled is not None else os.getenv("LLM_CACHE", "1").strip() == "1"
        if self.max_rpm <= 0 or self.call_timeout_s <= 0:
            raise LLMConfigError("LLM_MAX_RPM and LLM_CALL_TIMEOUT_S must be positive values in .env.")
        self.cache_dir = cache_dir or ROOT / "backend" / ".cache" / "llm"
        self._cache_path = self.cache_dir / "responses.sqlite3"
        self._http = http_client if http_client is not None else httpx.Client()
        self._limiter = _RollingRateLimiter(self.max_rpm)
        self._cache_lock = threading.Lock()
        self.cache_hits = 0
        self.cache_misses = 0

    def status(self) -> dict[str, Any]:
        """Return safe runtime status without exposing credentials."""
        return {
            "provider": self.provider,
            "model": self.model,
            "key_configured": bool(self.api_key),
            "cache_enabled": self.cache_enabled,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "max_rpm": self.max_rpm,
        }

    def _validate_config(self) -> None:
        if not self.api_key:
            raise LLMConfigError("Set GEMINI_API_KEY in the project .env file.")
        if not self.model:
            raise LLMConfigError("Set GEMINI_MODEL in the project .env file.")
        if self.provider != "gemini":
            raise LLMConfigError(f"Unsupported LLM_PROVIDER '{self.provider}'; set LLM_PROVIDER=gemini in .env.")

    def _cache_key(self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
        request_data = [self.model, self.temperature, system, history, tools]
        return hashlib.sha256(_canonical_json(request_data).encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> LLMReply | None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self._cache_lock, closing(sqlite3.connect(self._cache_path)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS replies (cache_key TEXT PRIMARY KEY, reply_json TEXT NOT NULL)"
                )
                row = connection.execute("SELECT reply_json FROM replies WHERE cache_key = ?", (key,)).fetchone()
        if row is None:
            self.cache_misses += 1
            return None
        cached = json.loads(row[0])
        self.cache_hits += 1
        return LLMReply(
            text=cached["text"],
            tool_calls=[ToolCall(**call) for call in cached["tool_calls"]],
            raw_content=cached["raw_content"],
            usage=cached["usage"],
            cached=True,
            latency_ms=0.0,
        )

    def _cache_put(self, key: str, reply: LLMReply) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        stored = {
            "text": reply.text,
            "tool_calls": [asdict(call) for call in reply.tool_calls],
            "raw_content": reply.raw_content,
            "usage": reply.usage,
        }
        with self._cache_lock, closing(sqlite3.connect(self._cache_path)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS replies (cache_key TEXT PRIMARY KEY, reply_json TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO replies (cache_key, reply_json) VALUES (?, ?)",
                    (key, _canonical_json(stored)),
                )

    def _gemini_contents(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents = []
        for turn in history:
            role = turn.get("role")
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": str(turn.get("text", ""))}]})
            elif role == "assistant":
                raw_parts = turn.get("raw")
                if raw_parts is not None:
                    parts = raw_parts
                else:
                    parts = []
                    if turn.get("text"):
                        parts.append({"text": turn["text"]})
                    for call in turn.get("tool_calls", []):
                        call_dict = asdict(call) if isinstance(call, ToolCall) else call
                        parts.append({"functionCall": {"name": call_dict["name"], "args": call_dict.get("args", {})}})
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                response_parts = []
                for result in turn.get("results", []):
                    response_parts.append({
                        "functionResponse": {
                            "name": str(result["name"]),
                            "response": result.get("output", {}),
                        }
                    })
                contents.append({"role": "user", "parts": response_parts})
            else:
                raise LLMBadResponse(f"Unsupported conversation history role: {role!r}.")
        return contents

    def _request(self, body: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        deadline = time.monotonic() + timeout_s
        saw_rate_limit = False
        last_error_msg: str | None = None
        for attempt in range(4):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if saw_rate_limit:
                    raise LLMRateLimited(last_error_msg or "Gemini 429 RESOURCE_EXHAUSTED: Rate limit persisted until the request timed out.")
                raise LLMUnavailable(last_error_msg or "The Gemini request timed out before it could complete.")
            self._limiter.acquire(remaining)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMUnavailable("The Gemini request timed out while waiting for rate-limit capacity.")
            try:
                response = self._http.post(
                    _GEMINI_URL.format(model=self.model),
                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                    json=body,
                    timeout=min(self.call_timeout_s, remaining),
                )
            except httpx.TimeoutException as error:
                if attempt == 3:
                    raise LLMUnavailable("The Gemini request timed out after four attempts.") from error
                delay = min(20.0, 0.5 * (2 ** attempt) + random.uniform(0.0, 0.25))
                if delay >= deadline - time.monotonic():
                    raise LLMUnavailable("The Gemini request timed out during retry backoff.") from error
                time.sleep(delay)
                continue
            except httpx.RequestError as error:
                if attempt == 3:
                    raise LLMUnavailable("Gemini could not be reached after four attempts.") from error
                delay = min(20.0, 0.5 * (2 ** attempt) + random.uniform(0.0, 0.25))
                if delay >= deadline - time.monotonic():
                    raise LLMUnavailable("Gemini could not be reached before the request timed out.") from error
                time.sleep(delay)
                continue

            status_code = int(response.status_code)
            if status_code == 429 or status_code >= 500:
                is_429 = status_code == 429
                saw_rate_limit = saw_rate_limit or is_429
                formatted_err = _format_gemini_error(status_code, response)
                last_error_msg = formatted_err

                # Fail fast if quota is permanently 0 or retry delay exceeds retry budget
                if is_429 and ("limit: 0" in formatted_err or "quota exceeded" in formatted_err.lower()):
                    delay = _retry_delay(response, attempt)
                    if delay > 20.0 or "limit: 0" in formatted_err:
                        raise LLMRateLimited(formatted_err)

                if attempt == 3:
                    break
                delay = _retry_delay(response, attempt)
                if delay >= deadline - time.monotonic():
                    break
                time.sleep(delay)
                continue
            if status_code < 200 or status_code >= 300:
                raise LLMUnavailable(_format_gemini_error(status_code, response))
            try:
                return response.json(), (time.perf_counter() - started) * 1000
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise LLMBadResponse("Gemini returned invalid JSON.") from error
        if saw_rate_limit:
            raise LLMRateLimited(last_error_msg or "Gemini 429 RESOURCE_EXHAUSTED: Rate limit persisted after retries.")
        raise LLMUnavailable(last_error_msg or "Gemini remained unavailable after four attempts.")

    def generate(
        self,
        system: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        bypass_cache: bool = False,
        timeout_s: float | None = None,
    ) -> LLMReply:
        """Generate one assistant reply and normalize Gemini's response."""
        self._validate_config()
        cache_key = self._cache_key(system, history, tools)
        if self.cache_enabled and not bypass_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._gemini_contents(history),
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": 2048},
        }
        declarations = convert_tools(tools)
        if declarations:
            body["tools"] = [{"functionDeclarations": declarations}]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        # Ensure all types in body (including date, datetime in tool responses) are JSON-safe
        body = json.loads(_canonical_json(body))

        started = time.perf_counter()
        payload, elapsed_ms = self._request(body, min(timeout_s or self.call_timeout_s, self.call_timeout_s))
        candidate = (payload.get("candidates") or [None])[0]
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise LLMBadResponse("Gemini returned no candidate content parts.")

        text = "\n".join(str(part["text"]) for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)).strip()
        tool_calls = []
        for index, part in enumerate(parts):
            function_call = part.get("functionCall") if isinstance(part, dict) else None
            if not isinstance(function_call, dict) or not isinstance(function_call.get("name"), str):
                continue
            args = function_call.get("args", {})
            if not isinstance(args, dict):
                raise LLMBadResponse("Gemini returned invalid function-call arguments.")
            stable_id = hashlib.sha256(
                f"{self.model}:{_canonical_json(function_call)}:{index}".encode("utf-8")
            ).hexdigest()[:24]
            tool_calls.append(ToolCall(id=f"gemini_{stable_id}", name=function_call["name"], args=args))

        usage_metadata = payload.get("usageMetadata", {})
        if not isinstance(usage_metadata, dict):
            usage_metadata = {}
        reply = LLMReply(
            text=text,
            tool_calls=tool_calls,
            raw_content=parts,
            usage=usage_metadata,
            cached=False,
            latency_ms=elapsed_ms or (time.perf_counter() - started) * 1000,
        )
        if self.cache_enabled and not bypass_cache:
            self._cache_put(cache_key, reply)
        return reply


_CLIENT: LLMClient | None = None
_CLIENT_LOCK = threading.Lock()


def get_llm_client() -> LLMClient:
    """Return the process-wide configured LLM client, refreshing if .env credentials change."""
    global _CLIENT
    with _CLIENT_LOCK:
        if os.getenv("OFFLINE_TESTS") == "1":
            raise LLMUnavailable("Offline test mode: live Gemini calls are disabled.")
        load_dotenv(ROOT / ".env", override=True)
        current_provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
        current_model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip()
        current_key = os.getenv("GEMINI_API_KEY", "").strip()
        if (
            _CLIENT is None
            or _CLIENT.api_key != current_key
            or _CLIENT.model != current_model
            or _CLIENT.provider != current_provider
        ):
            _CLIENT = LLMClient()
        return _CLIENT
