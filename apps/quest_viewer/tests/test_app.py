from __future__ import annotations

import re
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from quest_viewer.app import app, visitor_counter


visitor_test_directory = tempfile.TemporaryDirectory()
visitor_counter.database_path = (
    Path(visitor_test_directory.name) / "visitor_stats.db"
)
site_version = (
    Path(__file__).resolve().parents[1] / "VERSION"
).read_text(encoding="utf-8").strip()
client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "read-only"


def test_visit_api_deduplicates_anonymous_browser_id() -> None:
    visitor_id = "test_browser_1234567890"
    first = client.post("/api/visit", json={"visitor_id": visitor_id})
    repeat = client.post("/api/visit", json={"visitor_id": visitor_id})
    assert first.status_code == 200
    assert repeat.status_code == 200
    assert first.json()["is_new"] is True
    assert repeat.json()["is_new"] is False
    assert repeat.json()["count"] == first.json()["count"]


def test_default_page_renders_real_quest_90() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "寻仙任务存档" in response.text
    assert (
        f'<small class="brand-version">v{site_version}</small>'
        in response.text
    )
    assert "本地只读任务档案" not in response.text
    assert "例如：刘老太太" not in response.text
    assert "寻仙任务数据库" not in response.text
    assert "在线运行" not in response.text
    assert 'data-open-about>关于网站</button>' in response.text
    assert re.search(
        r'今日来访\s*<strong id="today-visitors">\d+</strong>',
        response.text,
    )
    assert (
        'href="https://github.com/icosohedral/xunxian-quests-archive"'
        in response.text
    )
    assert "作者与维护者" in response.text
    assert "<h3>icosohedral</h3>" in response.text
    assert "<span>GitHub</span>" in response.text
    assert re.search(
        r'<a class="about-credits__github"[^>]*>\s*'
        r"<span>GitHub</span>\s*icosohedral\s*"
        r'<span aria-hidden="true">↗</span>',
        response.text,
    )
    assert ">icosohedral/xunxian-quests-archive" not in response.text
    assert "寻仙任务资料库的整理、维护与网站开发。" in response.text
    assert "特别鸣谢" in response.text
    assert "贴吧用户「耳目清净」" in response.text
    assert "感谢其开发的寻仙游戏资源解包工具，为本资料库的资源整理提供了重要支持。" in response.text
    assert "SQLite 只读" not in response.text
    assert "项检索结果" not in response.text
    assert "只读记录" not in response.text
    assert "查看原始标签文本" not in response.text
    assert "mb/quest/quest_text.txt" not in response.text
    assert "大战黄风洞" in response.text
    assert "小桑村 · 1级起" not in response.text
    assert '<option value="小桑村"' in response.text
    assert '<option value="支线任务"' in response.text
    assert "支线任务（1815）" in response.text
    assert "活动任务（618）" in response.text
    assert "副本任务（487）" in response.text
    assert "声望任务（222）" in response.text
    assert "阵营任务（159）" in response.text
    assert 'data-parent="重复任务"' in response.text
    assert 'data-parent="声望任务"' in response.text
    assert 'value="未分类"' in response.text
    assert "六百里号山（57）" in response.text
    assert "黄风打手" in response.text
    assert "刘老太太" in response.text
    assert "quest-card-footer" not in response.text
    assert ">有文本<" not in response.text
    assert 'class="role-trigger"' in response.text
    assert '<h3>相关任务</h3>' in response.text
    assert "<h3>对象详情</h3>" in response.text
    assert 'id="evidence-status"' not in response.text
    assert "<h3>解析证据</h3>" not in response.text
    assert "<h3>原始来源</h3>" not in response.text
    assert "<h2>任务语境</h2>" in response.text
    assert "<h2>关系与依据</h2>" not in response.text
    assert "只展开 1 层" not in response.text
    assert "全部直接关系" not in response.text
    assert response.text.index("<h3>相关任务</h3>") < response.text.index(
        "<h3>对象详情</h3>"
    )
    assert "QUEST DOSSIER · ID" not in response.text
    assert "任务 ID 或名称" not in response.text
    assert response.text.count('class="quest-card ') == 5
    assert "1 / 1766" in response.text


def test_quest_90_page_contains_five_text_tabs_and_tags() -> None:
    response = client.get("/?selected=90")
    assert response.status_code == 200
    for label in ["接取对话", "任务背景", "提示文字", "进行中", "完成对话"]:
        assert label in response.text
    assert "entity-tag--enemy" in response.text
    assert "entity-tag--target" in response.text
    assert "原始数据为空" in response.text
    assert 'class="condition-quest-link"' in response.text
    assert 'href="/?selected=178&page=1"' in response.text
    assert "比较代码" not in response.text
    assert "NPC ID 207" not in response.text
    assert "阵营声望" in response.text
    assert ">+100</b>" in response.text
    assert "general · 槽位1" not in response.text


def test_unclassified_subcategory_is_hidden_in_quest_detail() -> None:
    response = client.get("/?selected=37")
    assert response.status_code == 200
    assert "<dt>任务类型</dt><dd>副本任务</dd>" in response.text
    assert "副本任务 · 未分类" not in response.text


def test_11257_page_exposes_merged_alias_without_source_panel() -> None:
    response = client.get("/?selected=11257")
    assert response.status_code == 200
    assert "孟浪多疑10" in response.text
    assert "孟浪多疑11" in response.text
    assert "重复记录无损合并 ×2" in response.text
    assert "<h3>原始来源</h3>" not in response.text
    assert 'id="related-quests"' in response.text


def test_1459_page_resolves_camp_and_displays_experience() -> None:
    response = client.get("/?selected=1459")
    assert response.status_code == 200
    assert "鬼谷仙派" in response.text
    assert "ID 15" not in response.text
    assert "经验值" in response.text
    assert ">+67万</b>" in response.text


def test_large_reward_amount_uses_yi_unit() -> None:
    response = client.get("/?selected=625")
    assert response.status_code == 200
    assert "经验值" in response.text
    assert ">+6000亿</b>" in response.text


def test_title_reward_resolves_from_title_resource() -> None:
    response = client.get("/?selected=12078")
    assert response.status_code == 200
    assert "十方名士" in response.text
    assert "称号 十方上师" in response.text
    assert '<span>称号</span>' in response.text
    assert '<span>称号ID</span>' not in response.text
    assert "ID 505" not in response.text
    assert "称号ID 506" not in response.text


def test_state_conditions_and_rewards_resolve_from_state_resource() -> None:
    response = client.get("/?selected=15714")
    assert response.status_code == 200
    assert "状态 聚仙庵情景任务所需2" in response.text
    assert '<span>状态</span>' in response.text
    assert "<strong>聚仙庵情景任务所需3</strong>" in response.text
    assert "ID 21055" not in response.text
    assert "ID 21056" not in response.text


def test_role_payload_contains_clickable_related_tasks() -> None:
    response = client.get("/?selected=90")
    assert response.status_code == 200
    assert "related_quests" in response.text
    assert '"quest_id": 50' in response.text
    assert '"quest_id": 1521' in response.text


def test_context_task_links_preserve_search_results() -> None:
    response = client.get(
        "/?selected=90&area=%E5%AE%81%E6%B5%B7%E5%8E%BF&page=2"
    )
    assert response.status_code == 200
    preserved = "area=%E5%AE%81%E6%B5%B7%E5%8E%BF&amp;page=2"
    assert f'href="/?selected=178&{preserved}"' in response.text
    assert f'data-preserved-query="{preserved}"' in response.text


def test_character_call_is_rendered_as_dynamic_player_address() -> None:
    response = client.get("/?selected=2911")
    assert response.status_code == 200
    assert "entity-tag--character" in response.text
    assert ">小家伙</button>" in response.text
    assert "查看原始标签文本" not in response.text
    assert ">狮子<" not in response.text


def test_color_control_markup_renders_as_plain_text() -> None:
    response = client.get("/?selected=1520")
    assert response.status_code == 200
    assert 'class="game-colored-text"' not in response.text
    assert "完成【仙缘】系列任务可开启任务背包栏上限" in response.text


def test_item_markup_distinguishes_hints_from_actual_items() -> None:
    hint_response = client.get("/?selected=9019")
    item_response = client.get("/?selected=897")
    assert 'class="entity-tag entity-tag--hint' not in hint_response.text
    assert "（提示：副本任务无寻路。）" in hint_response.text
    assert 'class="entity-tag entity-tag--item' in item_response.text
    assert "<span>道具</span>苍灵九宫石" in item_response.text


def test_area_markup_renders_as_plain_text() -> None:
    response = client.get("/?selected=182")
    assert response.status_code == 200
    assert "进入黄风洞中" in response.text
    assert "提示：消灭妖精后，先用左键点住妖精尸体" in response.text
    assert "&lt;area:" not in response.text
    assert "entity-tag--area" not in response.text
    assert "<span>敌人</span>（提示：" not in response.text


def test_api_returns_404_for_unknown_quest() -> None:
    response = client.get("/api/quests/99999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


def test_query_is_html_escaped() -> None:
    response = client.get("/", params={"q": "<script>alert(1)</script>"})
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_two_level_category_filter_preserves_child_on_pagination() -> None:
    response = client.get(
        "/",
        params={"category": "重复任务", "subcategory": "六百里号山"},
    )
    assert response.status_code == 200
    assert "57 条 · 第 1/12 页" in response.text
    assert '<option value="重复任务" selected' in response.text
    assert 'value="六百里号山"' in response.text
    assert "subcategory=%E5%85%AD%E7%99%BE%E9%87%8C%E5%8F%B7%E5%B1%B1" in response.text


def test_clipped_content_gets_hover_titles() -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "scrollWidth > element.clientWidth" in response.text
    assert "element.title = element.textContent.trim()" in response.text
    assert '".reward-card > strong"' in response.text
    assert response.text.index('label: "对象名称"') < response.text.index(
        'namespace: "对象类型"'
    )
    assert 'object_id: "对象 ID"' not in response.text
    assert 'call_profile_id: "称谓模板 ID"' not in response.text
    assert 'variant_count: "候选数量"' not in response.text
    assert "const relatedPageSize = 5" in response.text
    assert 'data-related-page="prev"' in response.text
    assert "updateSubcategoryOptions" in response.text
    assert "aboutDialog?.showModal()" in response.text
    assert "aboutDialog?.close()" in response.text


def test_search_pagination_uses_partial_api_refresh() -> None:
    page = client.get("/?selected=90&area=宁海县&page=2")
    assert page.status_code == 200
    assert 'id="search-result-list"' in page.text
    assert 'id="search-result-summary"' in page.text
    assert 'id="search-pagination"' in page.text

    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "fetchSearchPage" in script.text
    assert 'fetch(url, {' in script.text
    assert 'history.pushState({}, "", questLink(selected || "", params))' in script.text
    assert 'searchPagination?.addEventListener("click"' in script.text
    assert "prefetchAdjacentSearchPages" in script.text
