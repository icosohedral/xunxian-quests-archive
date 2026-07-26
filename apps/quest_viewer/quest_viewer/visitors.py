from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


class DailyVisitorCounter:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_visit (
                visit_day TEXT PRIMARY KEY,
                visitor_count INTEGER NOT NULL CHECK (visitor_count >= 0)
            );
            CREATE TABLE IF NOT EXISTS daily_visitor (
                visit_day TEXT NOT NULL,
                visitor_id TEXT NOT NULL,
                PRIMARY KEY (visit_day, visitor_id)
            );
            """
        )

    def count(self) -> int:
        today = datetime.now(CHINA_TIMEZONE).date().isoformat()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT visitor_count
                FROM daily_visit
                WHERE visit_day=?
                """,
                (today,),
            ).fetchone()
        return int(row[0]) if row else 0

    def record(self, visitor_id: str) -> tuple[int, str, bool]:
        today = datetime.now(CHINA_TIMEZONE).date().isoformat()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path, timeout=10) as connection:
            self._ensure_schema(connection)
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO daily_visitor (visit_day, visitor_id)
                VALUES (?, ?)
                """,
                (today, visitor_id),
            ).rowcount
            if inserted:
                connection.execute(
                    """
                    INSERT INTO daily_visit (visit_day, visitor_count)
                    VALUES (?, 1)
                    ON CONFLICT(visit_day) DO UPDATE
                    SET visitor_count=visitor_count + 1
                    """,
                    (today,),
                )
            row = connection.execute(
                """
                SELECT visitor_count
                FROM daily_visit
                WHERE visit_day=?
                """,
                (today,),
            ).fetchone()
        return (int(row[0]) if row else 0), today, bool(inserted)
