from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from questdb.resource_links import export_resource_links


def _build_fixture(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO build_meta VALUES
                ('created_at', '2026-07-28T00:00:00Z');

            CREATE TABLE quest (
                quest_id INTEGER,
                version_no INTEGER,
                quest_name TEXT
            );
            INSERT INTO quest VALUES (800001, 1, '合成任务');

            CREATE TABLE quest_reward (
                object_type_id INTEGER,
                object_id INTEGER,
                quest_id INTEGER,
                version_no INTEGER,
                amount INTEGER,
                source_file TEXT,
                source_row INTEGER
            );
            INSERT INTO quest_reward VALUES
                (2, 1515, 800001, 1, 2, 'fixtures/quest.tsv', 2),
                (21, 1515, 800001, 1, 1, 'fixtures/quest.tsv', 2);

            CREATE TABLE quest_condition (
                object_type_id INTEGER,
                object_id INTEGER,
                quest_id INTEGER,
                version_no INTEGER,
                source_file TEXT,
                source_row INTEGER
            );
            INSERT INTO quest_condition VALUES
                (2, 1515, 800001, 1, 'fixtures/quest.tsv', 2);

            CREATE TABLE quest_objective (
                object_type_id INTEGER,
                object_id INTEGER,
                quest_id INTEGER,
                version_no INTEGER,
                amount INTEGER,
                source_file TEXT,
                source_row INTEGER
            );
            INSERT INTO quest_objective VALUES
                (2, 1515, 800001, 1, 3, 'fixtures/quest.tsv', 2);

            CREATE TABLE quest_endpoint (
                object_type_id INTEGER,
                object_id INTEGER,
                quest_id INTEGER,
                version_no INTEGER,
                endpoint_kind TEXT,
                source_file TEXT,
                source_row INTEGER
            );
            INSERT INTO quest_endpoint VALUES
                (2, 1515, 800001, 1, 'accept', 'fixtures/quest.tsv', 2);
            """
        )


def test_export_keeps_resource_namespaces_separate(tmp_path: Path) -> None:
    database = tmp_path / "quest.db"
    output = tmp_path / "quest_resource_links.json"
    report_path = tmp_path / "report.json"
    _build_fixture(database)

    report = export_resource_links(
        database_path=database,
        output_path=output,
        report_path=report_path,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert report["link_count"] == 5
    assert {
        (
            link["resource_kind"],
            link["resource_id"],
            link["relation_type"],
        )
        for link in payload["links"]
    } == {
        ("item", 1515, "reward"),
        ("title", 1515, "title_reward"),
        ("quest_item", 1515, "required"),
        ("quest_item", 1515, "objective"),
        ("quest_item", 1515, "accept_endpoint"),
    }
    assert payload["quest_site_base_url"] == "https://quests.xunxian.wiki"
    assert all(
        link["quest_site_path"] == "/quests/800001"
        for link in payload["links"]
    )
