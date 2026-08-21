from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_ENTRIES = 1500


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.fresh_file = not path.exists()
        self._data: dict = {"version": 1, "seen": {}, "last_run": None}
        if not self.fresh_file:
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded.get("seen"), dict):
                    self._data = loaded
            except (json.JSONDecodeError, OSError):
                self.fresh_file = True

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def is_seen(self, key: str) -> bool:
        return key in self._data["seen"]

    def mark_seen(self, key: str) -> None:
        self._data["seen"][key] = self._now()

    def prune(self, limit: int = MAX_ENTRIES) -> None:
        seen = self._data["seen"]
        if len(seen) <= limit:
            return
        newest_first = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
        self._data["seen"] = dict(newest_first[:limit])

    def tracked_count(self) -> int:
        return len(self._data["seen"])

    def save(self) -> None:
        self._data["last_run"] = self._now()
        self.prune()
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=1, ensure_ascii=True)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
