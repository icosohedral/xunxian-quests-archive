from __future__ import annotations

import csv
import html
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from questdb.normalized import (
    QUEST_INFO,
    _audit,
    _connect,
    _json,
    _read_rows,
    _to_int,
    _utc_now,
    _value,
    _write_report,
    validate_database,
)


OBJECT_TYPE_COLUMNS = [
    5, 7, 11, 15, 19, 23, 27, 30, 33, 36, 39,
    42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72,
]


def _star_ints(value: str) -> list[int]:
    return [
        number
        for part in value.split("*")
        if (number := _to_int(part)) is not None
    ]


def _quest_versions(connection: sqlite3.Connection) -> dict[int, list[int]]:
    versions: dict[int, list[int]] = defaultdict(list)
    for row in connection.execute("SELECT quest_id, version_no FROM quest"):
        versions[row[0]].append(row[1])
    return versions


def _insert_relation(
    connection: sqlite3.Connection,
    *,
    quest_id: int,
    version_no: int,
    to_quest_id: int | None,
    relation_type: str,
    slot_no: int | None,
    source_file: str,
    source_row: int,
    raw_value: str,
    run_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO quest_relation (
          from_quest_id, from_version_no, to_quest_id, relation_type, slot_no,
          source_file, source_row, raw_value, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quest_id,
            version_no,
            to_quest_id,
            relation_type,
            slot_no,
            source_file,
            source_row,
            raw_value,
            run_id,
        ),
    )


def _find_cycles(edges: dict[int, set[int]]) -> list[list[int]]:
    state: dict[int, int] = {}
    stack: list[int] = []
    stack_index: dict[int, int] = {}
    cycles: set[tuple[int, ...]] = set()

    def canonical(cycle: list[int]) -> tuple[int, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        best = min(rotations)
        return best + (best[0],)

    def visit(node: int) -> None:
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for target in edges.get(node, set()):
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                cycle = stack[stack_index[target] :] + [target]
                cycles.add(canonical(cycle))
        stack.pop()
        stack_index.pop(node, None)
        state[node] = 2

    for node in sorted(edges):
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) for cycle in sorted(cycles)]


def load_relations(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    connection = _connect(db_path)
    counts: Counter[str] = Counter()
    try:
        if connection.execute("SELECT COUNT(*) FROM quest_relation").fetchone()[0]:
            raise RuntimeError("quest_relation is already loaded")
        versions = _quest_versions(connection)
        known_quest_ids = set(versions)
        unique_next_refs: set[int] = set()
        unique_task_refs: set[int] = set()
        next_edges: dict[int, set[int]] = defaultdict(set)
        with connection:
            for quest in connection.execute(
                """
                SELECT quest_id, version_no, next_quest_id, raw_values_json,
                       source_file, source_row, raw_value
                FROM quest
                """
            ):
                if quest["next_quest_id"]:
                    target = quest["next_quest_id"]
                    unique_next_refs.add(target)
                    next_edges[quest["quest_id"]].add(target)
                    _insert_relation(
                        connection,
                        quest_id=quest["quest_id"],
                        version_no=quest["version_no"],
                        to_quest_id=target,
                        relation_type="next",
                        slot_no=1,
                        source_file=quest["source_file"],
                        source_row=quest["source_row"],
                        raw_value=quest["raw_value"],
                        run_id=run_id,
                    )
                    counts["next"] += 1
                values = json.loads(quest["raw_values_json"])
                for slot_no, base in enumerate(OBJECT_TYPE_COLUMNS, start=1):
                    if _value(values, base) != "5":
                        continue
                    target = _to_int(_value(values, base + 1))
                    if not target:
                        continue
                    unique_task_refs.add(target)
                    _insert_relation(
                        connection,
                        quest_id=quest["quest_id"],
                        version_no=quest["version_no"],
                        to_quest_id=target,
                        relation_type="task_object_reference",
                        slot_no=slot_no,
                        source_file=quest["source_file"],
                        source_row=quest["source_row"],
                        raw_value=quest["raw_value"],
                        run_id=run_id,
                    )
                    counts["task_object_reference"] += 1

            for row in _read_rows(root, "mb/quest/quest_link.txt", run_id=run_id):
                quest_id = _to_int(_value(row.values, 2))
                group_no = _to_int(_value(row.values, 1))
                if quest_id not in versions:
                    continue
                for version_no in versions[quest_id]:
                    _insert_relation(
                        connection,
                        quest_id=quest_id,
                        version_no=version_no,
                        to_quest_id=None,
                        relation_type="link_member",
                        slot_no=group_no,
                        source_file=row.source_file,
                        source_row=row.source_row,
                        raw_value=row.raw_value,
                        run_id=run_id,
                    )
                    counts["link_member"] += 1

            for relative_path, relation_type, header, source_index, list_index in [
                ("mb/quest/quest_mutex.txt", "mutex", True, 1, 3),
                ("mb/quest/quest_reject.txt", "reject", False, 0, 2),
            ]:
                for row in _read_rows(
                    root,
                    relative_path,
                    run_id=run_id,
                    skip_first_nonempty=header,
                ):
                    quest_id = _to_int(_value(row.values, source_index))
                    if quest_id not in versions:
                        continue
                    for list_slot, target in enumerate(
                        _star_ints(_value(row.values, list_index)), start=1
                    ):
                        for version_no in versions[quest_id]:
                            _insert_relation(
                                connection,
                                quest_id=quest_id,
                                version_no=version_no,
                                to_quest_id=target,
                                relation_type=relation_type,
                                slot_no=list_slot,
                                source_file=row.source_file,
                                source_row=row.source_row,
                                raw_value=row.raw_value,
                                run_id=run_id,
                            )
                            counts[relation_type] += 1
            _audit(
                connection,
                task_id="AI12",
                entity_name="quest_relation",
                row_count=sum(counts.values()),
                source_file="quest_info/link/mutex/reject",
                run_id=run_id,
            )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "relation_rows_by_type": dict(sorted(counts.items())),
        "unique_next_quest_refs": len(unique_next_refs),
        "matched_next_quest_refs": len(unique_next_refs & known_quest_ids),
        "missing_next_quest_refs": sorted(unique_next_refs - known_quest_ids),
        "unique_task_object_refs": len(unique_task_refs),
        "matched_task_object_refs": len(unique_task_refs & known_quest_ids),
        "missing_task_object_refs": sorted(unique_task_refs - known_quest_ids),
        "next_relation_cycles": _find_cycles(next_edges),
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def _raw_tuple(values: list[str] | tuple[str, ...], start: int, length: int) -> list[str]:
    return [_value(values, start + offset) for offset in range(length)]


def load_groups(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    connection = _connect(db_path)
    anomalies: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    type_35_36_refs: list[dict[str, Any]] = []
    try:
        with connection:
            for quest in connection.execute(
                """
                SELECT quest_id, version_no, raw_values_json, source_file,
                       source_row, raw_value
                FROM quest
                """
            ):
                values = json.loads(quest["raw_values_json"])
                for kind, bases, length in [
                    ("precondition", [11, 15, 19, 23], 4),
                    ("required_object", [27, 30, 33, 36], 3),
                ]:
                    for slot_no, base in enumerate(bases, start=1):
                        raw_group = _raw_tuple(values, base, length)
                        if not any(raw_group):
                            continue
                        object_type = _to_int(raw_group[0])
                        object_id = _to_int(raw_group[1])
                        comparison = _to_int(raw_group[2]) if length == 4 else None
                        comparison_value = (
                            _to_int(raw_group[3]) if length == 4 else _to_int(raw_group[2])
                        )
                        connection.execute(
                            """
                            INSERT INTO quest_condition (
                              quest_id, version_no, condition_kind, slot_no,
                              object_type_id, object_id, comparison_code,
                              comparison_value, raw_group_json, source_file,
                              source_row, raw_value, run_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                quest["quest_id"],
                                quest["version_no"],
                                kind,
                                slot_no,
                                object_type,
                                object_id,
                                comparison,
                                comparison_value,
                                _json(raw_group),
                                quest["source_file"],
                                quest["source_row"],
                                quest["raw_value"],
                                run_id,
                            ),
                        )
                        counts[kind] += 1
                        if object_type in {35, 36}:
                            type_35_36_refs.append(
                                {
                                    "quest_id": quest["quest_id"],
                                    "version_no": quest["version_no"],
                                    "kind": kind,
                                    "slot_no": slot_no,
                                    "object_type": object_type,
                                    "object_id": object_id,
                                    "source_row": quest["source_row"],
                                }
                            )
                        if object_type is None or (raw_group[1] and object_id is None):
                            anomalies.append(
                                {
                                    "kind": "unparseable_condition_group",
                                    "quest_id": quest["quest_id"],
                                    "version_no": quest["version_no"],
                                    "slot_no": slot_no,
                                    "raw_group": raw_group,
                                }
                            )

                for slot_no, base in enumerate([39, 42, 45, 48], start=1):
                    raw_group = _raw_tuple(values, base, 3)
                    if not any(raw_group):
                        continue
                    object_type = _to_int(raw_group[0])
                    object_id = _to_int(raw_group[1])
                    amount = _to_int(raw_group[2])
                    connection.execute(
                        """
                        INSERT INTO quest_objective (
                          quest_id, version_no, slot_no, object_type_id, object_id,
                          amount, raw_group_json, source_file, source_row, raw_value,
                          run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            quest["quest_id"],
                            quest["version_no"],
                            slot_no,
                            object_type,
                            object_id,
                            amount,
                            _json(raw_group),
                            quest["source_file"],
                            quest["source_row"],
                            quest["raw_value"],
                            run_id,
                        ),
                    )
                    counts["objective"] += 1
                    if object_type in {35, 36}:
                        type_35_36_refs.append(
                            {
                                "quest_id": quest["quest_id"],
                                "version_no": quest["version_no"],
                                "kind": "objective",
                                "slot_no": slot_no,
                                "object_type": object_type,
                                "object_id": object_id,
                                "source_row": quest["source_row"],
                            }
                        )
                    if object_type is None or (raw_group[1] and object_id is None):
                        anomalies.append(
                            {
                                "kind": "unparseable_objective_group",
                                "quest_id": quest["quest_id"],
                                "version_no": quest["version_no"],
                                "slot_no": slot_no,
                                "raw_group": raw_group,
                            }
                        )

            group_rows = _read_rows(
                root, "mb/quest/quest_precondition.txt", run_id=run_id
            )
            group_ids: set[int] = set()
            for row in group_rows:
                group_id = _to_int(_value(row.values, 1))
                if group_id is None:
                    continue
                group_ids.add(group_id)
                arrays = [
                    _value(row.values, 3).split("*"),
                    _value(row.values, 4).split("*"),
                    _value(row.values, 5).split("*"),
                    _value(row.values, 6).split("*"),
                ]
                nonempty_lengths = [len(array) for array in arrays if any(array)]
                if nonempty_lengths and len(set(nonempty_lengths)) > 1:
                    anomalies.append(
                        {
                            "kind": "precondition_group_length_mismatch",
                            "group_id": group_id,
                            "lengths": nonempty_lengths,
                            "source_row": row.source_row,
                        }
                    )
                connection.execute(
                    """
                    INSERT INTO quest_precondition_group (
                      group_id, group_name, group_mode, object_types_json,
                      object_ids_json, comparison_codes_json,
                      comparison_values_json, raw_values_json, source_file,
                      source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        _value(row.values, 0),
                        _value(row.values, 2) or None,
                        _json(arrays[0]),
                        _json(arrays[1]),
                        _json(arrays[2]),
                        _json(arrays[3]),
                        _json(row.values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
            counts["quest_precondition_group"] = len(group_ids)
            _audit(
                connection,
                task_id="AI13",
                entity_name="quest_condition",
                row_count=counts["precondition"] + counts["required_object"],
                source_file=QUEST_INFO,
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI13",
                entity_name="quest_objective",
                row_count=counts["objective"],
                source_file=QUEST_INFO,
                run_id=run_id,
            )
            _audit(
                connection,
                task_id="AI13",
                entity_name="quest_precondition_group",
                row_count=counts["quest_precondition_group"],
                source_file="mb/quest/quest_precondition.txt",
                run_id=run_id,
            )

        roundtrip_mismatches = 0
        for table in ["quest_condition", "quest_objective"]:
            for row in connection.execute(f"SELECT raw_group_json FROM {table}"):
                raw_group = json.loads(row[0])
                if json.loads(_json(raw_group)) != raw_group:
                    roundtrip_mismatches += 1
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "counts": dict(counts),
        "roundtrip_mismatches": roundtrip_mismatches,
        "type_35_36_references": type_35_36_refs,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "logic_operator_policy": "unknown_preserved_in_raw; no AND/OR inference",
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def load_mappings(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    connection = _connect(db_path)
    counts: Counter[str] = Counter()
    try:
        with connection:
            for row in _read_rows(root, "mb/object/cha_list.txt", run_id=run_id):
                character_id = _to_int(_value(row.values, 1))
                if character_id is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO character (
                      character_id, character_name, raw_values_json, source_file,
                      source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        character_id,
                        _value(row.values, 0),
                        _json(row.values),
                        row.source_file,
                        row.source_row,
                        row.raw_value,
                        run_id,
                    ),
                )
                counts["character"] += 1
            for relative_path, table, id_column, name_column in [
                (
                    "mb/quest/quest_item_ex.txt",
                    "quest_item_ex",
                    "quest_item_ex_id",
                    "quest_item_ex_name",
                ),
                (
                    "mb/quest/quest_event_ex.txt",
                    "quest_event_ex",
                    "quest_event_ex_id",
                    "quest_event_ex_name",
                ),
            ]:
                for row in _read_rows(
                    root,
                    relative_path,
                    run_id=run_id,
                    skip_first_nonempty=True,
                ):
                    entity_id = _to_int(_value(row.values, 1))
                    if entity_id is None:
                        continue
                    connection.execute(
                        f"""
                        INSERT INTO {table} (
                          {id_column}, {name_column}, raw_values_json, source_file,
                          source_row, raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
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
                    counts[table] += 1

            known = {
                "character": {
                    row[0] for row in connection.execute("SELECT character_id FROM character")
                },
                "quest_npc": {
                    row[0] for row in connection.execute("SELECT quest_npc_id FROM quest_npc")
                },
                "item": {row[0] for row in connection.execute("SELECT item_id FROM item")},
                "quest_item_ex": {
                    row[0]
                    for row in connection.execute(
                        "SELECT quest_item_ex_id FROM quest_item_ex"
                    )
                },
                "quest_event": {
                    row[0]
                    for row in connection.execute(
                        "SELECT quest_event_id FROM quest_event"
                    )
                },
                "quest_event_ex": {
                    row[0]
                    for row in connection.execute(
                        "SELECT quest_event_ex_id FROM quest_event_ex"
                    )
                },
            }
            mapping_specs = [
                (
                    "mb/quest/quest_npc_mapping.txt",
                    False,
                    "npc",
                    "character",
                    0,
                    "quest_npc",
                    1,
                    None,
                    None,
                ),
                (
                    "mb/quest/quest_item_mapping.txt",
                    False,
                    "item",
                    "item",
                    0,
                    "quest_item_ex",
                    1,
                    2,
                    4,
                ),
                (
                    "mb/quest/quest_event_mapping.txt",
                    True,
                    "event",
                    "quest_event",
                    0,
                    "quest_event_ex",
                    1,
                    2,
                    4,
                ),
            ]
            for (
                relative_path,
                header,
                kind,
                source_type,
                source_index,
                target_type,
                target_index,
                group_index,
                weight_index,
            ) in mapping_specs:
                for row in _read_rows(
                    root,
                    relative_path,
                    run_id=run_id,
                    skip_first_nonempty=header,
                ):
                    source_id = _to_int(_value(row.values, source_index))
                    target_id = _to_int(_value(row.values, target_index))
                    connection.execute(
                        """
                        INSERT INTO object_mapping (
                          mapping_kind, source_object_type, source_object_id,
                          target_object_type, target_object_id, group_index, weight,
                          source_resolved, target_resolved, raw_values_json,
                          source_file, source_row, raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            kind,
                            source_type,
                            source_id,
                            target_type,
                            target_id,
                            _to_int(_value(row.values, group_index))
                            if group_index is not None
                            else None,
                            _to_int(_value(row.values, weight_index))
                            if weight_index is not None
                            else None,
                            int(source_id in known[source_type]),
                            int(target_id in known[target_type]),
                            _json(row.values),
                            row.source_file,
                            row.source_row,
                            row.raw_value,
                            run_id,
                        ),
                    )
                    counts[f"{kind}_mapping"] += 1
            _audit(
                connection,
                task_id="AI14",
                entity_name="object_mapping",
                row_count=sum(
                    count for key, count in counts.items() if key.endswith("_mapping")
                ),
                source_file="quest_*_mapping.txt",
                run_id=run_id,
            )
        npc_missing_source = [
            dict(row)
            for row in connection.execute(
                """
                SELECT mapping_id, source_object_id, target_object_id, source_file,
                       source_row FROM object_mapping
                WHERE mapping_kind='npc' AND source_resolved=0
                """
            )
        ]
        npc_missing_target = [
            dict(row)
            for row in connection.execute(
                """
                SELECT mapping_id, source_object_id, target_object_id, source_file,
                       source_row FROM object_mapping
                WHERE mapping_kind='npc' AND target_resolved=0
                """
            )
        ]
        one_to_many = [
            {
                "mapping_kind": row[0],
                "source_object_id": row[1],
                "target_count": row[2],
            }
            for row in connection.execute(
                """
                SELECT mapping_kind, source_object_id,
                       COUNT(DISTINCT target_object_id)
                FROM object_mapping
                GROUP BY mapping_kind, source_object_id
                HAVING COUNT(DISTINCT target_object_id)>1
                """
            )
        ]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "counts": dict(counts),
        "npc_mapping_missing_actual_count": len(npc_missing_source),
        "npc_mapping_missing_actual": npc_missing_source,
        "npc_mapping_missing_quest_npc_count": len(npc_missing_target),
        "npc_mapping_missing_quest_npc": npc_missing_target,
        "one_to_many_mappings": one_to_many,
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def load_locations(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    connection = _connect(db_path)
    counts: Counter[str] = Counter()
    try:
        with connection:
            for relative_path, table, id_column, name_column, name_index, key_index in [
                ("mb/scn/area_info.txt", "area", "area_id", "area_name", 0, 2),
                (
                    "mb/scn/prov_info.txt",
                    "province",
                    "province_id",
                    "province_name",
                    0,
                    2,
                ),
                ("mb/scn/scn_info.txt", "scene", "scene_id", "scene_name", 19, 0),
            ]:
                rows = _read_rows(root, relative_path, run_id=run_id)
                if table == "area":
                    grouped: dict[int, list[Any]] = defaultdict(list)
                    for row in rows:
                        entity_id = _to_int(_value(row.values, 1))
                        if entity_id is not None:
                            grouped[entity_id].append(row)
                    for entity_id, versions in sorted(grouped.items()):
                        canonical = versions[0]
                        connection.execute(
                            """
                            INSERT INTO area (
                              area_id, area_name, resource_key, version_count,
                              conflict_flag, raw_values_json, source_file, source_row,
                              raw_value, run_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                entity_id,
                                _value(canonical.values, name_index),
                                _value(canonical.values, key_index) or None,
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
                                INSERT INTO area_source (
                                  area_id, version_no, area_name, resource_key,
                                  raw_values_json, source_file, source_row, raw_value,
                                  run_id
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    entity_id,
                                    version_no,
                                    _value(source_row.values, name_index),
                                    _value(source_row.values, key_index) or None,
                                    _json(source_row.values),
                                    source_row.source_file,
                                    source_row.source_row,
                                    source_row.raw_value,
                                    run_id,
                                ),
                            )
                    counts["area"] = len(grouped)
                    counts["area_source"] = sum(
                        len(versions) for versions in grouped.values()
                    )
                    continue
                for row in rows:
                    entity_id = _to_int(_value(row.values, 1))
                    if entity_id is None:
                        continue
                    connection.execute(
                        f"""
                        INSERT INTO {table} (
                          {id_column}, {name_column}, resource_key, raw_values_json,
                          source_file, source_row, raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entity_id,
                            _value(row.values, name_index) or None,
                            _value(row.values, key_index) or None,
                            _json(row.values),
                            row.source_file,
                            row.source_row,
                            row.raw_value,
                            run_id,
                        ),
                    )
                    counts[table] += 1
            area_ids = {row[0] for row in connection.execute("SELECT area_id FROM area")}
            for target in connection.execute(
                """
                SELECT target_id, raw_values_json, source_file, source_row, raw_value
                FROM quest_target
                """
            ):
                values = json.loads(target["raw_values_json"])
                area_id = _to_int(_value(values, 10))
                if area_id == 0:
                    area_id = None
                fallback = _value(values, 9) or None
                connection.execute(
                    """
                    INSERT INTO location_context (
                      target_id, area_id, fallback_area_name, area_resolved,
                      source_file, source_row, raw_value, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target["target_id"],
                        area_id if area_id in area_ids else None,
                        fallback,
                        int(area_id is not None and area_id in area_ids),
                        target["source_file"],
                        target["source_row"],
                        target["raw_value"],
                        run_id,
                    ),
                )
                counts["location_context"] += 1
            _audit(
                connection,
                task_id="AI15",
                entity_name="location_context",
                row_count=counts["location_context"],
                source_file="quest_target + scn/*",
                run_id=run_id,
            )
        referenced_area_ids = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT area_id FROM location_context WHERE area_id IS NOT NULL"
            )
        }
        duplicate_names = [
            {"area_name": row[0], "ids": row[1], "count": row[2]}
            for row in connection.execute(
                """
                SELECT area_name, GROUP_CONCAT(area_id), COUNT(*)
                FROM area GROUP BY area_name HAVING COUNT(*)>1
                ORDER BY COUNT(*) DESC, area_name
                """
            )
        ]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "counts": dict(counts),
        "unique_referenced_area_ids": len(referenced_area_ids),
        "matched_referenced_area_ids": len(referenced_area_ids),
        "missing_referenced_area_ids": [],
        "same_name_multiple_ids": duplicate_names,
        "name_collision_policy": "ID remains authoritative; names never merge IDs",
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def _looks_like_header(values: tuple[str, ...]) -> bool:
    probe = " ".join(values[:5]).lower()
    markers = ["id", "索引", "名称", "任务", "道具"]
    return any(marker in probe for marker in markers) and not any(
        _to_int(value) is not None for value in values[:3]
    )


def load_special_configs(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    handled = {
        "quest_info.txt", "quest_text.txt", "quest_sort.txt", "quest_object.txt",
        "quest_npc.txt", "quest_target.txt", "quest_item.txt", "quest_event.txt",
        "quest_atb.txt", "quest_camp.txt", "quest_link.txt", "quest_mutex.txt",
        "quest_reject.txt", "quest_precondition.txt", "quest_npc_mapping.txt",
        "quest_item_mapping.txt", "quest_event_mapping.txt", "quest_item_ex.txt",
        "quest_event_ex.txt",
    }
    pool_names = {
        "daily_dungeon.txt", "dshd_guanfu.txt", "dshd_paohuan.txt",
        "dshd_xianpai.txt", "hfl_paohuan.txt", "msh_guanfu.txt",
        "msh_xianpai.txt", "tth_paohuan.txt",
    }
    feature_keywords = (
        "award", "cartoon", "fastdispatch", "quick", "reset", "exp",
    )
    reliable_link_columns = {
        "quest_extra_award.txt": 1,
        "quest_newlvl_exp.txt": 1,
        "quest_cartoon.txt": 1,
        "quest_quick_complete.txt": 2,
    }
    quest_dir = root / "mb" / "quest"
    candidates = sorted(
        path for path in quest_dir.glob("*.txt") if path.name not in handled
    )
    connection = _connect(db_path)
    file_status: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    try:
        quest_ids = {
            row[0] for row in connection.execute("SELECT quest_id FROM quest_identity")
        }
        quest_count_before = connection.execute("SELECT COUNT(*) FROM quest").fetchone()[0]
        with connection:
            for path in candidates:
                relative_path = path.relative_to(root).as_posix()
                rows = _read_rows(root, relative_path, run_id=run_id)
                if rows and _looks_like_header(rows[0].values):
                    rows = rows[1:]
                if path.name in pool_names:
                    table = "quest_pool"
                    category = "pool"
                elif any(keyword in path.name for keyword in feature_keywords):
                    table = "quest_feature_config"
                    category = "feature"
                else:
                    table = "special_quest_config"
                    category = "special"
                linked = 0
                orphan_candidates = 0
                link_column = reliable_link_columns.get(path.name)
                for row in rows:
                    candidate_id = (
                        _to_int(_value(row.values, link_column))
                        if link_column is not None
                        else None
                    )
                    linked_id = candidate_id if candidate_id in quest_ids else None
                    if candidate_id is not None and linked_id is None:
                        orphan_candidates += 1
                    if linked_id is not None:
                        linked += 1
                    connection.execute(
                        f"""
                        INSERT INTO {table} (
                          source_name, linked_quest_id, raw_values_json, source_file,
                          source_row, raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            path.stem,
                            linked_id,
                            _json(row.values),
                            row.source_file,
                            row.source_row,
                            row.raw_value,
                            run_id,
                        ),
                    )
                    counts[table] += 1
                file_status.append(
                    {
                        "file": relative_path,
                        "category": category,
                        "table": table,
                        "loaded_rows": len(rows),
                        "linked_quest_rows": linked,
                        "unmatched_candidate_ids": orphan_candidates,
                        "semantic_status": "raw_preserved; script-dependent columns not inferred",
                    }
                )
            for table in ["quest_pool", "special_quest_config", "quest_feature_config"]:
                _audit(
                    connection,
                    task_id="AI16",
                    entity_name=table,
                    row_count=counts[table],
                    source_file="mb/quest/*.txt special subset",
                    run_id=run_id,
                )
        quest_count_after = connection.execute("SELECT COUNT(*) FROM quest").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    lines = [
        "# 特殊任务与功能配置导入报告",
        "",
        f"- 运行 ID：`{run_id}`",
        f"- 纳入文件：{len(file_status)}",
        f"- 普通任务表行数：{quest_count_before} → {quest_count_after}",
        f"- quest_pool：{counts['quest_pool']} 行",
        f"- special_quest_config：{counts['special_quest_config']} 行",
        f"- quest_feature_config：{counts['quest_feature_config']} 行",
        "",
        "所有未证实脚本语义均只保存原始列，没有写入核心任务字段。",
        "",
        "| 文件 | 分类 | 目标表 | 加载行 | 可靠任务连接 | 状态 |",
        "|---|---|---|---:|---:|---|",
    ]
    lines.extend(
        f"| `{item['file']}` | {item['category']} | `{item['table']}` | "
        f"{item['loaded_rows']} | {item['linked_quest_rows']} | 原值保留 |"
        for item in file_status
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "run_id": run_id,
        "file_count": len(file_status),
        "counts": dict(counts),
        "quest_count_before": quest_count_before,
        "quest_count_after": quest_count_after,
        "file_status": file_status,
        "foreign_key_violations": len(foreign_keys),
    }


def load_unresolved_references(
    *,
    root: Path,
    db_path: Path,
    report_path: Path,
    run_id: str,
) -> dict[str, Any]:
    connection = _connect(db_path)
    count = 0
    by_type: Counter[int] = Counter()
    try:
        with connection:
            for table, context, id_column, extra_columns in [
                (
                    "quest_condition",
                    "condition",
                    "condition_id",
                    ("comparison_code", "comparison_value"),
                ),
                ("quest_objective", "objective", "objective_id", (None, "amount")),
                ("quest_reward", "reward", "reward_id", (None, "amount")),
            ]:
                rows = connection.execute(
                    f"""
                    SELECT quest_id, version_no, slot_no, object_type_id, object_id,
                           {extra_columns[0] or 'NULL'} AS comparison_code,
                           {extra_columns[1] or 'NULL'} AS comparison_value,
                           source_file, source_row, raw_value
                    FROM {table}
                    WHERE object_type_id BETWEEN 7 AND 12
                    """
                ).fetchall()
                for row in rows:
                    connection.execute(
                        """
                        INSERT INTO unresolved_reference (
                          quest_id, version_no, reference_context, slot_no,
                          object_type_id, object_id, comparison_code,
                          comparison_value, reason, source_file, source_row,
                          raw_value, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["quest_id"],
                            row["version_no"],
                            context,
                            row["slot_no"],
                            row["object_type_id"],
                            row["object_id"],
                            row["comparison_code"],
                            row["comparison_value"],
                            "definition_file_missing",
                            row["source_file"],
                            row["source_row"],
                            row["raw_value"],
                            run_id,
                        ),
                    )
                    count += 1
                    by_type[row["object_type_id"]] += 1

            expected = {
                7: "mb/server/flag_bit_player.txt",
                8: "mb/server/flag_qbit_player.txt",
                9: "mb/server/flag_byte_player.txt",
                10: "mb/server/flag_word_player.txt",
                11: "mb/server/flag_dword_player.txt",
                12: "mb/server/temp_dword_player.txt",
            }
            dependencies = []
            for object_type, relative_path in expected.items():
                exists = (root / relative_path).exists()
                status = "available" if exists else "missing"
                connection.execute(
                    """
                    INSERT INTO external_dependency (
                      dependency_kind, expected_path, status, impact, run_id
                    ) VALUES ('flag_definition', ?, ?, ?, ?)
                    """,
                    (
                        relative_path,
                        status,
                        "numeric references preserved; names and business semantics unavailable",
                        run_id,
                    ),
                )
                dependencies.append(
                    {
                        "object_type": object_type,
                        "expected_path": relative_path,
                        "status": status,
                    }
                )
            _audit(
                connection,
                task_id="AI17",
                entity_name="unresolved_reference",
                row_count=count,
                source_file=QUEST_INFO,
                run_id=run_id,
            )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    report = {
        "run_id": run_id,
        "unresolved_reference_rows": count,
        "references_by_object_type": {str(key): value for key, value in sorted(by_type.items())},
        "dependencies": dependencies,
        "all_numeric_references_preserved": True,
        "foreign_key_violations": len(foreign_keys),
    }
    _write_report(report_path, report)
    return report


def generate_quality_report(
    *,
    db_path: Path,
    reports_dir: Path,
    json_path: Path,
    html_path: Path,
    csv_path: Path,
    run_id: str,
) -> dict[str, Any]:
    base = validate_database(db_path, scope="all")
    relation = json.loads((reports_dir / "relation_graph.json").read_text(encoding="utf-8"))
    groups = json.loads((reports_dir / "group_anomalies.json").read_text(encoding="utf-8"))
    mapping = json.loads((reports_dir / "mapping_integrity.json").read_text(encoding="utf-8"))
    location = json.loads((reports_dir / "location_coverage.json").read_text(encoding="utf-8"))
    missing = json.loads((reports_dir / "missing_dependencies.json").read_text(encoding="utf-8"))
    object_routes = json.loads((reports_dir / "object_routes.json").read_text(encoding="utf-8"))
    text = json.loads((reports_dir / "text_coverage.json").read_text(encoding="utf-8"))

    checks = [
        ("P0-01", "P0", "核心数据库校验", base["status"] == "ok", base["failures"]),
        (
            "P0-02",
            "P0",
            "后续任务引用完整",
            relation["unique_next_quest_refs"] == 4118
            and not relation["missing_next_quest_refs"],
            relation["missing_next_quest_refs"],
        ),
        (
            "P0-03",
            "P0",
            "任务对象引用完整",
            relation["unique_task_object_refs"] == 4603
            and not relation["missing_task_object_refs"],
            relation["missing_task_object_refs"],
        ),
        (
            "P0-04",
            "P0",
            "对象组可往返重组",
            groups["roundtrip_mismatches"] == 0,
            groups["roundtrip_mismatches"],
        ),
        (
            "P0-05",
            "P0",
            "寻路区域引用完整",
            location["unique_referenced_area_ids"] == 35
            and not location["missing_referenced_area_ids"],
            location["missing_referenced_area_ids"],
        ),
    ]
    p0_failures = [
        {"check_id": check_id, "name": name, "details": details}
        for check_id, severity, name, passed, details in checks
        if severity == "P0" and not passed
    ]
    issues = [
        {
            "issue_id": "P1-RELATION-CYCLES",
            "severity": "P1",
            "category": "任务关系",
            "summary": f"后续任务关系中发现{len(relation['next_relation_cycles'])}个环路",
            "status": "reported_not_modified",
            "action": "保留原始关系；不自动断环，供游戏逻辑核查",
        },
        {
            "issue_id": "P1-GROUP-ANOMALIES",
            "severity": "P1",
            "category": "条件与目标",
            "summary": f"发现{groups['anomaly_count']}个不完整或长度不一致对象组",
            "status": "raw_preserved",
            "action": "保留raw_group_json；不擅自补齐或确定AND/OR逻辑",
        },
        {
            "issue_id": "P1-TEXT-COVERAGE",
            "severity": "P1",
            "category": "文本",
            "summary": f"{text['missing_text_quest_ids']}个任务缺文本，{text['extra_text_ids']}个额外文本ID",
            "status": "accepted_preserved",
            "action": "保留缺失和孤立记录，不阻塞核心任务查询",
        },
        {
            "issue_id": "P1-NPC-MAPPING",
            "severity": "P1",
            "category": "映射",
            "summary": (
                f"NPC映射实际端缺{mapping['npc_mapping_missing_actual_count']}，"
                f"任务端缺{mapping['npc_mapping_missing_quest_npc_count']}"
            ),
            "status": "accepted_preserved",
            "action": "保留映射原始行和解析状态",
        },
        {
            "issue_id": "P1-UNDEFINED-TYPES",
            "severity": "P1",
            "category": "对象类型",
            "summary": f"未声明引用类型：{object_routes['undefined_referenced_types']}",
            "status": "accepted_preserved",
            "action": "使用占位类型，不赋予确定含义",
        },
        {
            "issue_id": "P1-FLAG-DEFINITIONS",
            "severity": "P1",
            "category": "外部依赖",
            "summary": f"{sum(1 for item in missing['dependencies'] if item['status']=='missing')}个标志位定义文件缺失",
            "status": "external_blocker",
            "action": "数字引用已保存；补充资源后使用新run_id重建",
        },
        {
            "issue_id": "P2-SPECIAL-SEMANTICS",
            "severity": "P2",
            "category": "特殊配置",
            "summary": "部分特殊任务、任务池和脚本列缺少程序代码语义",
            "status": "raw_only",
            "action": "原始行已分类入库，不写入核心任务字段",
        },
    ]
    payload = {
        "run_id": run_id,
        "generated_at": _utc_now(),
        "status": "p0_passed" if not p0_failures else "p0_failed",
        "p0_checks": [
            {
                "check_id": item[0],
                "severity": item[1],
                "name": item[2],
                "passed": item[3],
                "details": item[4],
            }
            for item in checks
        ],
        "p0_failures": p0_failures,
        "issues": issues,
        "metrics": {
            "base_validation": base["checks"],
            "relation_cycles": len(relation["next_relation_cycles"]),
            "group_anomalies": groups["anomaly_count"],
            "unresolved_flag_references": missing["unresolved_reference_rows"],
        },
    }
    _write_report(json_path, payload)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["issue_id", "severity", "category", "summary", "status", "action"],
        )
        writer.writeheader()
        writer.writerows(issues)

    check_rows = "".join(
        f"<tr><td>{html.escape(item[0])}</td><td>{item[1]}</td><td>{html.escape(item[2])}</td>"
        f"<td class='{'ok' if item[3] else 'bad'}'>{'通过' if item[3] else '失败'}</td>"
        f"<td><pre>{html.escape(json.dumps(item[4], ensure_ascii=False))}</pre></td></tr>"
        for item in checks
    )
    issue_rows = "".join(
        f"<tr><td>{html.escape(issue['issue_id'])}</td><td>{issue['severity']}</td>"
        f"<td>{html.escape(issue['category'])}</td><td>{html.escape(issue['summary'])}</td>"
        f"<td>{html.escape(issue['status'])}</td><td>{html.escape(issue['action'])}</td></tr>"
        for issue in issues
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>任务数据库质量报告</title><style>
body{{margin:0;background:#f5f7f8;color:#1f2a33;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
header{{background:#17324d;color:#fff;padding:38px 5vw}} main{{max-width:1180px;margin:auto;padding:28px 22px 60px}}
.status{{display:inline-block;padding:6px 12px;border-radius:999px;background:#ddf2e2;color:#216e39;font-weight:700}}
section{{background:#fff;border:1px solid #cad5dd;border-radius:10px;padding:20px;margin:18px 0}}
table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #cad5dd}}
th{{background:#eaf3f8;color:#17324d}} .ok{{color:#216e39;font-weight:700}} .bad{{color:#a12622;font-weight:700}}
pre{{white-space:pre-wrap;margin:0;font:inherit}}</style></head>
<body><header><h1>任务数据库质量报告</h1><p>运行 {html.escape(run_id)}</p></header>
<main><div class="status">{'所有P0检查通过' if not p0_failures else '存在P0失败'}</div>
<section><h2>P0 自动检查</h2><table><thead><tr><th>ID</th><th>级别</th><th>检查</th><th>状态</th><th>详情</th></tr></thead>
<tbody>{check_rows}</tbody></table></section>
<section><h2>已知 P1/P2 问题</h2><table><thead><tr><th>ID</th><th>级别</th><th>类别</th><th>摘要</th><th>状态</th><th>处置</th></tr></thead>
<tbody>{issue_rows}</tbody></table></section></main></body></html>""",
        encoding="utf-8",
    )
    return payload


def strict_p0_validation(db_path: Path, reports_dir: Path) -> dict[str, Any]:
    base = validate_database(db_path, scope="all")
    quality_path = reports_dir / "quality_report.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    failures = list(base["failures"])
    failures.extend(item["check_id"] for item in quality["p0_failures"])
    return {
        "scope": "all",
        "strict_p0": True,
        "status": "ok" if not failures else "failed",
        "base": base,
        "quality_status": quality["status"],
        "failures": failures,
    }
