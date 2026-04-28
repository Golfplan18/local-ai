"""
sidebar_window.py — Sidebar Five-Turn Rolling Window (Phase 13.1)

Implements a rolling window of five turn pairs maximum for sidebar
conversations. After each exchange, if the history exceeds five pairs,
the oldest pair is removed. History lives only in session memory —
never written to disk or ChromaDB. Discarded on session end.

Why: Sidebar is currently fully stateless (single message only). Five
turns provides minimal conversational continuity for multi-step quick
queries without permanent storage overhead.

Usage:
    from orchestrator.tools.sidebar_window import SidebarWindow
    window = SidebarWindow()
    window.add_exchange(user_msg, assistant_msg)
    history = window.get_history()  # returns list of message dicts
"""

from __future__ import annotations

from dataclasses import dataclass, field


MAX_TURNS = 5


@dataclass
class SidebarWindow:
    """
    Five-turn rolling window for sidebar conversations.

    In-memory only — never persisted to disk or ChromaDB.
    Automatically discarded when the session ends.
    """
    _turns: list[tuple[str, str]] = field(default_factory=list)
    max_turns: int = MAX_TURNS

    def add_exchange(self, user_message: str, assistant_message: str):
        """Add a turn pair. Evicts oldest if at capacity."""
        self._turns.append((user_message, assistant_message))
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def get_history(self) -> list[dict]:
        """Return history as a list of message dicts for model context."""
        messages = []
        for user_msg, asst_msg in self._turns:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": asst_msg})
        return messages

    def get_turn_count(self) -> int:
        """Return the number of turn pairs in the window."""
        return len(self._turns)

    def clear(self):
        """Clear all history (called on session end)."""
        self._turns.clear()

    def is_empty(self) -> bool:
        return len(self._turns) == 0


# Global sidebar windows, keyed by panel_id
_sidebar_windows: dict[str, SidebarWindow] = {}


def get_sidebar_window(panel_id: str = "sidebar") -> SidebarWindow:
    """Get or create a sidebar window for a panel."""
    if panel_id not in _sidebar_windows:
        _sidebar_windows[panel_id] = SidebarWindow()
    return _sidebar_windows[panel_id]


def clear_sidebar_window(panel_id: str = "sidebar"):
    """Clear a sidebar window (on session end or panel close)."""
    if panel_id in _sidebar_windows:
        _sidebar_windows[panel_id].clear()


def clear_all_sidebar_windows():
    """Clear all sidebar windows (on server restart)."""
    _sidebar_windows.clear()
