from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = (
    WORKSPACE_ROOT
    / "outputs"
    / "quest_database"
    / "releases"
    / "1.0.1"
    / "quest.db"
)
DEFAULT_VISITOR_DB_PATH = (
    WORKSPACE_ROOT / "outputs" / "quest_viewer" / "visitor_stats.db"
)


@dataclass(frozen=True)
class Settings:
    database_path: Path
    visitor_database_path: Path
    page_size: int = 5
    max_page_size: int = 50


def load_settings() -> Settings:
    configured = os.environ.get("QUEST_DB_PATH")
    database_path = Path(configured).expanduser() if configured else DEFAULT_DB_PATH
    visitor_configured = os.environ.get("QUEST_VISITOR_DB_PATH")
    visitor_database_path = (
        Path(visitor_configured).expanduser()
        if visitor_configured
        else DEFAULT_VISITOR_DB_PATH
    )
    return Settings(
        database_path=database_path.resolve(),
        visitor_database_path=visitor_database_path.resolve(),
    )
