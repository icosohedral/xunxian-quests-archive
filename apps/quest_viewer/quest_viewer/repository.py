from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .db import readonly_connection
from .story_connections import story_context_relations


SERIES_CATEGORIES = {
    "【天劫路】",
    "【水月镜花】",
    "【修行】",
    "【十方劫】",
    "【魂魄劫】",
    "【天雷劫】",
    "【五行劫】",
    "【风云劫】",
    "【通天道】",
}

GROUPED_SUBCATEGORIES = {
    "玉灵山": "副本任务",
    "五行通天阵": "副本任务",
    "灵谷": "副本任务",
    "闯三关": "副本任务",
    "鬼王乱世": "副本任务",
    "官府当差任务": "声望任务",
    "仙派当值任务": "声望任务",
    "水下-龙太子党": "声望任务",
    "水下-龟丞相派": "声望任务",
    "仙友会任务": "声望任务",
    "降妖擂台": "声望任务",
    "门派任务": "阵营任务",
    "跨阵营任务": "阵营任务",
    "联盟任务": "阵营任务",
    "跨区任务": "阵营任务",
    "怒海争霸": "阵营任务",
    "元宝堂": "阵营任务",
    "联动任务": "活动任务",
    "定时任务": "活动任务",
    "周年庆": "活动任务",
    "极限挑战": "活动任务",
    "对抗战场": "活动任务",
    "砺炼任务": "活动任务",
    "休闲任务": "活动任务",
    "奇缘任务": "重复任务",
}

GROUPED_PARENT_CATEGORIES = set(GROUPED_SUBCATEGORIES.values())

AREA_FILTER_CHILDREN = {
    "宁海县": ("青牛坡",),
    "京城": ("野猪林", "中原", "京城西郊", "桃园", "京城南郊"),
    "石塘县": ("石塘大牢", "北郊林"),
    "茅山": ("石门县",),
    "东山岛": ("云梦山",),
    "地府": ("聚魂关",),
    "副本场景": (
        "东海龙宫",
        "皇陵下层",
        "破灭魔尊邪念副本",
        "白骨洞",
        "伏魔不周山",
        "灵感仙府",
        "寂静村落",
        "闯三关",
        "玉灵山",
        "五行劫",
        "五行通天阵",
        "魂魄劫",
        "【副本】皇陵穹顶·裂隙",
        "陈十四娘娘收妖传",
        "湘云水府副本",
        "副本",
        "九霄四时台",
    ),
    "湘云州": ("湘云水府",),
    "通天河": ("素贞观",),
    "摩云山": ("摩云山东部", "啸风洲"),
    "门派广场": ("众家门派",),
    "五岳山麓": ("五岳后山", "杏林", "县衙地牢"),
    "瑶池仙境": ("南天门", "星云战场"),
    "不周山": ("万仙台",),
    "乌鸡国": ("乌鸡国·上崖郡",),
    "女儿国": ("解阳山",),
    "车迟国": ("车迟国·东境",),
}

AREA_FILTER_MEMBERS = {
    parent: (parent, *children)
    for parent, children in AREA_FILTER_CHILDREN.items()
}
AREA_FILTER_PARENT_BY_CHILD = {
    child: parent
    for parent, children in AREA_FILTER_CHILDREN.items()
    for child in children
}


def _dicts(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _load_tab_name_index(path: Path) -> dict[int, str]:
    if not path.is_file():
        return {}
    names: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) < 2 or not fields[0].strip() or not fields[1].isdigit():
            continue
        names.setdefault(int(fields[1]), fields[0].strip())
    return names


def _experience_reward(raw_values_json: str | None) -> dict[str, Any] | None:
    raw_values = json.loads(raw_values_json) if raw_values_json else []
    formula = (
        str(raw_values[75]).strip()
        if len(raw_values) > 75 and raw_values[75]
        else ""
    )
    match = re.fullmatch(r"(?:cp|exp)\*(\d+)", formula)
    if not match:
        return None
    return {
        "reward_id": None,
        "reward_group": "experience",
        "slot_no": 1,
        "object_type_id": None,
        "object_type_name": "经验值",
        "object_id": None,
        "object_name": "经验值",
        "amount": int(match.group(1)),
        "formula": formula,
    }


def _category_taxonomy(
    raw_category_name: str | None,
) -> tuple[str | None, str | None]:
    if not raw_category_name:
        return None, None
    if raw_category_name.endswith("支线"):
        return "支线任务", raw_category_name[:-2]
    if raw_category_name.endswith("重复"):
        return "重复任务", raw_category_name[:-2]
    if raw_category_name in SERIES_CATEGORIES:
        return "系列任务", raw_category_name.strip("【】")
    if raw_category_name in GROUPED_SUBCATEGORIES:
        return GROUPED_SUBCATEGORIES[raw_category_name], raw_category_name
    if raw_category_name == "【正传】":
        return "正传任务", None
    if raw_category_name in GROUPED_PARENT_CATEGORIES:
        return raw_category_name, "未分类"
    return raw_category_name, None


def _main_category_name(raw_category_name: str | None) -> str | None:
    return _category_taxonomy(raw_category_name)[0]


def _sub_category_name(raw_category_name: str | None) -> str | None:
    return _category_taxonomy(raw_category_name)[1]


def _area_context(
    *,
    fallback_area_name: str | None,
    raw_values_json: str | None,
    inferred_parent_area_name: str | None = None,
    canonical_parent_area_name: str | None = None,
) -> dict[str, str | None]:
    raw_values = json.loads(raw_values_json) if raw_values_json else []
    parent_area_name = (
        str(raw_values[8]).strip() if len(raw_values) > 8 and raw_values[8] else None
    )
    child_area_name = (
        str(raw_values[9]).strip() if len(raw_values) > 9 and raw_values[9] else None
    ) or fallback_area_name
    parent_area_name = (
        canonical_parent_area_name
        or parent_area_name
        or inferred_parent_area_name
    )
    root_area_name = parent_area_name or fallback_area_name or child_area_name
    if (
        parent_area_name
        and child_area_name
        and parent_area_name != child_area_name
    ):
        display_area_name = f"{parent_area_name}·{child_area_name}"
    else:
        display_area_name = root_area_name or child_area_name
    return {
        "root_area_name": root_area_name,
        "subarea_name": (
            child_area_name
            if child_area_name and child_area_name != root_area_name
            else None
        ),
        "display_area_name": display_area_name,
    }


class QuestRepository:
    def __init__(self, database_path: Path, page_size: int = 5) -> None:
        self.database_path = database_path
        self.page_size = page_size
        resource_root = Path(__file__).resolve().parents[3] / "original_data" / "mb"
        self.title_names = _load_tab_name_index(
            resource_root / "etc" / "title_list.txt"
        )
        self.title_group_names = _load_tab_name_index(
            resource_root / "etc" / "title_group.txt"
        )
        self.state_names = _load_tab_name_index(
            resource_root / "skill" / "state_group.txt"
        )
        self.area_parent_by_id, self.area_parent_by_name = self._load_area_hierarchy()

    def _load_area_hierarchy(self) -> tuple[dict[int, str], dict[str, str]]:
        province_path = (
            Path(__file__).resolve().parents[3]
            / "original_data"
            / "mb"
            / "scn"
            / "prov_info.txt"
        )
        if not province_path.is_file():
            return {}, {}

        parent_by_id: dict[int, str] = {}
        for line in province_path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) < 4 or not fields[0].strip():
                continue
            parent_name = fields[0].strip()
            for raw_area_id in fields[3].split("*"):
                if raw_area_id.isdigit():
                    parent_by_id[int(raw_area_id)] = parent_name

        candidates_by_name: dict[str, set[str]] = {}
        with readonly_connection(self.database_path) as connection:
            for row in connection.execute("SELECT area_id, area_name FROM area"):
                parent_name = parent_by_id.get(row["area_id"])
                if parent_name and row["area_name"]:
                    candidates_by_name.setdefault(row["area_name"], set()).add(
                        parent_name
                    )
        parent_by_name = {
            area_name: next(iter(parent_names))
            for area_name, parent_names in candidates_by_name.items()
            if len(parent_names) == 1
        }
        return parent_by_id, parent_by_name

    def _canonical_area_name(
        self,
        area_id: int | None,
        fallback_area_name: str | None,
        explicit_parent_area_name: str | None,
        child_area_name: str | None,
        inferred_parent_area_name: str | None,
    ) -> str | None:
        by_id = (
            self.area_parent_by_id.get(area_id) if area_id is not None else None
        )
        by_name = self.area_parent_by_name.get(
            child_area_name or fallback_area_name or ""
        ) or self.area_parent_by_name.get(fallback_area_name or "")
        return (
            by_id
            or by_name
            or explicit_parent_area_name
            or inferred_parent_area_name
            or fallback_area_name
            or child_area_name
        )

    def _display_area_name(
        self,
        area_id: int | None,
        fallback_area_name: str | None,
        explicit_parent_area_name: str | None,
        child_area_name: str | None,
        inferred_parent_area_name: str | None,
    ) -> str | None:
        root_area_name = self._canonical_area_name(
            area_id,
            fallback_area_name,
            explicit_parent_area_name,
            child_area_name,
            inferred_parent_area_name,
        )
        leaf_area_name = child_area_name or fallback_area_name
        if root_area_name and leaf_area_name and root_area_name != leaf_area_name:
            return f"{root_area_name}·{leaf_area_name}"
        return root_area_name or leaf_area_name

    def _register_area_functions(self, connection: Any) -> None:
        connection.create_function(
            "canonical_area_name", 5, self._canonical_area_name
        )
        connection.create_function("display_area_name", 5, self._display_area_name)
        connection.create_function("main_category_name", 1, _main_category_name)
        connection.create_function("sub_category_name", 1, _sub_category_name)

    def search(
        self,
        *,
        q: str = "",
        npc: str = "",
        area: str = "",
        category: str = "",
        subcategory: str = "",
        page: int = 1,
    ) -> dict[str, Any]:
        page = max(1, page)
        conditions = ["rank_no = 1"]
        parameters: list[Any] = []
        q = q.strip()
        if q:
            conditions.append("quest_name LIKE ?")
            parameters.append(f"%{q}%")
        if npc.strip():
            conditions.append(
                """EXISTS (
                    SELECT 1 FROM quest_npc_detail qn
                    WHERE qn.quest_id = ranked.quest_id
                      AND qn.object_name LIKE ?
                )"""
            )
            parameters.append(f"%{npc.strip()}%")
        if area.strip():
            area_name = area.strip()
            area_members = AREA_FILTER_MEMBERS.get(area_name, (area_name,))
            placeholders = ", ".join("?" for _ in area_members)
            conditions.append(
                f"COALESCE(root_area_name, '') IN ({placeholders})"
            )
            parameters.extend(area_members)
        if category.strip():
            conditions.append("COALESCE(main_category_name, '') = ?")
            parameters.append(category.strip())
        if subcategory.strip():
            conditions.append("COALESCE(sub_category_name, '') = ?")
            parameters.append(subcategory.strip())

        where_sql = " AND ".join(conditions)
        cte = """
            WITH parent_counts AS (
                SELECT TRIM(json_extract(raw_values_json, '$[9]')) AS child_name,
                       TRIM(json_extract(raw_values_json, '$[8]')) AS parent_name,
                       COUNT(*) AS usage_count
                FROM quest_target
                WHERE NULLIF(TRIM(json_extract(raw_values_json, '$[8]')), '') IS NOT NULL
                  AND NULLIF(TRIM(json_extract(raw_values_json, '$[9]')), '') IS NOT NULL
                GROUP BY child_name, parent_name
            ),
            parent_map AS (
                SELECT child_name, parent_name
                FROM (
                    SELECT parent_counts.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY child_name
                               ORDER BY usage_count DESC, parent_name
                           ) AS preference_no
                    FROM parent_counts
                )
                WHERE preference_no=1
            ),
            enriched AS (
                SELECT qf.*,
                       canonical_area_name(
                           qf.area_id,
                           qf.area_name,
                           NULLIF(TRIM(json_extract(qt.raw_values_json, '$[8]')), ''),
                           NULLIF(TRIM(json_extract(qt.raw_values_json, '$[9]')), ''),
                           pm.parent_name
                       ) AS root_area_name,
                       NULLIF(TRIM(json_extract(qt.raw_values_json, '$[9]')), '')
                           AS subarea_name,
                       display_area_name(
                           qf.area_id,
                           qf.area_name,
                           NULLIF(TRIM(json_extract(qt.raw_values_json, '$[8]')), ''),
                           NULLIF(TRIM(json_extract(qt.raw_values_json, '$[9]')), ''),
                           pm.parent_name
                       ) AS display_area_name,
                       main_category_name(qf.category_name)
                           AS main_category_name,
                       sub_category_name(qf.category_name)
                           AS sub_category_name
                FROM quest_full qf
                LEFT JOIN quest_target qt ON qt.target_id=qf.tracking_target_id
                LEFT JOIN parent_map pm
                  ON pm.child_name=COALESCE(
                      NULLIF(TRIM(json_extract(qt.raw_values_json, '$[9]')), ''),
                      qf.area_name
                  )
            ),
            ranked AS (
                SELECT enriched.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY quest_id
                           ORDER BY source_row, version_no
                       ) AS rank_no,
                       COUNT(*) OVER (PARTITION BY quest_id) AS source_variant_count
                FROM enriched
            )
        """
        with readonly_connection(self.database_path) as connection:
            self._register_area_functions(connection)
            total = connection.execute(
                f"{cte} SELECT COUNT(*) FROM ranked WHERE {where_sql}",
                parameters,
            ).fetchone()[0]
            rows = _dicts(
                connection.execute(
                    f"""
                    {cte}
                    SELECT quest_id, version_no, conflict_flag, quest_name,
                           category_name, main_category_name, sub_category_name,
                           level_requirement, max_level,
                           accept_object_name, submit_object_name,
                           display_area_name AS area_name,
                           root_area_name, subarea_name,
                           text_row_count, objective_count, reward_count,
                           source_variant_count
                    FROM ranked
                    WHERE {where_sql}
                    ORDER BY level_requirement IS NULL,
                             level_requirement,
                             quest_id
                    LIMIT ? OFFSET ?
                    """,
                    [*parameters, self.page_size, (page - 1) * self.page_size],
                )
            )
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": self.page_size,
            "page_count": max(1, math.ceil(total / self.page_size)),
        }

    def facets(self) -> dict[str, list[dict[str, Any]]]:
        with readonly_connection(self.database_path) as connection:
            self._register_area_functions(connection)
            category_cte = """
                WITH classified AS (
                    SELECT qf.*,
                           main_category_name(qf.category_name)
                               AS main_category_name,
                           sub_category_name(qf.category_name)
                               AS sub_category_name,
                           ROW_NUMBER() OVER (
                               PARTITION BY quest_id
                               ORDER BY source_row, version_no
                           ) AS rank_no
                    FROM quest_full qf
                )
            """
            categories = _dicts(
                connection.execute(
                    f"""
                    {category_cte}
                    SELECT main_category_name AS name,
                           COUNT(*) AS task_count
                    FROM classified
                    WHERE rank_no=1
                      AND main_category_name IS NOT NULL
                      AND main_category_name <> ''
                    GROUP BY main_category_name
                    ORDER BY task_count DESC, main_category_name
                    """
                )
            )
            subcategories = _dicts(
                connection.execute(
                    f"""
                    {category_cte}
                    SELECT main_category_name AS parent_name,
                           sub_category_name AS name,
                           COUNT(*) AS task_count
                    FROM classified
                    WHERE rank_no=1
                      AND sub_category_name IS NOT NULL
                      AND sub_category_name <> ''
                    GROUP BY main_category_name, sub_category_name
                    ORDER BY main_category_name,
                             task_count DESC,
                             sub_category_name
                    """
                )
            )
            raw_areas = _dicts(
                connection.execute(
                    """
                    WITH parent_counts AS (
                        SELECT TRIM(json_extract(raw_values_json, '$[9]')) AS child_name,
                               TRIM(json_extract(raw_values_json, '$[8]')) AS parent_name,
                               COUNT(*) AS usage_count
                        FROM quest_target
                        WHERE NULLIF(TRIM(json_extract(raw_values_json, '$[8]')), '') IS NOT NULL
                          AND NULLIF(TRIM(json_extract(raw_values_json, '$[9]')), '') IS NOT NULL
                        GROUP BY child_name, parent_name
                    ),
                    parent_map AS (
                        SELECT child_name, parent_name
                        FROM (
                            SELECT parent_counts.*,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY child_name
                                       ORDER BY usage_count DESC, parent_name
                                   ) AS preference_no
                            FROM parent_counts
                        )
                        WHERE preference_no=1
                    ),
                    enriched AS (
                        SELECT qf.*,
                               canonical_area_name(
                                   qf.area_id,
                                   qf.area_name,
                                   NULLIF(TRIM(json_extract(qt.raw_values_json, '$[8]')), ''),
                                   NULLIF(TRIM(json_extract(qt.raw_values_json, '$[9]')), ''),
                                   pm.parent_name
                               ) AS root_area_name
                        FROM quest_full qf
                        LEFT JOIN quest_target qt
                          ON qt.target_id=qf.tracking_target_id
                        LEFT JOIN parent_map pm
                          ON pm.child_name=COALESCE(
                              NULLIF(TRIM(json_extract(qt.raw_values_json, '$[9]')), ''),
                              qf.area_name
                          )
                    ),
                    ranked AS (
                        SELECT enriched.*,
                               ROW_NUMBER() OVER (
                                   PARTITION BY quest_id
                                   ORDER BY source_row, version_no
                               ) AS rank_no
                        FROM enriched
                    )
                    SELECT ranked.root_area_name AS name,
                           MIN(ranked.level_requirement) AS min_level,
                           COUNT(DISTINCT ranked.quest_id) AS task_count
                    FROM ranked
                    WHERE ranked.rank_no=1
                      AND ranked.root_area_name IS NOT NULL
                      AND ranked.root_area_name <> ''
                    GROUP BY ranked.root_area_name
                    ORDER BY min_level IS NULL,
                             min_level,
                             MIN(ranked.quest_id),
                             ranked.root_area_name
                    """
                )
            )
            grouped_areas: dict[str, dict[str, Any]] = {}
            for order_no, item in enumerate(raw_areas):
                area_name = AREA_FILTER_PARENT_BY_CHILD.get(
                    item["name"], item["name"]
                )
                grouped = grouped_areas.setdefault(
                    area_name,
                    {
                        "name": area_name,
                        "min_level": item["min_level"],
                        "task_count": 0,
                        "_order": order_no,
                    },
                )
                item_level = item["min_level"]
                if item_level is not None and (
                    grouped["min_level"] is None
                    or item_level < grouped["min_level"]
                ):
                    grouped["min_level"] = item_level
                grouped["task_count"] += item["task_count"]
                grouped["_order"] = min(grouped["_order"], order_no)
            areas = sorted(
                grouped_areas.values(),
                key=lambda item: (
                    item["min_level"] is None,
                    item["min_level"] if item["min_level"] is not None else 0,
                    item["_order"],
                    item["name"],
                ),
            )
            for item in areas:
                item.pop("_order", None)
        return {
            "categories": categories,
            "subcategories": subcategories,
            "areas": areas,
        }

    def _resolve_object_name(
        self, connection: Any, object_type_id: int | None, object_id: int | None
    ) -> str | None:
        if object_id is None:
            return None
        if object_type_id == 20:
            return self.state_names.get(object_id)
        if object_type_id == 21:
            return self.title_names.get(object_id)
        if object_type_id == 22:
            return self.title_group_names.get(object_id)
        routes = {
            2: ("quest_item", "quest_item_id", "quest_item_name"),
            3: ("quest_npc", "quest_npc_id", "quest_npc_name"),
            5: ("quest", "quest_id", "quest_name"),
            6: ("quest_attribute", "attribute_id", "attribute_name"),
            13: ("quest_event", "quest_event_id", "quest_event_name"),
            15: ("quest_camp", "camp_id", "camp_name"),
        }
        route = routes.get(object_type_id)
        if not route:
            return None
        table, id_column, name_column = route
        row = connection.execute(
            f"SELECT {name_column} FROM {table} WHERE {id_column}=? LIMIT 1",
            (object_id,),
        ).fetchone()
        return row[0] if row else None

    def get(self, quest_id: int) -> dict[str, Any] | None:
        with readonly_connection(self.database_path) as connection:
            variants = _dicts(
                connection.execute(
                    "SELECT * FROM quest WHERE quest_id=? ORDER BY source_row, version_no",
                    (quest_id,),
                )
            )
            if not variants:
                return None

            primary = variants[0]
            version_no = primary["version_no"]
            summary_row = connection.execute(
                """
                SELECT * FROM quest_full
                WHERE quest_id=? AND version_no=?
                LIMIT 1
                """,
                (quest_id, version_no),
            ).fetchone()
            summary = dict(summary_row) if summary_row else dict(primary)
            target_area_row = connection.execute(
                """
                WITH current_target AS (
                    SELECT raw_values_json,
                           NULLIF(TRIM(json_extract(raw_values_json, '$[9]')), '')
                               AS child_name
                    FROM quest_target
                    WHERE target_id=?
                ),
                parent_counts AS (
                    SELECT TRIM(
                               json_extract(candidate.raw_values_json, '$[8]')
                           ) AS parent_name,
                           COUNT(*) AS usage_count
                    FROM quest_target candidate, current_target
                    WHERE NULLIF(
                              TRIM(json_extract(candidate.raw_values_json, '$[8]')),
                              ''
                          ) IS NOT NULL
                      AND TRIM(json_extract(candidate.raw_values_json, '$[9]'))
                          = current_target.child_name
                    GROUP BY parent_name
                )
                SELECT current_target.raw_values_json,
                       (
                           SELECT parent_name
                           FROM parent_counts
                           ORDER BY usage_count DESC, parent_name
                           LIMIT 1
                       ) AS inferred_parent_area_name
                FROM current_target
                LIMIT 1
                """,
                (summary.get("tracking_target_id"),),
            ).fetchone()
            target_raw_json = (
                target_area_row["raw_values_json"] if target_area_row else None
            )
            target_raw_values = json.loads(target_raw_json) if target_raw_json else []
            explicit_parent = (
                target_raw_values[8] if len(target_raw_values) > 8 else None
            )
            child_area = target_raw_values[9] if len(target_raw_values) > 9 else None
            inferred_parent = (
                target_area_row["inferred_parent_area_name"]
                if target_area_row
                else None
            )
            summary_area = _area_context(
                fallback_area_name=summary.get("area_name"),
                raw_values_json=target_raw_json,
                inferred_parent_area_name=inferred_parent,
                canonical_parent_area_name=self._canonical_area_name(
                    summary.get("area_id"),
                    summary.get("area_name"),
                    explicit_parent,
                    child_area,
                    inferred_parent,
                ),
            )
            summary.update(summary_area)
            summary["area_name"] = summary_area["display_area_name"]
            (
                summary["main_category_name"],
                summary["sub_category_name"],
            ) = _category_taxonomy(summary.get("category_name"))

            parsed_raw = [json.loads(row["raw_values_json"]) for row in variants]
            conflict_columns: list[int] = []
            if len(parsed_raw) > 1:
                for index in range(1, len(parsed_raw[0])):
                    if len({row[index] for row in parsed_raw}) > 1:
                        conflict_columns.append(index + 1)
            aliases = [
                row["quest_name"]
                for row in variants[1:]
                if row["quest_name"] != primary["quest_name"]
            ]
            safe_display_merge = len(variants) > 1 and not conflict_columns

            texts = _dicts(
                connection.execute(
                    """
                    SELECT * FROM quest_text_detail
                    WHERE quest_id=? ORDER BY text_row_id
                    """,
                    (quest_id,),
                )
            )
            endpoints = _dicts(
                connection.execute(
                    """
                    SELECT * FROM quest_npc_detail
                    WHERE quest_id=? AND version_no=?
                    ORDER BY endpoint_kind
                    """,
                    (quest_id, version_no),
                )
            )
            conditions = _dicts(
                connection.execute(
                    """
                    SELECT qc.*, ot.object_type_name
                    FROM quest_condition qc
                    LEFT JOIN object_type ot
                      ON ot.object_type_id=qc.object_type_id
                    WHERE qc.quest_id=? AND qc.version_no=?
                    ORDER BY qc.condition_kind, qc.slot_no
                    """,
                    (quest_id, version_no),
                )
            )
            for condition in conditions:
                condition["object_name"] = self._resolve_object_name(
                    connection,
                    condition["object_type_id"],
                    condition["object_id"],
                )
            objectives = _dicts(
                connection.execute(
                    """
                    SELECT qo.*, ot.object_type_name
                    FROM quest_objective qo
                    LEFT JOIN object_type ot
                      ON ot.object_type_id=qo.object_type_id
                    WHERE qo.quest_id=? AND qo.version_no=?
                    ORDER BY qo.slot_no
                    """,
                    (quest_id, version_no),
                )
            )
            for objective in objectives:
                objective["object_name"] = self._resolve_object_name(
                    connection,
                    objective["object_type_id"],
                    objective["object_id"],
                )
            rewards = _dicts(
                connection.execute(
                    """
                    SELECT * FROM quest_reward_detail
                    WHERE quest_id=? AND version_no=?
                    ORDER BY reward_group, slot_no
                    """,
                    (quest_id, version_no),
                )
            )
            for reward in rewards:
                if not reward.get("object_name"):
                    reward["object_name"] = self._resolve_object_name(
                        connection,
                        reward.get("object_type_id"),
                        reward.get("object_id"),
                    )
            experience_reward = _experience_reward(
                primary.get("raw_values_json")
            )
            if experience_reward:
                rewards.append(experience_reward)
            locations = _dicts(
                connection.execute(
                    """
                    SELECT ql.*, qt.raw_values_json,
                           (
                               SELECT TRIM(json_extract(candidate.raw_values_json, '$[8]'))
                               FROM quest_target candidate
                               WHERE NULLIF(
                                   TRIM(json_extract(candidate.raw_values_json, '$[8]')),
                                   ''
                               ) IS NOT NULL
                                 AND TRIM(json_extract(candidate.raw_values_json, '$[9]'))
                                     = TRIM(json_extract(qt.raw_values_json, '$[9]'))
                               GROUP BY TRIM(json_extract(candidate.raw_values_json, '$[8]'))
                               ORDER BY COUNT(*) DESC,
                                        TRIM(json_extract(candidate.raw_values_json, '$[8]'))
                               LIMIT 1
                           ) AS inferred_parent_area_name
                    FROM quest_location_detail ql
                    JOIN quest_target qt ON qt.target_id=ql.target_id
                    WHERE quest_id=? AND version_no=?
                    ORDER BY target_id
                    """,
                    (quest_id, version_no),
                )
            )
            for location in locations:
                location_raw_json = location.pop("raw_values_json", None)
                location_raw_values = (
                    json.loads(location_raw_json) if location_raw_json else []
                )
                explicit_parent = (
                    location_raw_values[8] if len(location_raw_values) > 8 else None
                )
                child_area = (
                    location_raw_values[9] if len(location_raw_values) > 9 else None
                )
                inferred_parent = location.pop(
                    "inferred_parent_area_name", None
                )
                location_area = _area_context(
                    fallback_area_name=location.get("area_name"),
                    raw_values_json=location_raw_json,
                    inferred_parent_area_name=inferred_parent,
                    canonical_parent_area_name=self._canonical_area_name(
                        location.get("area_id"),
                        location.get("area_name"),
                        explicit_parent,
                        child_area,
                        inferred_parent,
                    ),
                )
                location.update(location_area)
                location["area_name"] = location_area["display_area_name"]
            outgoing = _dicts(
                connection.execute(
                    """
                    SELECT * FROM quest_relation_detail
                    WHERE from_quest_id=? AND from_version_no=?
                    ORDER BY relation_type, slot_no
                    """,
                    (quest_id, version_no),
                )
            )
            incoming = _dicts(
                connection.execute(
                    """
                    SELECT * FROM quest_relation_detail
                    WHERE to_quest_id=?
                    ORDER BY relation_type, from_quest_id
                    """,
                    (quest_id,),
                )
            )
            story_connections = story_context_relations(quest_id)
            outgoing.extend(story_connections["outgoing"])
            incoming.extend(story_connections["incoming"])

        return {
            "summary": summary,
            "primary": primary,
            "aliases": aliases,
            "variants": [
                {
                    "version_no": row["version_no"],
                    "quest_name": row["quest_name"],
                    "source_file": row["source_file"],
                    "source_row": row["source_row"],
                }
                for row in variants
            ],
            "safe_display_merge": safe_display_merge,
            "conflict_columns": conflict_columns,
            "texts": texts,
            "endpoints": endpoints,
            "conditions": conditions,
            "objectives": objectives,
            "rewards": rewards,
            "locations": locations,
            "relations": {"incoming": incoming, "outgoing": outgoing},
        }

    def _related_quests(
        self,
        connection: Any,
        *,
        current_quest_id: int,
        role_kind: str,
        role_id: int,
    ) -> list[dict[str, Any]]:
        if role_kind == "target":
            tag_pattern = f"%<target:{role_id}>%"
            role_quest_ids = """
                SELECT quest_id
                FROM quest
                WHERE tracking_target_id=?
                UNION
                SELECT COALESCE(linked_quest_id, source_quest_id)
                FROM quest_text
                WHERE accept_dialogue LIKE ?
                   OR quest_description LIKE ?
                   OR hint_text LIKE ?
                   OR progress_dialogue LIKE ?
                   OR completion_dialogue LIKE ?
            """
            role_parameters: list[Any] = [
                role_id,
                tag_pattern,
                tag_pattern,
                tag_pattern,
                tag_pattern,
                tag_pattern,
            ]
        elif role_kind == "npc":
            role_quest_ids = """
                SELECT quest_id
                FROM quest
                WHERE (accept_object_type=3 AND accept_object_id=?)
                   OR (submit_object_type=3 AND submit_object_id=?)
                UNION
                SELECT quest_id
                FROM quest_objective
                WHERE object_type_id=3 AND object_id=?
            """
            role_parameters = [role_id, role_id, role_id]
        else:
            return []

        return _dicts(
            connection.execute(
                f"""
                WITH role_quests AS (
                    {role_quest_ids}
                ),
                ranked AS (
                    SELECT qf.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY quest_id
                               ORDER BY source_row, version_no
                           ) AS rank_no
                    FROM quest_full qf
                )
                SELECT ranked.quest_id, ranked.quest_name,
                       ranked.level_requirement, ranked.category_name,
                       ranked.area_name
                FROM ranked
                JOIN role_quests ON role_quests.quest_id=ranked.quest_id
                WHERE ranked.rank_no=1
                  AND ranked.quest_id<>?
                ORDER BY ranked.level_requirement IS NULL,
                         ranked.level_requirement,
                         ranked.quest_id
                """,
                [*role_parameters, current_quest_id],
            )
        )

    def resolve_npc_role(
        self,
        *,
        quest_id: int,
        npc_id: int,
        namespace: str = "任务 NPC",
    ) -> dict[str, Any] | None:
        with readonly_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT quest_npc_id AS object_id, quest_npc_name,
                       source_file, source_row
                FROM quest_npc
                WHERE quest_npc_id=?
                LIMIT 1
                """,
                (npc_id,),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            return {
                "status": "resolved",
                "kind": "npc",
                "label": result["quest_npc_name"],
                "namespace": namespace,
                **result,
                "related_quests": self._related_quests(
                    connection,
                    current_quest_id=quest_id,
                    role_kind="npc",
                    role_id=npc_id,
                ),
            }

    def resolve_friend_role(
        self,
        *,
        quest_id: int,
        version_no: int,
        name: str,
    ) -> dict[str, Any] | None:
        """Resolve <friend:name> only when the name identifies one role."""
        if not name:
            return None
        with readonly_connection(self.database_path) as connection:
            candidates = [
                ("npc", row["object_id"])
                for row in connection.execute(
                    """
                    SELECT DISTINCT quest_npc_id AS object_id
                    FROM quest_npc
                    WHERE quest_npc_name=?
                    """,
                    (name,),
                )
            ]
            candidates.extend(
                ("target", row["object_id"])
                for row in connection.execute(
                    """
                    SELECT DISTINCT target_id AS object_id
                    FROM quest_target
                    WHERE target_name=?
                    """,
                    (name,),
                )
            )
        if len(candidates) != 1:
            return None
        role_kind, object_id = candidates[0]
        if role_kind == "npc":
            resolution = self.resolve_npc_role(
                quest_id=quest_id,
                npc_id=object_id,
                namespace="关联角色",
            )
        else:
            resolution = self.resolve_tag(
                quest_id=quest_id,
                version_no=version_no,
                tag_kind="target",
                value=str(object_id),
            )
        if not resolution:
            return None
        return {
            **resolution,
            "kind": "friend",
            "namespace": "关联角色",
            "raw_tag": f"<friend:{name}>",
        }

    def resolve_tag(
        self,
        *,
        quest_id: int,
        version_no: int,
        tag_kind: str,
        value: str,
    ) -> dict[str, Any]:
        raw_tag = f"<{tag_kind}:{value}>"
        with readonly_connection(self.database_path) as connection:
            if tag_kind == "character" and value.strip().isdigit():
                call_profile_id = int(value.strip())
                row = connection.execute(
                    """
                    SELECT p.call_profile_id, p.speaker_profile_name,
                           p.variant_count, p.source_file, p.source_row,
                           (
                               SELECT call_text
                               FROM character_call_variant
                               WHERE call_profile_id=p.call_profile_id
                               ORDER BY variant_no
                               LIMIT 1
                           ) AS default_call,
                           (
                               SELECT GROUP_CONCAT(call_text, '、')
                               FROM (
                                   SELECT call_text
                                   FROM character_call_variant
                                   WHERE call_profile_id=p.call_profile_id
                                   ORDER BY variant_no
                               )
                           ) AS call_variants
                    FROM character_call_profile p
                    WHERE p.call_profile_id=?
                    """,
                    (call_profile_id,),
                ).fetchone()
                if row:
                    return {
                        "status": "resolved",
                        "kind": "character",
                        "label": row["default_call"] or f"玩家称谓 #{call_profile_id}",
                        "namespace": "动态玩家称谓",
                        **dict(row),
                        "selection_rule": "由游戏按玩家角色类型选择",
                        "raw_tag": raw_tag,
                    }
            target_match = re.match(r"^\s*(\d+)", value)
            if tag_kind == "target" and target_match:
                target_id = int(target_match.group(1))
                row = connection.execute(
                    """
                    SELECT qt.target_id, qt.target_name, qt.area_name,
                           qt.resource_key, qt.source_file, qt.source_row,
                           qt.raw_values_json,
                           (
                               SELECT TRIM(json_extract(candidate.raw_values_json, '$[8]'))
                               FROM quest_target candidate
                               WHERE NULLIF(
                                   TRIM(json_extract(candidate.raw_values_json, '$[8]')),
                                   ''
                               ) IS NOT NULL
                                 AND TRIM(json_extract(candidate.raw_values_json, '$[9]'))
                                     = TRIM(json_extract(qt.raw_values_json, '$[9]'))
                               GROUP BY TRIM(json_extract(candidate.raw_values_json, '$[8]'))
                               ORDER BY COUNT(*) DESC,
                                        TRIM(json_extract(candidate.raw_values_json, '$[8]'))
                               LIMIT 1
                           ) AS inferred_parent_area_name,
                           a.area_id
                    FROM quest_target qt
                    LEFT JOIN area a ON a.area_name=qt.area_name
                    WHERE qt.target_id=?
                    ORDER BY a.area_id LIMIT 1
                    """,
                    (target_id,),
                ).fetchone()
                if row:
                    result = dict(row)
                    target_raw_json = result.pop("raw_values_json", None)
                    target_raw_values = (
                        json.loads(target_raw_json) if target_raw_json else []
                    )
                    explicit_parent = (
                        target_raw_values[8]
                        if len(target_raw_values) > 8
                        else None
                    )
                    child_area = (
                        target_raw_values[9]
                        if len(target_raw_values) > 9
                        else None
                    )
                    inferred_parent = result.pop(
                        "inferred_parent_area_name", None
                    )
                    area = _area_context(
                        fallback_area_name=result.get("area_name"),
                        raw_values_json=target_raw_json,
                        inferred_parent_area_name=inferred_parent,
                        canonical_parent_area_name=self._canonical_area_name(
                            result.get("area_id"),
                            result.get("area_name"),
                            explicit_parent,
                            child_area,
                            inferred_parent,
                        ),
                    )
                    result.update(area)
                    result["area_name"] = area["display_area_name"]
                    return {
                        "status": "resolved",
                        "kind": "target",
                        "label": row["target_name"],
                        "namespace": "任务追踪目标",
                        **result,
                        "related_quests": self._related_quests(
                            connection,
                            current_quest_id=quest_id,
                            role_kind="target",
                            role_id=target_id,
                        ),
                        "raw_tag": raw_tag,
                    }
            if tag_kind == "enemy":
                rows = _dicts(
                    connection.execute(
                        """
                        SELECT qo.object_id, qo.amount, qn.quest_npc_name,
                               qn.source_file, qn.source_row
                        FROM quest_objective qo
                        JOIN quest_npc qn ON qn.quest_npc_id=qo.object_id
                        WHERE qo.quest_id=? AND qo.version_no=?
                          AND qo.object_type_id=3
                          AND qn.quest_npc_name=?
                        ORDER BY qo.slot_no
                        """,
                        (quest_id, version_no, value),
                    )
                )
                if len(rows) == 1:
                    return {
                        "status": "resolved",
                        "kind": "enemy",
                        "label": rows[0]["quest_npc_name"],
                        "namespace": "任务目标 NPC",
                        **rows[0],
                        "related_quests": self._related_quests(
                            connection,
                            current_quest_id=quest_id,
                            role_kind="npc",
                            role_id=rows[0]["object_id"],
                        ),
                        "raw_tag": raw_tag,
                    }
                if len(rows) > 1:
                    return {
                        "status": "ambiguous",
                        "kind": "enemy",
                        "label": value,
                        "namespace": "任务目标 NPC",
                        "candidates": rows,
                        "raw_tag": raw_tag,
                    }
            if tag_kind == "item":
                rows = _dicts(
                    connection.execute(
                        """
                        SELECT qo.object_id, qo.amount, qi.quest_item_name,
                               qi.source_file, qi.source_row
                        FROM quest_objective qo
                        JOIN quest_item qi ON qi.quest_item_id=qo.object_id
                        WHERE qo.quest_id=? AND qo.version_no=?
                          AND qo.object_type_id=2
                          AND qi.quest_item_name=?
                        ORDER BY qo.slot_no
                        """,
                        (quest_id, version_no, value),
                    )
                )
                if len(rows) == 1:
                    return {
                        "status": "resolved",
                        "kind": "item",
                        "label": rows[0]["quest_item_name"],
                        "namespace": "任务道具",
                        **rows[0],
                        "raw_tag": raw_tag,
                    }
                if len(rows) > 1:
                    return {
                        "status": "ambiguous",
                        "kind": "item",
                        "label": value,
                        "namespace": "任务道具",
                        "candidates": rows,
                        "raw_tag": raw_tag,
                    }
                return {
                    "status": "resolved",
                    "kind": "hint",
                    "label": value,
                    "namespace": "提示文本",
                    "raw_tag": raw_tag,
                }
        return {
            "status": "unresolved",
            "kind": tag_kind,
            "label": value,
            "namespace": {
                "target": "任务追踪目标",
                "enemy": "任务目标 NPC",
                "item": "任务道具",
                "character": "动态玩家称谓",
            }.get(tag_kind, "未知标签"),
            "raw_tag": raw_tag,
        }
