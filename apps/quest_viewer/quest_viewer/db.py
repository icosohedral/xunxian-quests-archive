from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


REQUIRED_VIEWS = {
    "quest_full",
    "quest_text_detail",
    "quest_npc_detail",
    "quest_reward_detail",
    "quest_relation_detail",
    "quest_location_detail",
}

REQUIRED_TABLES = {
    "character_call_profile",
    "character_call_variant",
}


def connect_readonly(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise FileNotFoundError(f"任务数据库不存在：{database_path}")
    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def readonly_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect_readonly(database_path)
    try:
        yield connection
    finally:
        connection.close()


def database_health(database_path: Path) -> dict[str, object]:
    with readonly_connection(database_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        views = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
        }
        missing_views = sorted(REQUIRED_VIEWS - views)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing_tables = sorted(REQUIRED_TABLES - tables)
        quest_count = connection.execute(
            "SELECT COUNT(DISTINCT quest_id) FROM quest"
        ).fetchone()[0]
    return {
        "status": (
            "ok"
            if integrity == "ok" and not missing_views and not missing_tables
            else "failed"
        ),
        "mode": "read-only",
        "integrity": integrity,
        "missing_views": missing_views,
        "missing_tables": missing_tables,
        "quest_count": quest_count,
        "database": database_path.name,
    }
