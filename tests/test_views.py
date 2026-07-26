from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "src" / "questdb" / "schema.sql"
VIEWS = ROOT / "src" / "questdb" / "views.sql"


def build_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.executescript(VIEWS.read_text(encoding="utf-8"))
    return connection


def test_expected_views_exist() -> None:
    connection = build_database()
    views = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
    }
    assert {
        "quest_full",
        "quest_text_detail",
        "quest_npc_detail",
        "quest_reward_detail",
        "quest_relation_detail",
        "quest_location_detail",
    } <= views


def test_quest_full_preserves_versions() -> None:
    connection = build_database()
    connection.execute("INSERT INTO quest_identity VALUES (11257, 2, 1)")
    connection.execute(
        "INSERT INTO quest_category VALUES (1181, '任务关闭', NULL, NULL, NULL, NULL, 't')"
    )
    sql = (
        "INSERT INTO quest (quest_id,version_no,conflict_flag,quest_name,category_id,"
        "raw_values_json,source_file,source_row,raw_value,run_id) "
        "VALUES (11257,?,1,?,1181,'[]','f',?,?, 't')"
    )
    connection.execute(sql, (1, "孟浪多疑10", 6211, "v1"))
    connection.execute(sql, (2, "孟浪多疑11", 6212, "v2"))
    rows = connection.execute(
        "SELECT version_no,quest_name FROM quest_full WHERE quest_id=11257 ORDER BY version_no"
    ).fetchall()
    assert rows == [(1, "孟浪多疑10"), (2, "孟浪多疑11")]


def test_views_do_not_pack_multivalue_rows_into_strings() -> None:
    sql = VIEWS.read_text(encoding="utf-8").lower()
    assert "group_concat" not in sql
