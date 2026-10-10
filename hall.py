"""Names saved after a brain's challenges are all finished."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_ENTRIES = 200
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .'-]{0,23}$")


class Hall:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._load()

    def add(self, name: str, *, level: int, wins: int, heats: int) -> dict:
        clean = clean_name(name)
        entry = {
            "name": clean,
            "level": int(level),
            "wins": int(wins),
            "heats": int(heats),
            "when": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
        self.entries.append(entry)
        del self.entries[:-MAX_ENTRIES]
        self._save()
        return entry

    def public(self) -> list[dict]:
        return list(reversed(self.entries[-30:]))

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        kept = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                kept.append(
                    {
                        "name": clean_name(str(item.get("name", ""))),
                        "level": int(item.get("level", 1)),
                        "wins": int(item.get("wins", 0)),
                        "heats": int(item.get("heats", 0)),
                        "when": str(item.get("when", ""))[:10],
                    }
                )
            except ValueError:
                continue
        return kept[-MAX_ENTRIES:]

    def _save(self) -> None:
        payload = json.dumps(self.entries, indent=2)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(payload)
        temporary.replace(self.path)


def clean_name(name: str) -> str:
    compact = " ".join(str(name).split())
    if not NAME_PATTERN.fullmatch(compact):
        raise ValueError("Use 1 to 24 letters, numbers, spaces, apostrophes, or hyphens.")
    return compact
