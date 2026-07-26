from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DECLARED_TYPES = {
    "0": "integer",
    "1": "string",
    "2": "float",
    "3": "vector",
    "4": "integer_array",
    "5": "string_array",
    "6": "float_array",
    "7": "vector_array",
}


def _numeric(value: str) -> bool:
    try:
        int(value)
    except ValueError:
        return False
    return True


def _ids(path: Path, column: int) -> set[int]:
    result: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) > column and _numeric(fields[column]):
            result.add(int(fields[column]))
    return result


def _declared_quest_types(index_list: Path) -> list[str]:
    for line in index_list.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) > 6 and fields[2] == "quest/quest_info":
            codes = fields[6].split("*")
            return [DECLARED_TYPES.get(code, f"unknown_{code}") for code in codes]
    raise ValueError("quest/quest_info not found in index_list")


def _known_fields() -> dict[int, dict[str, str]]:
    known: dict[int, dict[str, str]] = {
        1: {"name": "quest_name", "meaning": "任务名称", "confidence": "high"},
        2: {"name": "quest_id", "meaning": "任务编号", "confidence": "high"},
        3: {"name": "category_id", "meaning": "任务类型/分类ID", "confidence": "high"},
        4: {"name": "max_level", "meaning": "最高等级", "confidence": "high"},
        5: {"name": "level_requirement", "meaning": "等级限制", "confidence": "high"},
        6: {"name": "accept_object_type", "meaning": "接取对象类型", "confidence": "high"},
        7: {"name": "accept_object_id", "meaning": "接取对象ID", "confidence": "high"},
        8: {"name": "submit_object_type", "meaning": "提交对象类型", "confidence": "high"},
        9: {"name": "submit_object_id", "meaning": "提交对象ID", "confidence": "high"},
        76: {"name": "reward_formula", "meaning": "奖励公式字符串（具体语义待确认）", "confidence": "low"},
        79: {"name": "reward_numeric_value", "meaning": "奖励数值（具体种类待确认）", "confidence": "low"},
        80: {"name": "next_quest_id", "meaning": "后续任务ID", "confidence": "high"},
        90: {"name": "tracking_target_id", "meaning": "任务追踪/寻路目标ID", "confidence": "high"},
    }
    for slot, start in enumerate(range(12, 28, 4), start=1):
        for offset, suffix, meaning in [
            (0, "object_type", "条件对象类型"),
            (1, "object_id", "条件对象ID"),
            (2, "comparison", "条件比较方式"),
            (3, "value", "条件比较值/数量"),
        ]:
            known[start + offset] = {
                "name": f"precondition_{slot}_{suffix}",
                "meaning": f"前置条件槽位{slot}：{meaning}",
                "confidence": "medium",
            }
    for prefix, starts, label in [
        ("required_object", range(28, 40, 3), "需求/消耗对象"),
        ("objective", range(40, 52, 3), "任务目标"),
        ("fixed_reward", range(52, 64, 3), "固定物品奖励"),
        ("reward", range(64, 76, 3), "通用奖励"),
    ]:
        for slot, start in enumerate(starts, start=1):
            for offset, suffix, meaning in [
                (0, "object_type", "对象类型"),
                (1, "object_id", "对象ID"),
                (2, "amount", "数量/参数"),
            ]:
                known[start + offset] = {
                    "name": f"{prefix}_{slot}_{suffix}",
                    "meaning": f"{label}槽位{slot}：{meaning}",
                    "confidence": "medium",
                }
    return known


def _empirical_type(values: list[str]) -> str:
    if not values:
        return "empty"
    if all(_numeric(value) for value in values):
        return "integer"
    if any("*" in value for value in values):
        return "star_delimited_string"
    return "string"


def infer_quest_info_schema(
    *,
    quest_info: Path,
    index_list: Path,
    quest_dir: Path,
) -> dict[str, object]:
    physical_lines = quest_info.read_text(encoding="utf-8").splitlines()
    data_rows = [
        line.split("\t")
        for line in physical_lines[1:]
        if line.strip()
    ]
    if len(data_rows) != 8829:
        raise RuntimeError(f"quest_info data row count {len(data_rows)} != 8829")
    if any(len(row) != 106 for row in data_rows):
        bad = Counter(len(row) for row in data_rows)
        raise RuntimeError(f"quest_info data widths are not 106: {bad}")

    declared_types = _declared_quest_types(index_list)
    if len(declared_types) != 106:
        raise RuntimeError(
            f"index_list declared {len(declared_types)} quest_info fields, not 106"
        )
    known = _known_fields()
    fields: list[dict[str, object]] = []
    for index in range(106):
        column = index + 1
        values = [row[index] for row in data_rows if row[index] != ""]
        counts = Counter(values)
        metadata = known.get(
            column,
            {
                "name": f"col_{column:03d}",
                "meaning": "未知字段，保留原始列",
                "confidence": "low",
            },
        )
        top_values = [
            {"value": value, "count": count}
            for value, count in counts.most_common(8)
        ]
        sample_values = list(dict.fromkeys(values))[:8]
        fields.append(
            {
                "column": column,
                "stable_name": metadata["name"],
                "meaning": metadata["meaning"],
                "confidence": metadata["confidence"],
                "declared_type": declared_types[index],
                "empirical_type": _empirical_type(values),
                "nullable": len(values) != len(data_rows),
                "nonempty_count": len(values),
                "empty_count": len(data_rows) - len(values),
                "unique_count": len(counts),
                "top_values": top_values,
                "sample_values": sample_values,
                "source": "quest_info column order; index_list declared type; empirical profile",
            }
        )

    quest_ids = [int(row[1]) for row in data_rows]
    duplicate_ids = sorted(
        value for value, count in Counter(quest_ids).items() if count > 1
    )
    duplicate_records = []
    for duplicate_id in duplicate_ids:
        records = []
        for source_row, row in enumerate(data_rows, start=2):
            if int(row[1]) != duplicate_id:
                continue
            records.append(
                {
                    "source_row": source_row,
                    "quest_name": row[0],
                    "nonempty_columns": {
                        str(index + 1): value
                        for index, value in enumerate(row)
                        if value != ""
                    },
                }
            )
        duplicate_records.append(
            {"quest_id": duplicate_id, "records": records}
        )

    qset = set(quest_ids)
    qsort = _ids(quest_dir / "quest_sort.txt", 1)
    qnpc = _ids(quest_dir / "quest_npc.txt", 1)
    qtarget = _ids(quest_dir / "quest_target.txt", 0)
    category_refs = {int(row[2]) for row in data_rows if _numeric(row[2])}
    accept_npc_refs = {
        int(row[6]) for row in data_rows if row[5] == "3" and _numeric(row[6])
    }
    submit_npc_refs = {
        int(row[8]) for row in data_rows if row[7] == "3" and _numeric(row[8])
    }
    next_refs = {
        int(row[79])
        for row in data_rows
        if _numeric(row[79]) and int(row[79]) != 0
    }
    target_refs = {
        int(row[89]) for row in data_rows if _numeric(row[89])
    }
    reference_checks = {
        "category_id": {
            "column": 3,
            "unique_refs": len(category_refs),
            "matched": len(category_refs & qsort),
            "missing": sorted(category_refs - qsort),
        },
        "accept_npc_id": {
            "columns": [6, 7],
            "unique_refs": len(accept_npc_refs),
            "matched": len(accept_npc_refs & qnpc),
            "missing": sorted(accept_npc_refs - qnpc),
        },
        "submit_npc_id": {
            "columns": [8, 9],
            "unique_refs": len(submit_npc_refs),
            "matched": len(submit_npc_refs & qnpc),
            "missing": sorted(submit_npc_refs - qnpc),
        },
        "next_quest_id": {
            "column": 80,
            "unique_refs": len(next_refs),
            "matched": len(next_refs & qset),
            "missing": sorted(next_refs - qset),
        },
        "tracking_target_id": {
            "column": 90,
            "unique_refs": len(target_refs),
            "matched": len(target_refs & qtarget),
            "missing": sorted(target_refs - qtarget),
        },
    }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": quest_info.as_posix(),
        "index_file": index_list.as_posix(),
        "physical_line_count": len(physical_lines),
        "header_line_count": 1,
        "data_row_count": len(data_rows),
        "column_count": 106,
        "unique_quest_id_count": len(qset),
        "duplicate_quest_ids": duplicate_records,
        "reference_checks": reference_checks,
        "fields": fields,
        "approval_topics": [
            {
                "id": "field_names",
                "question": "是否接受中等置信度的条件、目标和奖励槽位命名？",
                "recommendation": "接受为暂定名；保留列号和raw，后续发现代码证据时再迁移名称。",
            },
            {
                "id": "unknown_fields",
                "question": "未知列是否统一使用 col_### 并原样保留？",
                "recommendation": "是；不得根据少量样例编造业务含义。",
            },
            {
                "id": "duplicate_11257",
                "question": "任务ID 11257的两个原始版本如何进入规范化主表？",
                "recommendation": "两个原始版本均保留；规范化表增加版本序号和冲突标记，不静默选一个。",
            },
        ],
    }


def write_schema_outputs(
    *,
    quest_info: Path,
    index_list: Path,
    quest_dir: Path,
    output_dir: Path,
) -> dict[str, object]:
    schema = infer_quest_info_schema(
        quest_info=quest_info,
        index_list=index_list,
        quest_dir=quest_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    schema_path = output_dir / "quest_info_schema.json"
    low_path = output_dir / "low_confidence_fields.json"
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    low = {
        "schema_version": 1,
        "generated_at": schema["generated_at"],
        "source_file": schema["source_file"],
        "low_confidence_count": sum(
            field["confidence"] == "low" for field in schema["fields"]
        ),
        "fields": [
            field for field in schema["fields"]
            if field["confidence"] == "low"
        ],
        "approval_topics": schema["approval_topics"],
    }
    low_path.write_text(
        json.dumps(low, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return schema

