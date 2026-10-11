from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

IDLE_TIMEOUT_SECONDS = 3600.0  # 60 minutes
MAX_SESSIONS = 200
MAX_TURNS_PER_SESSION = 6


@dataclass
class Session:
    session_id: str
    role: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)

    def add_turn(self, turn: dict[str, Any]) -> None:
        self.turns.append(turn)
        if len(self.turns) > MAX_TURNS_PER_SESSION:
            self.turns = self.turns[-MAX_TURNS_PER_SESSION:]
        self.last_active = time.time()

    def is_expired(self, timeout_s: float = IDLE_TIMEOUT_SECONDS) -> bool:
        return (time.time() - self.last_active) > timeout_s

    def reset(self, new_role: str) -> None:
        self.role = new_role
        self.turns = []
        self.last_active = time.time()

    @property
    def last_turn(self) -> dict[str, Any] | None:
        return self.turns[-1] if self.turns else None


class SessionStore:
    def __init__(self, max_sessions: int = MAX_SESSIONS, idle_timeout_s: float = IDLE_TIMEOUT_SECONDS):
        self._max_sessions = max_sessions
        self._idle_timeout_s = idle_timeout_s
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _cleanup_locked(self) -> None:
        # 1. Evict idle / expired sessions
        now = time.time()
        expired_ids = [
            sid for sid, s in self._sessions.items()
            if (now - s.last_active) > self._idle_timeout_s
        ]
        for sid in expired_ids:
            self._sessions.pop(sid, None)

        # 2. If still exceeding capacity, evict the least recently active session(s)
        if len(self._sessions) > self._max_sessions:
            sorted_by_activity = sorted(
                self._sessions.items(),
                key=lambda item: item[1].last_active,
            )
            to_remove = len(self._sessions) - self._max_sessions
            for sid, _ in sorted_by_activity[:to_remove]:
                self._sessions.pop(sid, None)

    def get_or_create(self, session_id: str | None, role: str) -> Session:
        with self._lock:
            self._cleanup_locked()

            if not session_id:
                # Generate new unique session ID
                new_id = f"sess_{uuid.uuid4().hex[:12]}"
                session = Session(session_id=new_id, role=role)
                self._sessions[new_id] = session
                self._cleanup_locked()
                return session

            existing = self._sessions.get(session_id)
            if existing is None:
                session = Session(session_id=session_id, role=role)
                self._sessions[session_id] = session
                self._cleanup_locked()
                return session

            # If existing session expired, reset it
            if existing.is_expired(self._idle_timeout_s):
                existing.reset(role)
                return existing

            # If role changed, reset session (no memory carried across roles)
            if existing.role != role:
                existing.reset(role)
                return existing

            existing.last_active = time.time()
            return existing

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            self._cleanup_locked()
            return self._sessions.get(session_id)

    def record_turn(self, session_id: str, role: str, turn: dict[str, Any]) -> Session:
        with self._lock:
            session = self.get_or_create(session_id, role)
            session.add_turn(turn)
            return session

    def reset_session(self, session_id: str, role: str) -> Session:
        with self._lock:
            session = self.get_or_create(session_id, role)
            session.reset(role)
            return session

    def count(self) -> int:
        with self._lock:
            self._cleanup_locked()
            return len(self._sessions)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


# Global singleton instance
_GLOBAL_STORE = SessionStore()


def get_session_store() -> SessionStore:
    return _GLOBAL_STORE
