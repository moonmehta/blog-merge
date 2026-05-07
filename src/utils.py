"""Utility helpers for feed-mixer."""

from __future__ import annotations

import threading

import requests

from src import config


class SessionManager:
    """Thread-local HTTP session manager."""

    def __init__(self, headers: dict[str, str] | None = None):
        self._sessions: dict[int, requests.Session] = {}
        self._headers: dict[str, str] = headers or {}
        self._headers.update({"User-Agent": config.UA})

    def get(self) -> requests.Session:
        """Get or create a thread-local requests session."""
        thread_id = threading.get_ident()
        if thread_id not in self._sessions:
            session = requests.Session()
            session.headers.update(self._headers)
            self._sessions[thread_id] = session
        return self._sessions[thread_id]

    def close_all(self):
        """Close all thread-local sessions."""
        for session in self._sessions.values():
            session.close()
        self._sessions.clear()
