from __future__ import annotations

import argparse
import base64
import json
import re
import sqlite3
import zlib
from pathlib import Path
from typing import Any

from build_web_database import (
    OUTPUT_DATABASE,
    SOURCE_DATABASE,
    WORKSPACE_ROOT,
    _encode_detail,
    _write_d1_dump,
)


DEFAULT_DELTA_SQL = (
    WORKSPACE_ROOT
    / "apps"
    / "quest_viewer_cloudflare"
    / "data"
    / "quest_web_reward_updates.sql"
)
CAMP_SOURCE = WORKSPACE_ROOT / "original_data" / "mb" / "camp" / "camp.txt"


def _decode_detail(value: str) -> dict[str, Any]:
    return json.loads(
        zlib.decompress(base64.b64decode(value)).decode("utf-8")
    )


def _camp_names() -> dict[int, str]:
    result: dict[int, str] = {}
    for raw_line in CAMP_SOURCE.read_text(encoding="utf-8").splitlines():
        fields = raw_line.split("\t")
        if len(fields) >= 2 and fields[1].strip().isdigit():
            result[int(fields[1].strip())] = fields[0].strip()
    return result


def _experience_by_quest() -> dict[int, tuple[int, str]]:
    result: dict[int, tuple[int, str]] = {}
    with sqlite3.connect(SOURCE_DATABASE) as connection:
        rows = connection.execute(
            """
            SELECT quest_id, raw_values_json
            FROM (
                SELECT quest_id,
                       raw_values_json,
                       ROW_NUMBER() OVER (
                           PARTITION BY quest_id
                           ORDER BY source_row, version_no
                       ) AS rank_no
                FROM quest
            )
            WHERE rank_no=1
            """
        )
        for quest_id, raw_values_json in rows:
            raw_values = json.loads(raw_values_json)
            formula = (
                str(raw_values[75]).strip()
                if len(raw_values) > 75 and raw_values[75]
                else ""
            )
            match = re.fullmatch(r"(?:cp|exp)\*(\d+)", formula)
            if match:
                result[int(quest_id)] = (int(match.group(1)), formula)
    return result


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def refresh(database_path: Path, delta_sql_path: Path) -> tuple[int, int, int]:
    camp_names = _camp_names()
    experience = _experience_by_quest()
    updates: list[tuple[str, int]] = []
    camp_fixes = 0
    experience_additions = 0

    with sqlite3.connect(database_path) as connection:
        rows = list(
            connection.execute(
                "SELECT quest_id, detail_z FROM web_quest ORDER BY quest_id"
            )
        )
        for quest_id, detail_z in rows:
            detail = _decode_detail(detail_z)
            rewards = [
                reward
                for reward in detail.get("rewards", [])
                if reward.get("reward_group") != "experience"
            ]
            changed = len(rewards) != len(detail.get("rewards", []))
            for reward in rewards:
                if reward.get("object_type_id") != 15:
                    continue
                camp_name = camp_names.get(reward.get("object_id"))
                if camp_name and reward.get("object_name") != camp_name:
                    reward["object_name"] = camp_name
                    camp_fixes += 1
                    changed = True
            experience_value = experience.get(int(quest_id))
            if experience_value:
                amount, formula = experience_value
                rewards.append(
                    {
                        "reward_id": None,
                        "reward_group": "experience",
                        "slot_no": 1,
                        "object_type_id": None,
                        "object_type_name": "经验值",
                        "object_id": None,
                        "object_name": "经验值",
                        "amount": amount,
                        "formula": formula,
                    }
                )
                experience_additions += 1
                changed = True
            if not changed:
                continue
            detail["rewards"] = rewards
            encoded = _encode_detail(detail)
            connection.execute(
                "UPDATE web_quest SET detail_z=? WHERE quest_id=?",
                (encoded, quest_id),
            )
            updates.append((encoded, int(quest_id)))
        connection.commit()
        _write_d1_dump(connection)

    statements = [
        (
            "UPDATE web_quest SET detail_z="
            f"{_sql_quote(encoded)} WHERE quest_id={quest_id};"
        )
        for encoded, quest_id in updates
    ]
    delta_sql_path.write_text("\n".join(statements) + "\n", encoding="utf-8")
    return len(updates), camp_fixes, experience_additions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=OUTPUT_DATABASE)
    parser.add_argument("--delta-sql", type=Path, default=DEFAULT_DELTA_SQL)
    args = parser.parse_args()
    updated, camp_fixes, experience_additions = refresh(
        args.database,
        args.delta_sql,
    )
    print(
        f"更新任务 {updated} 个；阵营名称 {camp_fixes} 条；"
        f"经验奖励 {experience_additions} 条",
        flush=True,
    )


if __name__ == "__main__":
    main()
