from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _short(value: str | None, limit: int = 500) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else value[:limit] + "…"


def _object_label(
    object_type: int | None,
    object_id: int | None,
    names: dict[int, dict[int, str]],
    type_names: dict[int, str],
) -> str:
    if object_type is None or object_id is None:
        return "—"
    name = names.get(object_type, {}).get(object_id)
    type_name = type_names.get(object_type, f"类型{object_type}")
    return f"{type_name} · {object_id}" + (f" · {name}" if name else "")


def _collect_sample(
    connection: sqlite3.Connection,
    quest_id: int,
    names: dict[int, dict[int, str]],
    type_names: dict[int, str],
) -> list[dict[str, Any]]:
    versions = connection.execute(
        """
        SELECT q.*, c.category_name
        FROM quest q
        LEFT JOIN quest_category c ON c.category_id=q.category_id
        WHERE q.quest_id=?
        ORDER BY q.version_no
        """,
        (quest_id,),
    ).fetchall()
    samples = []
    for quest in versions:
        text_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT source_row, accept_dialogue, quest_description, hint_text,
                       progress_dialogue, completion_dialogue, source_file
                FROM quest_text
                WHERE source_quest_id=?
                ORDER BY source_row
                """,
                (quest_id,),
            )
        ]
        endpoints = []
        for row in connection.execute(
            """
            SELECT endpoint_kind, object_type_id, object_id, resolved,
                   source_column_type, source_column_id
            FROM quest_endpoint
            WHERE quest_id=? AND version_no=?
            ORDER BY endpoint_kind
            """,
            (quest_id, quest["version_no"]),
        ):
            endpoints.append(
                {
                    **dict(row),
                    "display": _object_label(
                        row["object_type_id"], row["object_id"], names, type_names
                    ),
                }
            )
        rewards = []
        for row in connection.execute(
            """
            SELECT reward_group, slot_no, object_type_id, object_id, amount,
                   item_resolved
            FROM quest_reward
            WHERE quest_id=? AND version_no=?
            ORDER BY reward_group, slot_no
            """,
            (quest_id, quest["version_no"]),
        ):
            rewards.append(
                {
                    **dict(row),
                    "display": _object_label(
                        row["object_type_id"], row["object_id"], names, type_names
                    ),
                }
            )
        target = None
        if quest["tracking_target_id"]:
            row = connection.execute(
                """
                SELECT target_id, target_name, area_name, resource_key,
                       source_file, source_row
                FROM quest_target WHERE target_id=?
                """,
                (quest["tracking_target_id"],),
            ).fetchone()
            target = dict(row) if row else None
        samples.append(
            {
                "quest": dict(quest),
                "texts": text_rows,
                "endpoints": endpoints,
                "target": target,
                "rewards": rewards,
            }
        )
    return samples


def generate_g02_sample_pack(
    *,
    db_path: Path,
    html_path: Path,
    json_path: Path,
    run_id: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        type_names = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT object_type_id, object_type_name FROM object_type"
            )
        }
        names: dict[int, dict[int, str]] = {
            2: {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT item_id, item_name FROM item"
                )
            },
            3: {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT quest_npc_id, quest_npc_name FROM quest_npc"
                )
            },
            5: {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT quest_id, quest_name FROM quest WHERE version_no=1"
                )
            },
            6: {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT attribute_id, attribute_name FROM quest_attribute"
                )
            },
            13: {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT quest_event_id, quest_event_name FROM quest_event"
                )
            },
            15: {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT camp_id, camp_name FROM quest_camp"
                )
            },
        }
        sample_ids = [1, 2, 1694, 7304, 11257]
        samples = {
            str(quest_id): _collect_sample(
                connection, quest_id, names, type_names
            )
            for quest_id in sample_ids
        }
        metrics = {
            "quest_rows": connection.execute(
                "SELECT COUNT(*) FROM quest"
            ).fetchone()[0],
            "unique_quest_ids": connection.execute(
                "SELECT COUNT(*) FROM quest_identity"
            ).fetchone()[0],
            "text_rows": connection.execute(
                "SELECT COUNT(*) FROM quest_text"
            ).fetchone()[0],
            "category_rows": connection.execute(
                "SELECT COUNT(*) FROM quest_category WHERE category_name IS NOT NULL"
            ).fetchone()[0],
            "npc_rows": connection.execute(
                "SELECT COUNT(*) FROM quest_npc"
            ).fetchone()[0],
            "target_rows": connection.execute(
                "SELECT COUNT(*) FROM quest_target"
            ).fetchone()[0],
            "item_rows": connection.execute(
                "SELECT COUNT(*) FROM item"
            ).fetchone()[0],
            "reward_rows": connection.execute(
                "SELECT COUNT(*) FROM quest_reward"
            ).fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }
    finally:
        connection.close()

    payload = {
        "run_id": run_id,
        "generated_at": _utc_now(),
        "database": str(db_path),
        "metrics": metrics,
        "samples": samples,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    cards: list[str] = []
    for quest_id in [1, 2, 1694, 7304, 11257]:
        for sample in samples[str(quest_id)]:
            quest = sample["quest"]
            text_blocks = []
            if sample["texts"]:
                for text in sample["texts"]:
                    fields = [
                        ("接取文本", text["accept_dialogue"]),
                        ("任务说明", text["quest_description"]),
                        ("提示", text["hint_text"]),
                        ("进行中", text["progress_dialogue"]),
                        ("完成文本", text["completion_dialogue"]),
                    ]
                    visible = "".join(
                        f"<dt>{html.escape(label)}</dt><dd>{html.escape(_short(value))}</dd>"
                        for label, value in fields
                        if value
                    )
                    text_blocks.append(
                        f"<div class='text-block'><div class='source'>文本来源："
                        f"{html.escape(text['source_file'])}:{text['source_row']}</div>"
                        f"<dl>{visible or '<dd>该行常用文本列为空，原始行仍已保存。</dd>'}</dl></div>"
                    )
            else:
                text_blocks.append("<div class='notice'>该任务没有匹配的 quest_text 记录。</div>")

            endpoint_rows = "".join(
                f"<tr><td>{'接取' if ep['endpoint_kind']=='accept' else '提交'}</td>"
                f"<td>{html.escape(ep['display'])}</td><td>{'是' if ep['resolved'] else '否'}</td>"
                f"<td>第{ep['source_column_type']}/{ep['source_column_id']}列</td></tr>"
                for ep in sample["endpoints"]
            ) or "<tr><td colspan='4'>无可解析的接交对象</td></tr>"

            reward_rows = "".join(
                f"<tr><td>{'固定' if reward['reward_group']=='fixed' else '通用'}</td>"
                f"<td>{reward['slot_no']}</td><td>{html.escape(reward['display'])}</td>"
                f"<td>{html.escape(_clean(reward['amount']))}</td>"
                f"<td>{'是' if reward['object_type_id'] != 2 or reward['item_resolved'] else '否'}</td></tr>"
                for reward in sample["rewards"]
            ) or "<tr><td colspan='5'>无普通奖励槽位</td></tr>"

            target = sample["target"]
            target_text = (
                f"{target['target_id']} · {html.escape(target['target_name'])}"
                f" · {html.escape(_clean(target['area_name']))}"
                if target
                else "—"
            )
            conflict_badge = (
                "<span class='badge warn'>冲突版本</span>"
                if quest["conflict_flag"]
                else "<span class='badge ok'>普通记录</span>"
            )
            cards.append(
                f"""
                <article class="card">
                  <header>
                    <div><span class="qid">任务 {quest['quest_id']} · v{quest['version_no']}</span>
                    {conflict_badge}</div>
                    <h2>{html.escape(quest['quest_name'])}</h2>
                    <p>{html.escape(_clean(quest['category_name']))}</p>
                  </header>
                  <div class="facts">
                    <div><strong>等级限制</strong><span>{html.escape(_clean(quest['level_requirement']))}</span></div>
                    <div><strong>最高等级</strong><span>{html.escape(_clean(quest['max_level']))}</span></div>
                    <div><strong>寻路目标</strong><span>{target_text}</span></div>
                    <div><strong>原始来源</strong><span>{html.escape(quest['source_file'])}:{quest['source_row']}</span></div>
                  </div>
                  <h3>接取与提交对象</h3>
                  <table><thead><tr><th>阶段</th><th>对象</th><th>已解析</th><th>来源列</th></tr></thead>
                  <tbody>{endpoint_rows}</tbody></table>
                  <h3>任务文本</h3>
                  {''.join(text_blocks)}
                  <h3>普通奖励</h3>
                  <table><thead><tr><th>分组</th><th>槽位</th><th>对象</th><th>数量</th><th>已解析</th></tr></thead>
                  <tbody>{reward_rows}</tbody></table>
                  <details><summary>原始 quest_info 行预览</summary>
                    <pre>{html.escape(_short(quest['raw_value'], 1200))}</pre>
                  </details>
                </article>
                """
            )

    html_document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>G02 · 任务数据库 MVP 抽查包</title>
  <style>
    :root {{ --navy:#17324d; --blue:#246b9e; --teal:#2f7d7a; --paper:#f5f7f8;
      --line:#cad5dd; --ink:#1f2a33; --muted:#657582; --green:#216e39; --amber:#8a5a00; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper);
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif; }}
    .hero {{ background:var(--navy); color:white; padding:44px max(5vw,28px); }}
    .hero h1 {{ margin:0 0 10px; font-size:30px; }}
    .hero p {{ margin:0; color:#d8e6ef; }}
    main {{ max-width:1180px; margin:0 auto; padding:28px 22px 60px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; margin-bottom:28px; }}
    .metric {{ background:white; border:1px solid var(--line); border-radius:10px; padding:15px; }}
    .metric strong {{ display:block; font-size:23px; color:var(--teal); }}
    .metric span {{ font-size:13px; color:var(--muted); }}
    .card {{ background:white; border:1px solid var(--line); border-radius:12px;
      padding:24px; margin:0 0 22px; box-shadow:0 4px 14px rgba(23,50,77,.06); }}
    .card header {{ border-bottom:2px solid #eaf3f8; padding-bottom:14px; }}
    .card h2 {{ margin:8px 0 5px; color:var(--navy); }}
    .card h3 {{ color:var(--blue); margin:24px 0 10px; font-size:17px; }}
    .card header p {{ margin:0; color:var(--muted); }}
    .qid {{ font-weight:700; color:var(--blue); }}
    .badge {{ border-radius:999px; padding:3px 9px; margin-left:8px; font-size:12px; font-weight:700; }}
    .badge.ok {{ background:#ddf2e2; color:var(--green); }}
    .badge.warn {{ background:#fff1cc; color:var(--amber); }}
    .facts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; margin-top:18px; }}
    .facts div {{ background:#f3f5f7; padding:11px; border-radius:7px; }}
    .facts strong,.facts span {{ display:block; }}
    .facts strong {{ font-size:12px; color:var(--muted); margin-bottom:4px; }}
    table {{ border-collapse:collapse; width:100%; font-size:14px; }}
    th,td {{ border-bottom:1px solid var(--line); text-align:left; padding:9px 8px; vertical-align:top; }}
    th {{ background:#eaf3f8; color:var(--navy); }}
    .text-block {{ border-left:4px solid var(--teal); background:#f8fbfb; padding:13px 15px; margin:10px 0; }}
    .source {{ color:var(--muted); font-size:12px; margin-bottom:8px; }}
    dl {{ margin:0; display:grid; grid-template-columns:90px 1fr; gap:7px 12px; }}
    dt {{ color:var(--blue); font-weight:700; }}
    dd {{ margin:0; white-space:pre-wrap; }}
    .notice {{ background:#fff1cc; color:var(--amber); padding:12px; border-radius:7px; }}
    details {{ margin-top:20px; }}
    summary {{ cursor:pointer; color:var(--blue); font-weight:700; }}
    pre {{ white-space:pre-wrap; word-break:break-all; background:#f3f5f7; padding:12px; max-height:260px; overflow:auto; }}
    .footnote {{ background:#e8f4f2; border-radius:10px; padding:16px 18px; color:#285b59; }}
  </style>
</head>
<body>
  <section class="hero">
    <h1>G02 · 任务数据库 MVP 抽查包</h1>
    <p>运行 {html.escape(run_id)} · 任务 1、2、1694、7304，以及重复 ID 11257 的两个版本</p>
  </section>
  <main>
    <section class="metrics">
      {''.join(f"<div class='metric'><strong>{value}</strong><span>{html.escape(key)}</span></div>" for key,value in metrics.items())}
    </section>
    <div class="footnote">本页展示的是当前已通过自动校验的 MVP 聚合结果。条件、目标组逻辑和任务链将在 G02 批准后继续深化。</div>
    {''.join(cards)}
  </main>
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_document, encoding="utf-8")
    return {
        "html": str(html_path),
        "json": str(json_path),
        "sample_quest_ids": [1, 2, 1694, 7304, 11257],
        "sample_version_count": sum(len(value) for value in samples.values()),
        "metrics": metrics,
    }
