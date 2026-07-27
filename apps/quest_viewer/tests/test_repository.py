from __future__ import annotations

import sqlite3

import pytest

from quest_viewer.config import load_settings
from quest_viewer.db import connect_readonly, database_health
from quest_viewer.repository import QuestRepository
from quest_viewer.story_connections import (
    CONFIRMED_COMPLETION_BRIDGES,
    VERSION_UPDATE_BRIDGES,
)
from quest_viewer.tags import tokenize_text


@pytest.fixture(scope="module")
def repository() -> QuestRepository:
    settings = load_settings()
    return QuestRepository(settings.database_path)


def test_database_is_healthy_and_read_only() -> None:
    settings = load_settings()
    health = database_health(settings.database_path)
    assert health["status"] == "ok"
    assert health["mode"] == "read-only"
    assert health["quest_count"] == 8828

    connection = connect_readonly(settings.database_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden_write(value TEXT)")
    finally:
        connection.close()


def test_search_uses_quest_name_not_quest_id(repository: QuestRepository) -> None:
    result = repository.search(q="大战黄风洞")
    assert result["total"] == 1
    assert result["items"][0]["quest_id"] == 90
    assert result["items"][0]["quest_name"] == "大战黄风洞"
    numeric_text = repository.search(q="90")
    assert all(item["quest_id"] != 90 for item in numeric_text["items"])


def test_search_orders_by_level_then_quest_id(
    repository: QuestRepository,
) -> None:
    result = repository.search(area="京城", page=1)
    order_keys = [
        (
            item["level_requirement"] is None,
            item["level_requirement"] or 0,
            item["quest_id"],
        )
        for item in result["items"]
    ]
    assert order_keys == sorted(order_keys)


def test_search_by_npc_and_area(repository: QuestRepository) -> None:
    by_npc = repository.search(q="大战黄风洞", npc="刘老太太")
    by_area = repository.search(q="大战黄风洞", area="宁海县")
    assert any(item["quest_id"] == 90 for item in by_npc["items"])
    assert any(item["quest_id"] == 90 for item in by_area["items"])


def test_facets_use_requested_business_order(repository: QuestRepository) -> None:
    facets = repository.facets()
    category_counts = [item["task_count"] for item in facets["categories"]]
    category_by_name = {
        item["name"]: item["task_count"] for item in facets["categories"]
    }
    repeat_children = [
        item
        for item in facets["subcategories"]
        if item["parent_name"] == "重复任务"
    ]
    unclassified_by_parent = {
        item["parent_name"]: item["task_count"]
        for item in facets["subcategories"]
        if item["name"] == "未分类"
    }
    area_levels = [
        item["min_level"] for item in facets["areas"] if item["min_level"] is not None
    ]
    assert category_counts == sorted(category_counts, reverse=True)
    assert category_by_name["正传任务"] == 1831
    assert category_by_name["支线任务"] == 1815
    assert category_by_name["重复任务"] == 334
    assert category_by_name["系列任务"] == 603
    assert category_by_name["副本任务"] == 487
    assert category_by_name["声望任务"] == 222
    assert category_by_name["阵营任务"] == 159
    assert category_by_name["活动任务"] == 618
    assert len(repeat_children) == 27
    assert sum(item["task_count"] for item in repeat_children) == 334
    assert repeat_children[0] == {
        "parent_name": "重复任务",
        "name": "六百里号山",
        "task_count": 57,
    }
    assert unclassified_by_parent["副本任务"] == 439
    assert unclassified_by_parent["活动任务"] == 372
    assert "正传任务" not in unclassified_by_parent
    assert "重复任务" not in unclassified_by_parent
    assert facets["areas"][0]["name"] == "小桑村"
    area_names = {item["name"] for item in facets["areas"]}
    assert "桃花林" not in area_names
    assert "副本场景" in area_names
    assert "青牛坡" not in area_names
    assert "聚魂关" not in area_names
    assert "车迟国·东境" not in area_names
    assert "东海龙宫" not in area_names
    assert "京城南郊" not in area_names
    assert "九霄四时台" not in area_names
    assert "乌鸡国·上崖郡" not in area_names
    assert area_levels == sorted(area_levels)


def test_main_and_subcategory_filters_use_taxonomy(
    repository: QuestRepository,
) -> None:
    all_repeat = repository.search(category="重复任务")
    regional_repeat = repository.search(
        category="重复任务",
        subcategory="六百里号山",
    )
    series = repository.search(category="系列任务", subcategory="天劫路")
    assert all_repeat["total"] == 334
    assert regional_repeat["total"] == 57
    assert all(
        item["main_category_name"] == "重复任务"
        and item["sub_category_name"] == "六百里号山"
        for item in regional_repeat["items"]
    )
    assert series["total"] == 256


def test_single_child_main_categories_do_not_get_unclassified_subcategory(
    repository: QuestRepository,
) -> None:
    facets = repository.facets()
    standalone_parents = {
        "VIP任务",
        "仙缘任务",
        "任务关闭",
        "奇遇任务",
        "师徒任务",
        "情缘任务",
        "教学任务",
        "正传任务",
        "百货任务",
        "职业任务",
        "跑环任务",
        "镇妖塔任务",
        "风物志任务",
    }
    assert not any(
        item["parent_name"] in standalone_parents
        for item in facets["subcategories"]
    )
    assert {
        item["parent_name"]
        for item in facets["subcategories"]
        if item["name"] == "未分类"
    } == {"副本任务", "活动任务"}


@pytest.mark.parametrize(
    ("main_category", "subcategory", "expected_count"),
    [
        ("副本任务", "玉灵山", 17),
        ("副本任务", "五行通天阵", 8),
        ("声望任务", "官府当差任务", 64),
        ("声望任务", "水下-龙太子党", 33),
        ("阵营任务", "门派任务", 113),
        ("阵营任务", "跨阵营任务", 17),
        ("活动任务", "联动任务", 133),
        ("活动任务", "周年庆", 27),
        ("活动任务", "休闲任务", 5),
        ("重复任务", "奇缘任务", 5),
        ("副本任务", "未分类", 439),
        ("活动任务", "未分类", 372),
    ],
)
def test_configured_category_groups(
    repository: QuestRepository,
    main_category: str,
    subcategory: str,
    expected_count: int,
) -> None:
    result = repository.search(
        category=main_category,
        subcategory=subcategory,
    )
    assert result["total"] == expected_count


def test_parent_area_filter_includes_subareas(repository: QuestRepository) -> None:
    result = repository.search(q="报恩德灵狐有托付", area="小桑村")
    assert result["total"] == 1
    assert result["items"][0]["area_name"] == "小桑村·桃花林"
    assert repository.search(q="报恩德灵狐有托付", area="桃花林")["total"] == 0


def test_configured_area_filter_group_keeps_original_detail_area(
    repository: QuestRepository,
) -> None:
    result = repository.search(q="刻印显芒幻境开", area="宁海县")
    assert result["total"] == 1
    assert result["items"][0]["quest_id"] == 7372
    assert result["items"][0]["area_name"] == "青牛坡"

    detail = repository.get(7372)
    assert detail is not None
    assert detail["summary"]["area_name"] == "青牛坡"


def test_detail_displays_parent_and_subarea(repository: QuestRepository) -> None:
    detail = repository.get(37)
    assert detail is not None
    assert detail["summary"]["root_area_name"] == "小桑村"
    assert detail["summary"]["subarea_name"] == "桃花林"
    assert detail["summary"]["area_name"] == "小桑村·桃花林"


def test_manual_area_correction_for_quest_1459(
    repository: QuestRepository,
) -> None:
    detail = repository.get(1459)
    assert detail is not None
    assert detail["summary"]["root_area_name"] == "云梦山"
    assert detail["summary"]["area_name"] == "云梦山"
    assert any(
        reward["object_type_name"] == "阵营"
        and reward["object_id"] == 15
        and reward["object_name"] == "鬼谷仙派"
        for reward in detail["rewards"]
    )
    assert any(
        reward["object_type_name"] == "经验值"
        and reward["amount"] == 666750
        for reward in detail["rewards"]
    )


def test_all_camp_rewards_resolve_to_names() -> None:
    settings = load_settings()
    connection = connect_readonly(settings.database_path)
    try:
        unresolved = connection.execute(
            """
            SELECT COUNT(*)
            FROM quest_reward reward
            LEFT JOIN quest_camp camp ON camp.camp_id=reward.object_id
            WHERE reward.object_type_id=15
              AND camp.camp_id IS NULL
            """
        ).fetchone()[0]
    finally:
        connection.close()
    assert unresolved == 0


def test_quest_90_has_expected_context(repository: QuestRepository) -> None:
    detail = repository.get(90)
    assert detail is not None
    assert detail["summary"]["accept_object_name"] == "刘老太太"
    assert detail["summary"]["submit_object_name"] == "刘老太太"
    assert detail["summary"]["area_name"] == "宁海县·宁海县城"
    assert detail["objectives"][0]["object_id"] == 207
    assert detail["objectives"][0]["object_name"] == "黄风打手"
    assert detail["objectives"][0]["amount"] == 6
    assert detail["texts"][0]["quest_description"] == ""
    assert "黄风洞中消灭<enemy:黄风打手>" in detail["texts"][0]["hint_text"]


def test_quest_90_tags_resolve_in_separate_namespaces(
    repository: QuestRepository,
) -> None:
    enemy = repository.resolve_tag(
        quest_id=90, version_no=1, tag_kind="enemy", value="黄风打手"
    )
    target = repository.resolve_tag(
        quest_id=90, version_no=1, tag_kind="target", value="91"
    )
    assert enemy["status"] == "resolved"
    assert enemy["object_id"] == 207
    assert enemy["amount"] == 6
    assert target["status"] == "resolved"
    assert target["target_id"] == 91
    assert target["label"] == "刘老太太"
    assert target["area_name"] == "宁海县·宁海县城"
    assert target["resource_key"] == "nhx_nhxch_liulaotaitai"
    assert [item["quest_id"] for item in target["related_quests"]] == [
        112,
        1520,
        1521,
        1522,
    ]
    assert all(item["quest_id"] != 90 for item in target["related_quests"])


def test_npc_role_finds_other_tasks_without_duplicate_versions(
    repository: QuestRepository,
) -> None:
    role = repository.resolve_npc_role(quest_id=90, npc_id=33)
    assert role is not None
    assert role["label"] == "刘老太太"
    assert [item["quest_id"] for item in role["related_quests"]] == [
        50,
        1520,
        1521,
        1522,
    ]


def test_related_quests_are_not_truncated_before_ui_pagination(
    repository: QuestRepository,
) -> None:
    role = repository.resolve_npc_role(quest_id=886, npc_id=7003)
    assert role is not None
    assert len(role["related_quests"]) == 134
    assert all(item["quest_id"] != 886 for item in role["related_quests"])


def test_tag_tokenizer_preserves_unknown_tags(repository: QuestRepository) -> None:
    tokens = tokenize_text(
        "前往<target:999999>，保持原文。",
        repository=repository,
        quest_id=90,
        version_no=1,
    )
    tag = next(token for token in tokens if token["type"] == "tag")
    assert tag["value"] == "<target:999999>"
    assert tag["resolution"]["status"] == "unresolved"


def test_text_control_and_plain_markup_rules(repository: QuestRepository) -> None:
    tokens = tokenize_text(
        (
            "<c:FFFF0000>混元锤<c>交给<name>。"
            "<brief:密林县令><aim:护送张头>"
        ),
        repository=repository,
        quest_id=800,
        version_no=1,
    )
    assert all(token["type"] == "text" for token in tokens)
    assert "".join(token["value"] for token in tokens) == (
        "混元锤交给玩家。密林县令护送张头"
    )


def test_unmatched_enemy_keeps_text_without_entity(
    repository: QuestRepository,
) -> None:
    tokens = tokenize_text(
        "提防<enemy:并不存在的妖怪>。",
        repository=repository,
        quest_id=90,
        version_no=1,
    )
    assert all(token["type"] == "text" for token in tokens)
    assert "".join(token["value"] for token in tokens) == "提防并不存在的妖怪。"


@pytest.mark.parametrize(
    "markup",
    [
        "<targte:91>",
        "<targer:91>",
        "<taget:91>",
        "<taret:91>",
        "<traget:91>",
        "<target：91>",
        "<target:91刘老太太>",
    ],
)
def test_target_typo_and_payload_normalization(
    repository: QuestRepository,
    markup: str,
) -> None:
    tokens = tokenize_text(
        markup,
        repository=repository,
        quest_id=90,
        version_no=1,
    )
    tag = next(token for token in tokens if token["type"] == "tag")
    assert tag["resolution"]["kind"] == "target"
    assert tag["resolution"]["target_id"] == 91
    assert tag["resolution"]["label"] == "刘老太太"


def test_friend_is_clickable_only_for_a_unique_role(
    repository: QuestRepository,
) -> None:
    unique = tokenize_text(
        "拜访<friend:游方仙人>。",
        repository=repository,
        quest_id=207,
        version_no=1,
    )
    unique_tag = next(token for token in unique if token["type"] == "tag")
    assert unique_tag["resolution"]["kind"] == "friend"
    assert unique_tag["resolution"]["label"] == "游方仙人"
    assert unique_tag["resolution"]["object_id"] == 302
    assert "related_quests" in unique_tag["resolution"]

    ambiguous = tokenize_text(
        "拜访<friend:小淘气>。",
        repository=repository,
        quest_id=50,
        version_no=1,
    )
    assert all(token["type"] == "text" for token in ambiguous)
    assert "".join(token["value"] for token in ambiguous) == "拜访小淘气。"


def test_inline_item_control_uses_global_item_name(
    repository: QuestRepository,
) -> None:
    tokens = tokenize_text(
        "任务奖励\\n您将得到\\n<ic:47791>",
        repository=repository,
        quest_id=19510,
        version_no=1,
    )
    assert all(token["type"] == "text" for token in tokens)
    assert "".join(token["value"] for token in tokens).endswith("VIP凭证")


def test_character_call_tag_resolves_to_dynamic_variants(
    repository: QuestRepository,
) -> None:
    resolution = repository.resolve_tag(
        quest_id=2911,
        version_no=1,
        tag_kind="character",
        value="18",
    )
    assert resolution["status"] == "resolved"
    assert resolution["namespace"] == "动态玩家称谓"
    assert resolution["speaker_profile_name"] == "男中-市井老成"
    assert resolution["variant_count"] == 14
    assert resolution["call_variants"].startswith("小家伙、老弟、老弟、老兄")
    assert resolution["default_call"] == "小家伙"
    assert resolution["label"] == "小家伙"
    assert "related_quests" not in resolution

    tokens = tokenize_text(
        "不知<character:18>可否应允？",
        repository=repository,
        quest_id=2911,
        version_no=1,
    )
    tag = next(token for token in tokens if token["type"] == "tag")
    assert tag["value"] == "<character:18>"
    assert tag["resolution"]["call_profile_id"] == 18


def test_navigation_item_hint_and_color_controls_are_hidden(
    repository: QuestRepository,
) -> None:
    detail = repository.get(1520)
    assert detail is not None
    tokens = tokenize_text(
        detail["texts"][0]["hint_text"],
        repository=repository,
        quest_id=1520,
        version_no=1,
    )
    rendered_text = "".join(
        token["value"] for token in tokens if token["type"] == "text"
    )
    assert "点击带有下划线的文字" not in rendered_text
    assert all(
        token.get("resolution", {}).get("kind") != "item"
        for token in tokens
    )
    assert all("color" not in token for token in tokens)
    assert "完成【仙缘】系列任务" in rendered_text


def test_item_markup_is_classified_by_structured_objective(
    repository: QuestRepository,
) -> None:
    actual_item = repository.resolve_tag(
        quest_id=897,
        version_no=1,
        tag_kind="item",
        value="苍灵九宫石",
    )
    prompt_text = repository.resolve_tag(
        quest_id=9019,
        version_no=1,
        tag_kind="item",
        value="（提示：副本任务无寻路。）",
    )
    assert actual_item["kind"] == "item"
    assert actual_item["namespace"] == "任务道具"
    assert prompt_text["kind"] == "hint"
    assert prompt_text["namespace"] == "提示文本"


def test_area_markup_keeps_text_without_creating_an_entity(
    repository: QuestRepository,
) -> None:
    tokens = tokenize_text(
        "请<area:进入黄风洞中>，完成任务。",
        repository=repository,
        quest_id=182,
        version_no=1,
    )
    assert "".join(token["value"] for token in tokens) == "请进入黄风洞中，完成任务。"
    assert all(token["type"] == "text" for token in tokens)


def test_prompt_markup_keeps_text_without_creating_an_entity(
    repository: QuestRepository,
) -> None:
    prompt = "（提示：消灭妖精后，使用三清派蓝葫芦吸收。）"
    tokens = tokenize_text(
        f"吸纳妖气<enemy:{prompt}>，然后复命。",
        repository=repository,
        quest_id=182,
        version_no=1,
    )
    assert "".join(token["value"] for token in tokens) == f"吸纳妖气{prompt}，然后复命。"
    assert all(token["type"] == "text" for token in tokens)


def test_11257_is_losslessly_merged_for_display(
    repository: QuestRepository,
) -> None:
    detail = repository.get(11257)
    assert detail is not None
    assert detail["summary"]["quest_name"] == "孟浪多疑10"
    assert detail["aliases"] == ["孟浪多疑11"]
    assert detail["safe_display_merge"] is True
    assert detail["conflict_columns"] == []
    assert [item["source_row"] for item in detail["variants"]] == [6211, 6212]


def test_confirmed_story_connections_match_completion_conditions() -> None:
    settings = load_settings()
    connection = connect_readonly(settings.database_path)
    try:
        rows = connection.execute(
            """
            WITH main AS (
                SELECT *
                FROM quest_full
                WHERE category_id = 1000
            )
            SELECT old.quest_id,
                   old.quest_name,
                   new.quest_id,
                   new.quest_name
            FROM quest_condition AS condition
            JOIN main AS old ON old.quest_id = condition.object_id
            JOIN main AS new ON new.quest_id = condition.quest_id
            WHERE condition.condition_kind = 'precondition'
              AND condition.object_type_id = 5
              AND condition.comparison_code = 1
              AND condition.comparison_value = 1
              AND COALESCE(old.next_quest_id, 0) = 0
            GROUP BY old.quest_id, new.quest_id
            """
        ).fetchall()
    finally:
        connection.close()

    database_bridges = {tuple(row) for row in rows}
    configured_bridges = set(CONFIRMED_COMPLETION_BRIDGES)
    assert len(configured_bridges) == 69
    assert configured_bridges == database_bridges


def test_story_context_includes_confirmed_and_version_update_bridges(
    repository: QuestRepository,
) -> None:
    confirmed = repository.get(1643)
    confirmed_target = repository.get(1645)
    version_update = repository.get(1648)
    version_target = repository.get(123)
    assert confirmed is not None
    assert confirmed_target is not None
    assert version_update is not None
    assert version_target is not None

    confirmed_relation = next(
        relation
        for relation in confirmed["relations"]["outgoing"]
        if relation["to_quest_id"] == 1645
        and relation["relation_type"] == "completion_requirement"
    )
    assert confirmed_relation["inferred"] is False
    assert confirmed_relation["confidence"] == "confirmed"
    assert any(
        relation["from_quest_id"] == 1643
        and relation["relation_type"] == "completion_requirement"
        for relation in confirmed_target["relations"]["incoming"]
    )

    version_relation = next(
        relation
        for relation in version_update["relations"]["outgoing"]
        if relation["to_quest_id"] == 123
        and relation["relation_type"] == "version_update"
    )
    assert version_relation["inferred"] is True
    assert version_relation["confidence"] == "high"
    assert any(
        relation["from_quest_id"] == 1648
        and relation["relation_type"] == "version_update"
        for relation in version_target["relations"]["incoming"]
    )
    assert len(VERSION_UPDATE_BRIDGES) == 20


def test_story_context_keeps_all_parallel_branches(
    repository: QuestRepository,
) -> None:
    confirmed = repository.get(3869)
    version_update = repository.get(3311)
    assert confirmed is not None
    assert version_update is not None

    confirmed_targets = {
        relation["to_quest_id"]
        for relation in confirmed["relations"]["outgoing"]
        if relation["relation_type"] == "completion_requirement"
    }
    version_targets = {
        relation["to_quest_id"]
        for relation in version_update["relations"]["outgoing"]
        if relation["relation_type"] == "version_update"
    }
    assert confirmed_targets == {559, 3870, 3872, 3874, 3876}
    assert version_targets == {3313, 3332}
