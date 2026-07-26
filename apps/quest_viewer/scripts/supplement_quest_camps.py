from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE = (
    WORKSPACE_ROOT
    / "outputs"
    / "quest_database"
    / "releases"
    / "1.0.1"
    / "quest.db"
)
DEFAULT_SOURCE = WORKSPACE_ROOT / "original_data" / "mb" / "camp" / "camp.txt"


def supplement(database_path: Path, source_path: Path) -> tuple[int, int]:
    source_rows: dict[int, tuple[str, list[str], int, str]] = {}
    for source_row, raw_line in enumerate(
        source_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        fields = raw_line.split("\t")
        if len(fields) < 2 or not fields[1].strip().isdigit():
            continue
        camp_id = int(fields[1].strip())
        source_rows[camp_id] = (fields[0].strip(), fields, source_row, raw_line)

    with sqlite3.connect(database_path) as connection:
        missing_ids = {
            int(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT reward.object_id
                FROM quest_reward reward
                LEFT JOIN quest_camp camp ON camp.camp_id=reward.object_id
                WHERE reward.object_type_id=15
                  AND reward.object_id IS NOT NULL
                  AND camp.camp_id IS NULL
                """
            )
        }
        unavailable_ids = missing_ids - source_rows.keys()
        if unavailable_ids:
            raise RuntimeError(
                f"完整阵营表仍缺少这些奖励引用：{sorted(unavailable_ids)}"
            )
        inserted = 0
        for camp_id in sorted(missing_ids):
            camp_name, fields, source_row, raw_line = source_rows[camp_id]
            connection.execute(
                """
                INSERT INTO quest_camp (
                    camp_id, camp_name, raw_values_json,
                    source_file, source_row, raw_value, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camp_id,
                    camp_name,
                    json.dumps(fields, ensure_ascii=False),
                    "mb/camp/camp.txt",
                    source_row,
                    raw_line,
                    "manual-camp-supplement-20260725",
                ),
            )
            inserted += 1
        connection.commit()
        affected_tasks = int(
            connection.execute(
                f"""
                SELECT COUNT(DISTINCT quest_id)
                FROM quest_reward
                WHERE object_type_id=15
                  AND object_id IN ({",".join("?" for _ in missing_ids)})
                """,
                tuple(sorted(missing_ids)),
            ).fetchone()[0]
            if missing_ids
            else 0
        )
    return inserted, affected_tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    inserted, affected_tasks = supplement(args.database, args.source)
    print(
        f"补充阵营 {inserted} 条；修复任务 {affected_tasks} 个",
        flush=True,
    )


if __name__ == "__main__":
    main()
