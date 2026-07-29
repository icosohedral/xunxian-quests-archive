"""导出任务站与资源资料站之间的轻量关系文件。"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


QUEST_SITE_BASE_URL = "https://quests.xunxian.wiki"


def _open_read_only(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _required_tables_exist(connection: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    required = {
        "build_meta",
        "quest",
        "quest_reward",
        "quest_condition",
        "quest_objective",
        "quest_endpoint",
    }
    missing = required - tables
    if missing:
        raise ValueError(f"任务数据库缺少导出所需表：{sorted(missing)}")


def _candidate_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    specifications = [
        (
            """
            SELECT
                CASE reward.object_type_id
                    WHEN 2 THEN 'item'
                    WHEN 21 THEN 'title'
                END AS resource_kind,
                reward.object_id AS resource_id,
                reward.quest_id,
                quest.quest_name,
                CASE reward.object_type_id
                    WHEN 2 THEN 'reward'
                    WHEN 21 THEN 'title_reward'
                END AS relation_type,
                reward.amount,
                reward.source_file,
                reward.source_row
            FROM quest_reward AS reward
            JOIN quest
              ON quest.quest_id = reward.quest_id
             AND quest.version_no = reward.version_no
            WHERE reward.object_type_id IN (2, 21)
              AND reward.object_id IS NOT NULL
              AND reward.object_id >= 0
            """,
            "reward",
        ),
        (
            """
            SELECT
                CASE condition.object_type_id
                    WHEN 2 THEN 'quest_item'
                    WHEN 21 THEN 'title'
                END AS resource_kind,
                condition.object_id AS resource_id,
                condition.quest_id,
                quest.quest_name,
                'required' AS relation_type,
                NULL AS amount,
                condition.source_file,
                condition.source_row
            FROM quest_condition AS condition
            JOIN quest
              ON quest.quest_id = condition.quest_id
             AND quest.version_no = condition.version_no
            WHERE condition.object_type_id IN (2, 21)
              AND condition.object_id IS NOT NULL
              AND condition.object_id >= 0
            """,
            "condition",
        ),
        (
            """
            SELECT
                'quest_item' AS resource_kind,
                objective.object_id AS resource_id,
                objective.quest_id,
                quest.quest_name,
                'objective' AS relation_type,
                objective.amount,
                objective.source_file,
                objective.source_row
            FROM quest_objective AS objective
            JOIN quest
              ON quest.quest_id = objective.quest_id
             AND quest.version_no = objective.version_no
            WHERE objective.object_type_id = 2
              AND objective.object_id IS NOT NULL
              AND objective.object_id >= 0
            """,
            "objective",
        ),
        (
            """
            SELECT
                'quest_item' AS resource_kind,
                endpoint.object_id AS resource_id,
                endpoint.quest_id,
                quest.quest_name,
                CASE endpoint.endpoint_kind
                    WHEN 'accept' THEN 'accept_endpoint'
                    WHEN 'submit' THEN 'submit_endpoint'
                END AS relation_type,
                NULL AS amount,
                endpoint.source_file,
                endpoint.source_row
            FROM quest_endpoint AS endpoint
            JOIN quest
              ON quest.quest_id = endpoint.quest_id
             AND quest.version_no = endpoint.version_no
            WHERE endpoint.object_type_id = 2
              AND endpoint.object_id IS NOT NULL
              AND endpoint.object_id >= 0
            """,
            "endpoint",
        ),
    ]
    for query, source_table in specifications:
        for row in connection.execute(query):
            item = dict(row)
            item["_source_table"] = source_table
            candidates.append(item)
    return candidates


def export_resource_links(
    *,
    database_path: Path,
    output_path: Path,
    report_path: Path | None = None,
    quest_site_base_url: str = QUEST_SITE_BASE_URL,
) -> dict[str, Any]:
    """从发布数据库读取关系并输出版本化小型 JSON，不复制数据库。"""
    if not database_path.is_file():
        raise FileNotFoundError(f"任务数据库不存在：{database_path}")
    connection = _open_read_only(database_path)
    try:
        _required_tables_exist(connection)
        candidates = _candidate_rows(connection)
        created_at_row = connection.execute(
            "SELECT value FROM build_meta WHERE key='created_at'"
        ).fetchone()
        generated_at = (
            created_at_row[0] if created_at_row else "1970-01-01T00:00:00Z"
        )
    finally:
        connection.close()

    candidates.sort(
        key=lambda item: (
            item["resource_kind"],
            item["resource_id"],
            item["quest_id"],
            item["relation_type"],
            item["source_file"],
            item["source_row"],
        )
    )
    links_by_identity: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    duplicate_candidates = 0
    source_counts: Counter[str] = Counter()
    for candidate in candidates:
        identity = (
            candidate["resource_kind"],
            candidate["resource_id"],
            candidate["quest_id"],
            candidate["relation_type"],
        )
        source_counts[candidate.pop("_source_table")] += 1
        if identity in links_by_identity:
            duplicate_candidates += 1
            continue
        link = {
            "resource_kind": candidate["resource_kind"],
            "resource_id": candidate["resource_id"],
            "quest_id": candidate["quest_id"],
            "quest_name": candidate["quest_name"],
            "relation_type": candidate["relation_type"],
            "source_file": candidate["source_file"],
            "source_row": candidate["source_row"],
            "quest_site_path": f"/quests/{candidate['quest_id']}",
        }
        if candidate["amount"] is not None and candidate["amount"] > 0:
            link["amount"] = candidate["amount"]
        links_by_identity[identity] = link

    links = list(links_by_identity.values())
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "quest_site_base_url": quest_site_base_url.rstrip("/"),
        "links": links,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = {
        "schema_version": 1,
        "database_path": database_path.name,
        "generated_at": generated_at,
        "candidate_count": len(candidates),
        "link_count": len(links),
        "duplicate_candidate_count": duplicate_candidates,
        "source_counts": dict(sorted(source_counts.items())),
        "relation_counts": dict(
            sorted(Counter(link["relation_type"] for link in links).items())
        ),
        "resource_kind_counts": dict(
            sorted(Counter(link["resource_kind"] for link in links).items())
        ),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report
