from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from questdb.parser import ParsedRow, iter_nonempty, parse_text_file


QUEST_INFO = "mb/quest/quest_info.txt"
QUEST_TEXT = "mb/quest/quest_text.txt"
QUEST_SORT = "mb/quest/quest_sort.txt"
CHARACTER_CALL = "mb/etc/cha_call.txt"


CHARACTER_CALL_SCHEMA = """
CREATE TABLE IF NOT EXISTS character_call_profile (
    call_profile_id INTEGER PRIMARY KEY,
    speaker_profile_name TEXT NOT NULL,
    variant_count INTEGER NOT NULL,
    raw_values_json TEXT NOT NULL CHECK (json_valid(raw_values_json)),
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS character_call_variant (
    call_profile_id INTEGER NOT NULL,
    variant_no INTEGER NOT NULL,
    call_text TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (call_profile_id, variant_no),
    FOREIGN KEY (call_profile_id)
      REFERENCES character_call_profile(call_profile_id)
);
CREATE INDEX IF NOT EXISTS idx_character_call_text
ON character_call_variant(call_text);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _value(values: tuple[str, ...] | list[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def _json(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _read_rows(
    root: Path,
    relative_path: str,
    *,
    run_id: str,
    skip_first_nonempty: bool = False,
) -> list[ParsedRow]:
    rows = list(
        iter_nonempty(
            parse_text_file(
                root / relative_path,
                run_id=run_id,
                source_root=root,
            )
        )
    )
    return rows[1:] if skip_first_nonempty else rows


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _write_report(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _audit(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    entity_name: str,
    row_count: int,
    source_file: str | None,
    run_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO load_audit
          (task_id, entity_name, row_count, source_file, run_id, loaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, entity_name, row_count, source_file, run_id, _utc_now()),
    )


def init_database(db_path: Path, *, run_id: str) -> dict[str, Any]:
    if db_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing normalized DB: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).with_name("schema.sql")
    connection = _connect(db_path)
    try:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.executemany(
            "INSERT INTO build_meta(key, value) VALUES (?, ?)",
            [
                ("run_id", run_id),
                ("schema_version", "2"),
                ("created_at", _utc_now()),
                ("g01_decision", "approved_recommended"),
            ],
        )
        connection.commit()
        tables = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    return {"db": str(db_path), "table_count": tables, "integrity_check": integrity}


def load_quest(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    rows = _read_rows(
        root,
        QUEST_INFO,
        run_id=run_id,
        skip_first_nonempty=True,
    )
    parsed: list[tuple[ParsedRow, int]] = []
    for row in rows:
        quest_id = _to_int(_value(row.values, 1))
        if quest_id is None:
            raise ValueError(f"Invalid quest_id at {row.source_file}:{row.source_row}")
        parsed.append((row, quest_id))

    id_counts = Counter(quest_id for _, quest_id in parsed)
    duplicates = {quest_id: count for quest_id, count in id_counts.items() if count > 1}
    if duplicates != {11257: 2}:
        raise ValueError(f"Unexpected duplicate quest IDs: {duplicates}")

    connection = _connect(db_path)
    try:
        if connection.execute("SELECT COUNT(*) FROM quest").fetchone()[0]:
            raise RuntimeError("quest table is already loaded")
        with connection:
            category_ids = {
                category_id
                for row, _ in parsed
                if (category_id := _to_int(_value(row.values, 2))) is not None
            }
            connection.executemany(
                """
                INSERT OR IGNORE INTO quest_category
                  (category_id, category_name, source_file, source_row, raw_value, run_id)
                VALUES (?, NULL, NULL, NULL, NULL, ?)
                """,
                [(category_id, run_id) for category_id in sorted(category_ids)],
            )
            connection.executemany(
                """
                INSERT INTO quest_identity(quest_id, version_count, has_conflict)
                VALUES (?, ?, ?)
                """,
                [
                    (quest_id, count, int(count > 1))
                    for quest_id, count in sorted(id_counts.items())
                ],
            )
            versions: Counter[int] = Counter()
            quest_rows = []
            for row, quest_id in parsed:
                versions[quest_id] += 1
                values = row.values
                quest_rows.append(
                    (
                        quest_id,
                        versions[quest_id],
                        int(id_counts[quest_id] > 1),
                        _value(values, 0),
                        _to_int(_value(values, 2)),
                        _to_int(_value(values, 3)),
                        _to_int(_value(values, 4)),
                        _to_int(_value(values, 5)),
                        _to_int(_value(values, 6)),
                        _to_int(_value(values, 7)),
                        _to_int(_value(values, 8)),
                        _to_int(_value(values, 79)),
                        _to_int(_value(values, 89)),
                        _json(values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    )
                )
            connection.executemany(
                """
                INSERT INTO quest (
                  quest_id, version_no, conflict_flag, quest_name, category_id,
                  max_level, level_requirement, accept_object_type, accept_object_id,
                  submit_object_type, submit_object_id, next_quest_id,
                  tracking_target_id, raw_values_json, source_file, source_row,
                  raw_value, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                quest_rows,
            )
            _audit(
                connection,
                task_id="AI07",
                entity_name="quest",
                row_count=len(quest_rows),
                source_file=QUEST_INFO,
                run_id=run_id,
            )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "source_file": QUEST_INFO,
        "source_rows": len(rows),
        "quest_rows": len(parsed),
        "unique_quest_ids": len(id_counts),
        "duplicate_quest_ids": [
            {"quest_id": quest_id, "version_count": count, "strategy": "preserve_all"}
            for quest_id, count in sorted(duplicates.items())
        ],
        "g01_strategy": {
            "primary_key": ["quest_id", "version_no"],
            "conflict_flag": True,
        },
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def load_character_calls(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    rows = _read_rows(root, CHARACTER_CALL, run_id=run_id)
    connection = _connect(db_path)
    try:
        connection.executescript(CHARACTER_CALL_SCHEMA)
        if connection.execute(
            "SELECT COUNT(*) FROM character_call_profile"
        ).fetchone()[0]:
            raise RuntimeError("character_call_profile table is already loaded")
        profile_count = 0
        variant_count = 0
        with connection:
            for row in rows:
                call_profile_id = _to_int(_value(row.values, 1))
                if call_profile_id is None:
                    continue
                variants = [
                    value.strip() for value in row.values[2:16] if value.strip()
                ]
                connection.execute(
                    """
                    INSERT INTO character_call_profile (
                      call_profile_id, speaker_profile_name, variant_count,
                      raw_values_json, source_file, source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        call_profile_id,
                        _value(row.values, 0),
                        len(variants),
                        _json(row.values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                for variant_no, call_text in enumerate(row.values[2:16], start=1):
                    call_text = call_text.strip()
                    if not call_text:
                        continue
                    connection.execute(
                        """
                        INSERT INTO character_call_variant (
                          call_profile_id, variant_no, call_text,
                          source_file, source_row, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            call_profile_id,
                            variant_no,
                            call_text,
                            row.source_file,
                            row.source_row,
                            run_id,
                        ),
                    )
                    variant_count += 1
                profile_count += 1
            _audit(
                connection,
                task_id="AI08C",
                entity_name="character_call_profile",
                row_count=profile_count,
                source_file=CHARACTER_CALL,
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI08C",
                entity_name="character_call_variant",
                row_count=variant_count,
                source_file=CHARACTER_CALL,
                run_id=run_id,
            )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "source_file": CHARACTER_CALL,
        "profile_count": profile_count,
        "variant_count": variant_count,
        "foreign_key_violations": len(foreign_keys),
        "variant_policy": (
            "variant numbers preserved; player-type column semantics not inferred"
        ),
    }
    _write_report(report_path, report)
    return report


def load_text_and_categories(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    category_rows = _read_rows(root, QUEST_SORT, run_id=run_id)
    text_rows = _read_rows(root, QUEST_TEXT, run_id=run_id)
    connection = _connect(db_path)
    try:
        quest_ids = {
            row[0] for row in connection.execute("SELECT quest_id FROM quest_identity")
        }
        with connection:
            loaded_categories = 0
            for row in category_rows:
                category_id = _to_int(_value(row.values, 1))
                if category_id is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO quest_category (
                      category_id, category_name, sort_order, source_file, source_row,
                      raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(category_id) DO UPDATE SET
                      category_name=excluded.category_name,
                      sort_order=excluded.sort_order,
                      source_file=excluded.source_file,
                      source_row=excluded.source_row,
                      raw_value=excluded.raw_value,
                      run_id=excluded.run_id
                    """,
                    (
                        category_id,
                        _value(row.values, 0),
                        _to_int(_value(row.values, 2)),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                loaded_categories += 1

            loaded_text = 0
            source_text_ids: set[int] = set()
            for row in text_rows:
                source_quest_id = _to_int(_value(row.values, 0))
                if source_quest_id is None:
                    continue
                source_text_ids.add(source_quest_id)
                values = row.values
                connection.execute(
                    """
                    INSERT INTO quest_text (
                      source_quest_id, linked_quest_id, language, accept_dialogue,
                      voice_key, quest_description, hint_text, progress_dialogue,
                      completion_dialogue, raw_values_json, source_file, source_row,
                      raw_value, run_id
                    ) VALUES (?, ?, 'zh-CN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_quest_id,
                        source_quest_id if source_quest_id in quest_ids else None,
                        _value(values, 1),
                        _value(values, 2),
                        _value(values, 3),
                        _value(values, 4),
                        _value(values, 5),
                        _value(values, 6),
                        _json(values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                loaded_text += 1
            _audit(
                connection,
                task_id="AI08",
                entity_name="quest_category",
                row_count=loaded_categories,
                source_file=QUEST_SORT,
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI08",
                entity_name="quest_text",
                row_count=loaded_text,
                source_file=QUEST_TEXT,
                run_id=run_id,
            )
        in_use_categories = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT category_id FROM quest WHERE category_id IS NOT NULL"
            )
        }
        resolved_categories = {
            row[0]
            for row in connection.execute(
                "SELECT category_id FROM quest_category WHERE category_name IS NOT NULL"
            )
        }
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "quest_unique_ids": len(quest_ids),
        "text_physical_rows": len(text_rows),
        "text_rows_loaded": loaded_text,
        "text_unique_ids": len(source_text_ids),
        "matched_quest_ids": len(quest_ids & source_text_ids),
        "missing_text_quest_ids": len(quest_ids - source_text_ids),
        "extra_text_ids": len(source_text_ids - quest_ids),
        "extra_text_id_samples": sorted(source_text_ids - quest_ids)[:30],
        "categories_loaded": loaded_categories,
        "in_use_category_ids": len(in_use_categories),
        "matched_in_use_category_ids": len(in_use_categories & resolved_categories),
        "missing_category_ids": sorted(in_use_categories - resolved_categories),
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def _last_int(values: tuple[str, ...]) -> int | None:
    for value in reversed(values):
        if (number := _to_int(value)) is not None:
            return number
    return None


def load_objects(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    route_map = {
        1: "quest_category",
        2: "quest_item",
        3: "quest_npc",
        5: "quest_identity",
        6: "quest_attribute",
        13: "quest_event",
        15: "quest_camp",
    }
    specs = [
        ("mb/quest/quest_item.txt", "quest_item", "quest_item_id", "quest_item_name"),
        ("mb/quest/quest_event.txt", "quest_event", "quest_event_id", "quest_event_name"),
        ("mb/quest/quest_atb.txt", "quest_attribute", "attribute_id", "attribute_name"),
        ("mb/quest/quest_camp.txt", "quest_camp", "camp_id", "camp_name"),
    ]
    object_rows = _read_rows(root, "mb/quest/quest_object.txt", run_id=run_id)
    quest_rows_for_types = _read_rows(
        root,
        QUEST_INFO,
        run_id=run_id,
        skip_first_nonempty=True,
    )
    object_type_columns = [
        5, 7, 11, 15, 19, 23, 27, 30, 33, 36, 39,
        42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72,
    ]
    connection = _connect(db_path)
    counts: dict[str, int] = {}
    try:
        with connection:
            for row in object_rows:
                object_type_id = _to_int(_value(row.values, 1))
                if object_type_id is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO object_type (
                      object_type_id, object_type_name, route_table, index_no,
                      is_known_route, source_file, source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        object_type_id,
                        _value(row.values, 0),
                        route_map.get(object_type_id),
                        _last_int(row.values),
                        int(object_type_id in route_map),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
            declared_type_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT object_type_id FROM object_type"
                )
            }
            first_undefined_reference: dict[int, ParsedRow] = {}
            for quest_row in quest_rows_for_types:
                for column in object_type_columns:
                    object_type_id = _to_int(_value(quest_row.values, column))
                    if (
                        object_type_id is not None
                        and object_type_id not in declared_type_ids
                        and object_type_id not in first_undefined_reference
                    ):
                        first_undefined_reference[object_type_id] = quest_row
            for object_type_id, source_row in sorted(first_undefined_reference.items()):
                connection.execute(
                    """
                    INSERT INTO object_type (
                      object_type_id, object_type_name, route_table, index_no,
                      is_known_route, source_file, source_row, raw_value, run_id
                    ) VALUES (?, ?, NULL, NULL, 0, ?, ?, ?, ?)
                    """,
                    (
                        object_type_id,
                        f"未定义对象类型{object_type_id}",
                        source_row.source_file,
                        source_row.source_row,
                        source_row.raw_value,
                        run_id,
                    ),
                )
            counts["object_type"] = connection.execute(
                "SELECT COUNT(*) FROM object_type"
            ).fetchone()[0]
            _audit(
                connection,
                task_id="AI09",
                entity_name="object_type",
                row_count=counts["object_type"],
                source_file="mb/quest/quest_object.txt",
                run_id=run_id,
            )

            object_conflicts: list[dict[str, Any]] = []
            for relative_path, table, id_column, name_column in specs:
                rows = _read_rows(root, relative_path, run_id=run_id)
                loaded = 0
                if table == "quest_item":
                    grouped: dict[int, list[ParsedRow]] = defaultdict(list)
                    for row in rows:
                        entity_id = _to_int(_value(row.values, 1))
                        if entity_id is not None:
                            grouped[entity_id].append(row)
                    for entity_id, versions in sorted(grouped.items()):
                        canonical = versions[0]
                        connection.execute(
                            """
                            INSERT INTO quest_item (
                              quest_item_id, quest_item_name, version_count,
                              conflict_flag, raw_values_json, source_file, source_row,
                              raw_value, run_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                entity_id,
                                _value(canonical.values, 0),
                                len(versions),
                                int(len(versions) > 1),
                                _json(canonical.values),
                                canonical.source_file,
                                canonical.source_row,
                                canonical.raw_value,
                                run_id,
                            ),
                        )
                        for version_no, source_row in enumerate(versions, start=1):
                            connection.execute(
                                """
                                INSERT INTO quest_item_source (
                                  quest_item_id, version_no, quest_item_name,
                                  raw_values_json, source_file, source_row, raw_value,
                                  run_id
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    entity_id,
                                    version_no,
                                    _value(source_row.values, 0),
                                    _json(source_row.values),
                                    source_row.source_file,
                                    source_row.source_row,
                                    source_row.raw_value,
                                    run_id,
                                ),
                            )
                        if len(versions) > 1:
                            object_conflicts.append(
                                {
                                    "table": table,
                                    "id": entity_id,
                                    "versions": [
                                        {
                                            "version_no": version_no,
                                            "source_row": source_row.source_row,
                                            "name": _value(source_row.values, 0),
                                        }
                                        for version_no, source_row in enumerate(
                                            versions, start=1
                                        )
                                    ],
                                    "strategy": "first_source_is_canonical_all_versions_preserved",
                                }
                            )
                    loaded = len(grouped)
                    counts["quest_item_source"] = sum(
                        len(versions) for versions in grouped.values()
                    )
                    counts[table] = loaded
                    _audit(
                        connection,
                        task_id="AI09",
                        entity_name=table,
                        row_count=loaded,
                        source_file=relative_path,
                        run_id=run_id,
                    )
                    _audit(
                        connection,
                        task_id="AI09",
                        entity_name="quest_item_source",
                        row_count=counts["quest_item_source"],
                        source_file=relative_path,
                        run_id=run_id,
                    )
                    continue
                sql = (
                    f"INSERT INTO {table} ({id_column}, {name_column}, raw_values_json, "
                    "source_file, source_row, raw_value, run_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
                )
                for row in rows:
                    entity_id = _to_int(_value(row.values, 1))
                    if entity_id is None:
                        continue
                    connection.execute(
                        sql,
                        (
                            entity_id,
                            _value(row.values, 0),
                            _json(row.values),
                            row.source_file,
                            row.source_row,
                            row.raw_value,
                            run_id,
                        ),
                    )
                    loaded += 1
                counts[table] = loaded
                _audit(
                    connection,
                    task_id="AI09",
                    entity_name=table,
                    row_count=loaded,
                    source_file=relative_path,
                    run_id=run_id,
                )
        routes = {
            row["object_type_id"]: row["route_table"]
            for row in connection.execute(
                "SELECT object_type_id, route_table FROM object_type"
            )
        }
        unknown = [
            {
                "object_type_id": row["object_type_id"],
                "object_type_name": row["object_type_name"],
                "index_no": row["index_no"],
            }
            for row in connection.execute(
                """
                SELECT object_type_id, object_type_name, index_no
                FROM object_type WHERE route_table IS NULL
                ORDER BY object_type_id
                """
            )
        ]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    required_route_ids = [2, 3, 5, 6, 13, 15]
    report = {
        "run_id": run_id,
        "counts": counts,
        "required_routes": {
            str(object_type_id): routes.get(object_type_id)
            for object_type_id in required_route_ids
        },
        "required_routes_ok": all(routes.get(object_type_id) for object_type_id in required_route_ids),
        "unknown_route_types": unknown,
        "undefined_referenced_types": sorted(first_undefined_reference),
        "source_conflicts": object_conflicts,
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def _resolved_object_ids(connection: sqlite3.Connection) -> dict[int, set[int]]:
    definitions = {
        2: ("quest_item", "quest_item_id"),
        3: ("quest_npc", "quest_npc_id"),
        5: ("quest_identity", "quest_id"),
        6: ("quest_attribute", "attribute_id"),
        13: ("quest_event", "quest_event_id"),
        15: ("quest_camp", "camp_id"),
    }
    return {
        object_type: {
            row[0] for row in connection.execute(f"SELECT {id_column} FROM {table}")
        }
        for object_type, (table, id_column) in definitions.items()
    }


def load_npc_and_targets(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    npc_rows = _read_rows(root, "mb/quest/quest_npc.txt", run_id=run_id)
    target_rows = _read_rows(root, "mb/quest/quest_target.txt", run_id=run_id)
    connection = _connect(db_path)
    try:
        with connection:
            loaded_npcs = 0
            for row in npc_rows:
                npc_id = _to_int(_value(row.values, 1))
                if npc_id is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO quest_npc (
                      quest_npc_id, quest_npc_name, raw_values_json, source_file,
                      source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        npc_id,
                        _value(row.values, 0),
                        _json(row.values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                loaded_npcs += 1

            loaded_targets = 0
            for row in target_rows:
                target_id = _to_int(_value(row.values, 0))
                if target_id is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO quest_target (
                      target_id, target_name, area_name, resource_key, raw_values_json,
                      source_file, source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_id,
                        _value(row.values, 1),
                        _value(row.values, 9) or None,
                        _value(row.values, 4) or None,
                        _json(row.values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                loaded_targets += 1

            resolved_ids = _resolved_object_ids(connection)
            quest_rows = connection.execute(
                """
                SELECT quest_id, version_no, accept_object_type, accept_object_id,
                       submit_object_type, submit_object_id, source_file, source_row,
                       raw_value
                FROM quest
                """
            ).fetchall()
            endpoint_count = 0
            for quest in quest_rows:
                for kind, object_type, object_id, type_col, id_col in [
                    (
                        "accept",
                        quest["accept_object_type"],
                        quest["accept_object_id"],
                        6,
                        7,
                    ),
                    (
                        "submit",
                        quest["submit_object_type"],
                        quest["submit_object_id"],
                        8,
                        9,
                    ),
                ]:
                    if object_type is None or object_id is None:
                        continue
                    resolved = object_id in resolved_ids.get(object_type, set())
                    connection.execute(
                        """
                        INSERT INTO quest_endpoint (
                          quest_id, version_no, endpoint_kind, object_type_id, object_id,
                          resolved, source_column_type, source_column_id, source_file,
                          source_row, raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            quest["quest_id"],
                            quest["version_no"],
                            kind,
                            object_type,
                            object_id,
                            int(resolved),
                            type_col,
                            id_col,
                            quest["source_file"],
                            quest["source_row"],
                            quest["raw_value"],
                            run_id,
                        ),
                    )
                    endpoint_count += 1
            _audit(
                connection,
                task_id="AI10",
                entity_name="quest_npc",
                row_count=loaded_npcs,
                source_file="mb/quest/quest_npc.txt",
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI10",
                entity_name="quest_target",
                row_count=loaded_targets,
                source_file="mb/quest/quest_target.txt",
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI10",
                entity_name="quest_endpoint",
                row_count=endpoint_count,
                source_file=QUEST_INFO,
                run_id=run_id,
            )

        npc_ids = {
            row[0] for row in connection.execute("SELECT quest_npc_id FROM quest_npc")
        }
        target_ids = {
            row[0] for row in connection.execute("SELECT target_id FROM quest_target")
        }
        raw_quest_rows = connection.execute(
            "SELECT raw_values_json FROM quest"
        ).fetchall()
        npc_type_columns = [5, 7, 11, 15, 19, 23, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72]
        referenced_npcs: set[int] = set()
        referenced_targets: set[int] = set()
        for raw_row in raw_quest_rows:
            values = json.loads(raw_row[0])
            for base in npc_type_columns:
                if _value(values, base) == "3":
                    object_id = _to_int(_value(values, base + 1))
                    if object_id is not None:
                        referenced_npcs.add(object_id)
            target_id = _to_int(_value(values, 89))
            if target_id:
                referenced_targets.add(target_id)
        unresolved_endpoints = connection.execute(
            "SELECT COUNT(*) FROM quest_endpoint WHERE resolved=0"
        ).fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "quest_npc_rows": loaded_npcs,
        "quest_target_rows": loaded_targets,
        "quest_endpoint_rows": endpoint_count,
        "unique_referenced_npc_ids": len(referenced_npcs),
        "matched_referenced_npc_ids": len(referenced_npcs & npc_ids),
        "missing_referenced_npc_ids": sorted(referenced_npcs - npc_ids),
        "unique_referenced_target_ids": len(referenced_targets),
        "matched_referenced_target_ids": len(referenced_targets & target_ids),
        "missing_referenced_target_ids": sorted(referenced_targets - target_ids),
        "unresolved_endpoint_rows": unresolved_endpoints,
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def load_items_and_rewards(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    sources = [
        ("mb/item/item_list.txt", "item_list", 1),
        ("mb/item/item_list2.txt", "item_list2", 2),
        ("mb/item/item_list3.txt", "item_list3", 3),
    ]
    by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for relative_path, source_table, priority in sources:
        for row in _read_rows(
            root,
            relative_path,
            run_id=run_id,
            skip_first_nonempty=True,
        ):
            item_id = _to_int(_value(row.values, 0))
            if item_id is None:
                continue
            by_id[item_id].append(
                {
                    "item_id": item_id,
                    "item_name": _value(row.values, 1),
                    "source_table": source_table,
                    "priority": priority,
                    "row": row,
                }
            )

    connection = _connect(db_path)
    try:
        with connection:
            for item_id, variants in sorted(by_id.items()):
                canonical = min(variants, key=lambda item: item["priority"])
                row = canonical["row"]
                connection.execute(
                    """
                    INSERT INTO item (
                      item_id, item_name, canonical_source, source_priority,
                      source_file, source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        canonical["item_name"],
                        canonical["source_table"],
                        canonical["priority"],
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                for variant in variants:
                    source_row = variant["row"]
                    connection.execute(
                        """
                        INSERT INTO item_source (
                          item_id, source_table, item_name, source_priority,
                          is_canonical, raw_values_json, source_file, source_row,
                          raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item_id,
                            variant["source_table"],
                            variant["item_name"],
                            variant["priority"],
                            int(variant is canonical),
                            _json(source_row.values),
                            source_row.source_file,
                            source_row.source_row,
                            source_row.raw_value,
                            run_id,
                        ),
                    )

            item_ids = set(by_id)
            quest_rows = connection.execute(
                """
                SELECT quest_id, version_no, raw_values_json, source_file,
                       source_row, raw_value
                FROM quest
                """
            ).fetchall()
            reward_count = 0
            reward_item_ids: set[int] = set()
            for quest in quest_rows:
                values = json.loads(quest["raw_values_json"])
                for reward_group, bases in [
                    ("fixed", [51, 54, 57, 60]),
                    ("general", [63, 66, 69, 72]),
                ]:
                    for slot_no, base in enumerate(bases, start=1):
                        object_type = _to_int(_value(values, base))
                        if object_type is None:
                            continue
                        object_id = _to_int(_value(values, base + 1))
                        amount = _to_int(_value(values, base + 2))
                        if object_type == 2 and object_id:
                            reward_item_ids.add(object_id)
                        connection.execute(
                            """
                            INSERT INTO quest_reward (
                              quest_id, version_no, reward_group, slot_no,
                              object_type_id, object_id, amount, item_resolved,
                              source_file, source_row, raw_value, run_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                quest["quest_id"],
                                quest["version_no"],
                                reward_group,
                                slot_no,
                                object_type,
                                object_id,
                                amount,
                                int(object_type == 2 and object_id in item_ids),
                                quest["source_file"],
                                quest["source_row"],
                                quest["raw_value"],
                                run_id,
                            ),
                        )
                        reward_count += 1
            _audit(
                connection,
                task_id="AI11",
                entity_name="item",
                row_count=len(item_ids),
                source_file="mb/item/item_list*.txt",
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI11",
                entity_name="item_source",
                row_count=sum(len(variants) for variants in by_id.values()),
                source_file="mb/item/item_list*.txt",
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI11",
                entity_name="quest_reward",
                row_count=reward_count,
                source_file=QUEST_INFO,
                run_id=run_id,
            )
        conflicts = []
        for item_id, variants in sorted(by_id.items()):
            if len(variants) < 2:
                continue
            signatures = {(item["item_name"], item["row"].raw_value) for item in variants}
            if len(signatures) > 1:
                conflicts.append(
                    {
                        "item_id": item_id,
                        "sources": [
                            {
                                "source_table": item["source_table"],
                                "priority": item["priority"],
                                "item_name": item["item_name"],
                            }
                            for item in variants
                        ],
                        "canonical_source": min(
                            variants, key=lambda item: item["priority"]
                        )["source_table"],
                    }
                )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "canonical_item_rows": len(by_id),
        "item_source_rows": sum(len(variants) for variants in by_id.values()),
        "cross_table_item_ids": sum(1 for variants in by_id.values() if len(variants) > 1),
        "cross_table_conflicts": conflicts,
        "source_priority": ["item_list", "item_list2", "item_list3"],
        "quest_reward_rows": reward_count,
        "unique_reward_item_ids": len(reward_item_ids),
        "matched_reward_item_ids": len(reward_item_ids & set(by_id)),
        "missing_reward_item_ids": sorted(reward_item_ids - set(by_id)),
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def validate_database(db_path: Path, *, scope: str) -> dict[str, Any]:
    connection = _connect(db_path)
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        if scope in {"quest", "all"}:
            checks["quest_rows"] = connection.execute(
                "SELECT COUNT(*) FROM quest"
            ).fetchone()[0]
            checks["unique_quest_ids"] = connection.execute(
                "SELECT COUNT(*) FROM quest_identity"
            ).fetchone()[0]
            checks["duplicate_id_rows"] = connection.execute(
                "SELECT COUNT(*) FROM quest_identity WHERE version_count>1"
            ).fetchone()[0]
            checks["quest_11257_versions"] = connection.execute(
                "SELECT COUNT(*) FROM quest WHERE quest_id=11257 AND conflict_flag=1"
            ).fetchone()[0]
            if checks["quest_rows"] != 8829:
                failures.append("quest_rows")
            if checks["unique_quest_ids"] != 8828:
                failures.append("unique_quest_ids")
            if checks["duplicate_id_rows"] != 1 or checks["quest_11257_versions"] != 2:
                failures.append("duplicate_11257_strategy")

        if scope in {"text", "all"}:
            quest_ids = {
                row[0] for row in connection.execute("SELECT quest_id FROM quest_identity")
            }
            text_ids = {
                row[0] for row in connection.execute(
                    "SELECT DISTINCT source_quest_id FROM quest_text"
                )
            }
            checks["matched_quest_text_ids"] = len(quest_ids & text_ids)
            checks["missing_text_quest_ids"] = len(quest_ids - text_ids)
            checks["extra_text_ids"] = len(text_ids - quest_ids)
            checks["matched_in_use_categories"] = connection.execute(
                """
                SELECT COUNT(DISTINCT q.category_id)
                FROM quest q JOIN quest_category c ON c.category_id=q.category_id
                WHERE c.category_name IS NOT NULL
                """
            ).fetchone()[0]
            if (
                checks["matched_quest_text_ids"],
                checks["missing_text_quest_ids"],
                checks["extra_text_ids"],
                checks["matched_in_use_categories"],
            ) != (8671, 157, 49, 102):
                failures.append("text_category_coverage")

        if scope in {"objects", "all"}:
            required_routes = {
                row[0]: row[1]
                for row in connection.execute(
                    """
                    SELECT object_type_id, route_table FROM object_type
                    WHERE object_type_id IN (2,3,5,6,13,15)
                    """
                )
            }
            checks["required_routes"] = required_routes
            if len(required_routes) != 6 or any(value is None for value in required_routes.values()):
                failures.append("required_object_routes")

        if scope in {"npc-target", "all"}:
            referenced_npcs: set[int] = set()
            npc_type_columns = [
                5, 7, 11, 15, 19, 23, 27, 30, 33, 36, 39,
                42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72,
            ]
            for row in connection.execute("SELECT raw_values_json FROM quest"):
                values = json.loads(row[0])
                for base in npc_type_columns:
                    if _value(values, base) == "3":
                        object_id = _to_int(_value(values, base + 1))
                        if object_id is not None:
                            referenced_npcs.add(object_id)
            known_npcs = {
                row[0] for row in connection.execute("SELECT quest_npc_id FROM quest_npc")
            }
            checks["unique_referenced_npc_ids"] = len(referenced_npcs)
            checks["missing_referenced_npc_ids"] = len(referenced_npcs - known_npcs)
            checks["unresolved_endpoint_rows"] = connection.execute(
                "SELECT COUNT(*) FROM quest_endpoint WHERE resolved=0"
            ).fetchone()[0]
            checks["missing_target_rows"] = connection.execute(
                """
                SELECT COUNT(*) FROM quest q
                LEFT JOIN quest_target t ON t.target_id=q.tracking_target_id
                WHERE q.tracking_target_id IS NOT NULL
                  AND q.tracking_target_id<>0
                  AND t.target_id IS NULL
                """
            ).fetchone()[0]
            if checks["unique_referenced_npc_ids"] != 3853:
                failures.append("unique_referenced_npc_ids")
            if (
                checks["missing_referenced_npc_ids"]
                or checks["unresolved_endpoint_rows"]
                or checks["missing_target_rows"]
            ):
                failures.append("npc_target_coverage")

        if scope in {"items", "all"}:
            checks["unique_reward_item_ids"] = connection.execute(
                """
                SELECT COUNT(DISTINCT object_id) FROM quest_reward
                WHERE object_type_id=2 AND object_id IS NOT NULL AND object_id<>0
                """
            ).fetchone()[0]
            checks["unresolved_reward_item_ids"] = connection.execute(
                """
                SELECT COUNT(DISTINCT object_id) FROM quest_reward
                WHERE object_type_id=2 AND object_id IS NOT NULL
                  AND object_id<>0 AND item_resolved=0
                """
            ).fetchone()[0]
            if checks["unique_reward_item_ids"] != 1995:
                failures.append("unique_reward_item_ids")
            if checks["unresolved_reward_item_ids"]:
                failures.append("unresolved_reward_item_ids")

        checks["foreign_key_violations"] = len(
            connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        checks["integrity_check"] = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        if checks["foreign_key_violations"]:
            failures.append("foreign_key_violations")
        if checks["integrity_check"] != "ok":
            failures.append("integrity_check")
    finally:
        connection.close()
    return {
        "scope": scope,
        "status": "ok" if not failures else "failed",
        "checks": checks,
        "failures": failures,
    }
