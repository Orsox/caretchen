from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_FILE_NAME = "history.json"
_MAX_ENTRIES = 50


@dataclass
class HistoryEntry:
    timestamp: str  # ISO 8601
    raw_text: str
    refined_text: str
    was_refined: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        return cls(
            timestamp=str(data.get("timestamp", "")),
            raw_text=str(data.get("raw_text", "")),
            refined_text=str(data.get("refined_text", "")),
            was_refined=bool(data.get("was_refined", False)),
        )


class DictationHistory:
    """Thread-safe history of dictation results with JSON persistence."""

    def __init__(self, history_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._entries: list[HistoryEntry] = []
        self._max_entries = _MAX_ENTRIES

        if history_path is None:
            history_path = Path(__file__).resolve().parent.parent / "data" / HISTORY_FILE_NAME

        self._history_path = history_path
        self._load()

    @property
    def entries(self) -> list[HistoryEntry]:
        with self._lock:
            return list(self._entries)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def add(self, raw_text: str, refined_text: str, was_refined: bool) -> None:
        entry = HistoryEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_text=raw_text,
            refined_text=refined_text,
            was_refined=was_refined,
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]
        self._save()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
        self._save()

    def _load(self) -> None:
        if not self._history_path.exists():
            return
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                with self._lock:
                    self._entries = [HistoryEntry.from_dict(item) for item in data[-_MAX_ENTRIES:]]
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = [e.to_dict() for e in self._entries]
            self._history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
