from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from questdb.parser import parse_text_file


CORE_FILES = {
    "original_data/mb/quest/quest_info.txt",
    "original_data/mb/quest/quest_text.txt",
    "original_data/mb/quest/quest_sort.txt",
    "original_data/mb/quest/quest_object.txt",
    "original_data/mb/quest/quest_npc.txt",
    "original_data/mb/quest/quest_item.txt",
    "original_data/mb/quest/quest_event.txt",
    "original_data/mb/quest/quest_target.txt",
}


SCHEMA = """
CREATE TABLE load_batches (
    run_id TEXT PRIMARY KEY,
    input_root TEXT NOT NULL,
    inventory_path TEXT NOT NULL,
    profiles_path TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);

CREATE TABLE raw_files (
    run_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    encoding TEXT NOT NULL,
    physical_line_count INTEGER NOT NULL,
    loaded_row_count INTEGER NOT NULL,
    loaded_cell_count INTEGER NOT NULL,
    load_status TEXT NOT NULL,
    PRIMARY KEY (run_id, source_file),
    FOREIGN KEY (run_id) REFERENCES load_batches(run_id)
);

CREATE TABLE raw_rows (
    run_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    values_json TEXT NOT NULL,
    line_ending TEXT NOT NULL,
    column_count INTEGER NOT NULL,
    PRIMARY KEY (run_id, source_file, source_row),
    FOREIGN KEY (run_id, source_file)
        REFERENCES raw_files(run_id, source_file)
);

CREATE INDEX raw_rows_source_idx
    ON raw_rows(source_file, source_row);

CREATE VIEW raw_cells AS
SELECT
    rows.run_id AS run_id,
    rows.source_file AS source_file,
    rows.source_row AS source_row,
    CAST(cells.key AS INTEGER) + 1 AS column_index,
    CAST(cells.value AS TEXT) AS value
FROM raw_rows AS rows, json_each(rows.values_json) AS cells;
"""


def _profile_map(profiles: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        profile["path"]: profile
        for profile in profiles["profiles"]
    }


def _validate_loaded_database(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    expected_file_count: int,
    profile_by_path: dict[str, dict[str, object]],
) -> dict[str, object]:
    file_count = connection.execute(
        "SELECT COUNT(*) FROM raw_files WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    if file_count != expected_file_count:
        raise RuntimeError(
            f"raw file count mismatch: actual={file_count} "
            f"expected={expected_file_count}"
        )

    empty_core_files: list[str] = []
    for source_file in sorted(CORE_FILES):
        row = connection.execute(
            """
            SELECT loaded_row_count
            FROM raw_files
            WHERE run_id = ? AND source_file = ?
            """,
            (run_id, source_file),
        ).fetchone()
        if row is None or row[0] == 0:
            empty_core_files.append(source_file)
    if empty_core_files:
        raise RuntimeError(f"empty core files: {empty_core_files}")

    quest_info_nonempty = connection.execute(
        """
        SELECT COUNT(*)
        FROM raw_rows
        WHERE run_id = ?
          AND source_file = 'original_data/mb/quest/quest_info.txt'
          AND TRIM(raw_value) <> ''
        """,
        (run_id,),
    ).fetchone()[0]
    quest_profile = profile_by_path[
        "original_data/mb/quest/quest_info.txt"
    ]
    header_rows = 1 if (
        quest_profile["header"]["classification"] == "yes"
        and quest_profile["header"]["confidence"] == "high"
    ) else 0
    quest_info_data_rows = quest_info_nonempty - header_rows
    if quest_info_data_rows != 8829:
        raise RuntimeError(
            f"quest_info data row mismatch: {quest_info_data_rows} != 8829"
        )

    return {
        "file_count": file_count,
        "quest_info_nonempty_rows": quest_info_nonempty,
        "quest_info_header_rows": header_rows,
        "quest_info_data_rows": quest_info_data_rows,
        "empty_core_files": empty_core_files,
    }


def load_raw(
    *,
    inventory_path: Path,
    profiles_path: Path,
    output_db: Path,
    manifest_path: Path,
    check: bool = False,
) -> dict[str, object]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    if inventory["run_id"] != profiles["run_id"]:
        raise ValueError("inventory and profile run IDs do not match")
    run_id = inventory["run_id"]
    if output_db.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing run database: {output_db}"
        )

    output_db.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_db = output_db.with_name(output_db.name + ".tmp")
    if temporary_db.exists():
        temporary_db.unlink()

    source_root = Path(inventory["input_root"]).parent
    profile_by_path = _profile_map(profiles)
    loaded_at = datetime.now(timezone.utc).isoformat()
    file_results: list[dict[str, object]] = []
    total_rows = 0
    total_cells = 0

    try:
        connection = sqlite3.connect(temporary_db)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        connection.execute(
            """
            INSERT INTO load_batches(
                run_id, input_root, inventory_path, profiles_path, loaded_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                inventory["input_root"],
                inventory_path.as_posix(),
                profiles_path.as_posix(),
                loaded_at,
            ),
        )

        for record in inventory["files"]:
            source_file = record["path"]
            path = source_root / source_file
            rows = parse_text_file(
                path,
                run_id=run_id,
                source_root=source_root,
            )
            cell_count = sum(len(row.values) for row in rows)
            connection.execute(
                """
                INSERT INTO raw_files(
                    run_id, source_file, sha256, size_bytes, encoding,
                    physical_line_count, loaded_row_count, loaded_cell_count,
                    load_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'loaded')
                """,
                (
                    run_id,
                    source_file,
                    record["sha256"],
                    record["size_bytes"],
                    record["encoding"],
                    record["line_count"],
                    len(rows),
                    cell_count,
                ),
            )
            connection.executemany(
                """
                INSERT INTO raw_rows(
                    run_id, source_file, source_row, raw_value, values_json,
                    line_ending, column_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        row.run_id,
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        json.dumps(row.values, ensure_ascii=False),
                        row.line_ending,
                        len(row.values),
                    )
                    for row in rows
                ),
            )
            total_rows += len(rows)
            total_cells += cell_count
            file_results.append(
                {
                    "path": source_file,
                    "status": "loaded",
                    "row_count": len(rows),
                    "cell_count": cell_count,
                }
            )

        validation = _validate_loaded_database(
            connection,
            run_id=run_id,
            expected_file_count=inventory["file_count"],
            profile_by_path=profile_by_path,
        )
        connection.commit()
        connection.close()
        os.replace(temporary_db, output_db)
    except Exception:
        try:
            connection.close()
        except UnboundLocalError:
            pass
        temporary_db.unlink(missing_ok=True)
        raise

    result = {
        "schema_version": 1,
        "run_id": run_id,
        "loaded_at": loaded_at,
        "database_path": output_db.as_posix(),
        "inventory_path": inventory_path.as_posix(),
        "profiles_path": profiles_path.as_posix(),
        "file_count": len(file_results),
        "row_count": total_rows,
        "cell_count": total_cells,
        "validation": validation,
        "files": file_results,
    }
    manifest_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if check and validation["file_count"] != inventory["file_count"]:
        raise RuntimeError("post-load check failed")
    return result
