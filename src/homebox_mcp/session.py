"""Session state management for conversational AI context.

Tracks current working location and last operation for undo support.
Persists to JSON file for restart recovery.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Session:
    """Conversational session state for a single user/connection."""

    current_location: dict[str, Any] | None = None  # {id, name, parent_id, parent_name}
    last_operation: dict[str, Any] | None = None  # {type, entity_type, entity_id, summary, previous_state}
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def set_location(self, location: dict[str, Any]) -> None:
        """Update current working location."""
        self.current_location = location
        self._touch()

    def log_operation(
        self,
        op_type: str,
        entity_type: str,
        entity_id: str,
        summary: str,
        previous_state: dict[str, Any] | None = None,
    ) -> None:
        """Record a mutating operation for potential undo."""
        self.last_operation = {
            "type": op_type,  # create, update, delete
            "entity_type": entity_type,  # item, location
            "entity_id": entity_id,
            "summary": summary,
            "previous_state": previous_state,
        }
        self._touch()

    def clear_last_operation(self) -> None:
        """Clear undo state after undo is performed."""
        self.last_operation = None
        self._touch()

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


class SessionManager:
    """Manages sessions with JSON file persistence."""

    def __init__(self, session_file: str = "/data/sessions.json"):
        self._sessions: dict[str, Session] = {}
        self._file = Path(session_file)

    def get(self, session_id: str = "default") -> Session:
        """Get or create a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = Session()
        return self._sessions[session_id]

    def save(self) -> None:
        """Persist all sessions to disk."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: asdict(s) for sid, s in self._sessions.items()}
        self._file.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        """Load sessions from disk if file exists."""
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                for sid, sdata in data.items():
                    self._sessions[sid] = Session(**sdata)
            except (json.JSONDecodeError, TypeError):
                pass  # Start fresh if file is corrupt
