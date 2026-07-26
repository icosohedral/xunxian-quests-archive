from __future__ import annotations

import sqlite3
from pathlib import Path

from questdb.normalized import init_database, load_character_calls


SCHEMA_PATH = Path(__file__).parents[1] / "src" / "questdb" / "schema.sql"
WORKSPACE_ROOT = Path(__file__).parents[1]


def build_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return connection


def test_required_tables_exist() -> None:
    connection = build_database()
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    required = {
        "quest",
        "quest_text",
        "character_call_profile",
        "character_call_variant",
        "quest_category",
        "object_type",
        "quest_condition",
        "quest_objective",
        "quest_reward",
        "quest_relation",
        "quest_npc",
        "quest_target",
        "quest_item_source",
        "quest_precondition_group",
        "object_mapping",
        "location_context",
        "area_source",
        "unresolved_reference",
        "external_dependency",
        "load_audit",
    }
    assert required <= tables


def test_quest_has_composite_primary_key_and_audit_columns() -> None:
    connection = build_database()
    columns = {
        row[1]: row for row in connection.execute("PRAGMA table_info(quest)")
    }
    assert columns["quest_id"][5] == 1
    assert columns["version_no"][5] == 2
    for name in ("source_file", "source_row", "raw_value", "run_id"):
        assert name in columns
        assert columns[name][3] == 1


def test_foreign_keys_are_declared() -> None:
    connection = build_database()
    quest_foreign_tables = {
        row[2] for row in connection.execute("PRAGMA foreign_key_list(quest)")
    }
    endpoint_foreign_tables = {
        row[2]
        for row in connection.execute("PRAGMA foreign_key_list(quest_endpoint)")
    }
    assert {"quest_identity", "quest_category"} <= quest_foreign_tables
    assert {"quest", "object_type"} <= endpoint_foreign_tables


def test_expected_indexes_exist() -> None:
    connection = build_database()
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    assert {
        "idx_quest_name",
        "idx_quest_category",
        "idx_text_source_quest",
        "idx_endpoint_object",
        "idx_reward_object",
    } <= indexes


def test_duplicate_versions_are_preserved() -> None:
    connection = build_database()
    connection.execute(
        "INSERT INTO quest_identity VALUES (11257, 2, 1)"
    )
    connection.execute(
        "INSERT INTO quest_category VALUES (1181, NULL, NULL, NULL, NULL, NULL, 't')"
    )
    template = (
        "INSERT INTO quest (quest_id, version_no, conflict_flag, quest_name, "
        "category_id, raw_values_json, source_file, source_row, raw_value, run_id) "
        "VALUES (11257, ?, 1, ?, 1181, '[]', 'quest_info.txt', ?, ?, 't')"
    )
    connection.execute(template, (1, "孟浪多疑10", 6211, "v1"))
    connection.execute(template, (2, "孟浪多疑11", 6212, "v2"))
    assert connection.execute(
        "SELECT COUNT(*) FROM quest WHERE quest_id=11257"
    ).fetchone()[0] == 2


def test_foreign_key_check_is_clean_for_empty_schema() -> None:
    connection = build_database()
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_character_call_profiles_are_loaded_losslessly(tmp_path: Path) -> None:
    database_path = tmp_path / "quest.db"
    report_path = tmp_path / "character_calls.json"
    init_database(database_path, run_id="test-character-calls")
    report = load_character_calls(
        root=WORKSPACE_ROOT / "original_data",
        db_path=database_path,
        report_path=report_path,
        run_id="test-character-calls",
    )
    assert report["profile_count"] == 60
    assert report["variant_count"] == 840

    connection = sqlite3.connect(database_path)
    try:
        profile = connection.execute(
            """
            SELECT speaker_profile_name, variant_count
            FROM character_call_profile
            WHERE call_profile_id=18
            """
        ).fetchone()
        variants = connection.execute(
            """
            SELECT call_text
            FROM character_call_variant
            WHERE call_profile_id=18
            ORDER BY variant_no
            """
        ).fetchall()
    finally:
        connection.close()
    assert profile == ("男中-市井老成", 14)
    assert [row[0] for row in variants][:4] == [
        "小家伙",
        "老弟",
        "老弟",
        "老兄",
    ]
