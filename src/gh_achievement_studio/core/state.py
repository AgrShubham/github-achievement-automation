"""Application local state and checkpoint persistence in %LOCALAPPDATA%."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "GitHubAchievementStudio"
    return Path.home() / ".github-achievement-studio"


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (default_app_dir() / "state.json")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        current.update(patch)
        self.save(current)
        return current
