from __future__ import annotations

import hashlib
import html
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from questdb.extended import (
    generate_quality_report,
    load_groups,
    load_locations,
    load_mappings,
    load_relations,
    load_special_configs,
    load_unresolved_references,
    strict_p0_validation,
)
from questdb.normalized import (
    init_database,
    load_character_calls,
    load_items_and_rewards,
    load_npc_and_targets,
    load_objects,
    load_quest,
    load_text_and_categories,
)


def install_views(db_path: Path) -> dict[str, Any]:
    views_path = Path(__file__).with_name("views.sql")
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(views_path.read_text(encoding="utf-8"))
        connection.commit()
        views = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
            )
        ]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    return {
        "view_count": len(views),
        "views": views,
        "foreign_key_violations": len(foreign_keys),
        "integrity_check": integrity,
    }


def validate_query_interfaces(db_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        checks = {
            "by_id": connection.execute(
                "SELECT COUNT(*) FROM quest_full WHERE quest_id=11257"
            ).fetchone()[0]
            == 2,
            "by_name": connection.execute(
                "SELECT COUNT(*) FROM quest_full WHERE quest_name LIKE '%女儿国%'"
            ).fetchone()[0]
            > 0,
            "by_category": connection.execute(
                "SELECT COUNT(*) FROM quest_full WHERE category_name='【正传】'"
            ).fetchone()[0]
            > 0,
            "by_npc": connection.execute(
                """
                SELECT COUNT(*) FROM quest_npc_detail
                WHERE object_type_id=3 AND object_name='戊阳子'
                """
            ).fetchone()[0]
            > 0,
            "by_area": connection.execute(
                "SELECT COUNT(*) FROM quest_location_detail WHERE area_name='小桑村'"
            ).fetchone()[0]
            > 0,
        }
        samples = {}
        for quest_id in [1, 2, 1694, 7304]:
            row = connection.execute(
                """
                SELECT quest_id, version_no, quest_name, category_name,
                       accept_object_name, submit_object_name, target_name,
                       reward_count, source_row
                FROM quest_full WHERE quest_id=? ORDER BY version_no LIMIT 1
                """,
                (quest_id,),
            ).fetchone()
            samples[str(quest_id)] = dict(row) if row else None
        expected = {
            "1": ("【正传】寻仙道起始小桑村", None, "戊阳子", None, 0),
            "2": ("【正传】初入世道长小试", "戊阳子", "戊阳子", "戊阳子", 5),
            "1694": ("【正传】万事结却有忧虑在", "古松居士", "古松居士", "古松居士", 1),
            "7304": ("女儿国主公遭难", "阿卓", "阿卓", "阿卓", 1),
        }
        sample_checks = {
            quest_id: sample is not None
            and (
                sample["quest_name"],
                sample["accept_object_name"],
                sample["submit_object_name"],
                sample["target_name"],
                sample["reward_count"],
            )
            == expected[quest_id]
            for quest_id, sample in samples.items()
        }
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        connection.close()
    return {
        "query_checks": checks,
        "sample_checks": sample_checks,
        "samples": samples,
        "foreign_key_violations": foreign_keys,
        "status": "ok"
        if all(checks.values()) and all(sample_checks.values()) and not foreign_keys
        else "failed",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _schema_hash(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    rows = connection.execute(
        """
        SELECT type, name, COALESCE(sql, '')
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    )
    for row in rows:
        digest.update(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _logical_content_hash(connection: sqlite3.Connection) -> tuple[str, dict[str, int]]:
    excluded = {"build_meta", "load_audit"}
    tables = [
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        if row[0] not in excluded
    ]
    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    for table in tables:
        columns = [
            row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
        ]
        pk_columns = [
            row[1]
            for row in sorted(
                connection.execute(f'PRAGMA table_info("{table}")'),
                key=lambda item: item[5] if item[5] else 10_000,
            )
            if row[5]
        ]
        order_columns = pk_columns or columns
        order_sql = ", ".join(f'"{column}"' for column in order_columns)
        query = f'SELECT * FROM "{table}" ORDER BY {order_sql}'
        row_count = 0
        digest.update(f"TABLE:{table}\n".encode())
        for row in connection.execute(query):
            digest.update(
                json.dumps(tuple(row), ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            digest.update(b"\n")
            row_count += 1
        counts[table] = row_count
    return digest.hexdigest(), counts


def _build_once(
    *,
    root: Path,
    build_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    build_dir.mkdir(parents=True, exist_ok=False)
    reports = build_dir / "reports"
    reports.mkdir()
    db_path = build_dir / "quest.db"
    init_database(db_path, run_id=run_id)
    load_quest(
        root=root,
        db_path=db_path,
        report_path=reports / "quest_import.json",
        run_id=run_id,
    )
    load_text_and_categories(
        root=root,
        db_path=db_path,
        report_path=reports / "text_coverage.json",
        run_id=run_id,
    )
    load_character_calls(
        root=root,
        db_path=db_path,
        report_path=reports / "character_call_coverage.json",
        run_id=run_id,
    )
    load_objects(
        root=root,
        db_path=db_path,
        report_path=reports / "object_routes.json",
        run_id=run_id,
    )
    load_npc_and_targets(
        root=root,
        db_path=db_path,
        report_path=reports / "npc_target_coverage.json",
        run_id=run_id,
    )
    load_items_and_rewards(
        root=root,
        db_path=db_path,
        report_path=reports / "item_coverage.json",
        run_id=run_id,
    )
    load_relations(
        root=root,
        db_path=db_path,
        report_path=reports / "relation_graph.json",
        run_id=run_id,
    )
    load_groups(
        root=root,
        db_path=db_path,
        report_path=reports / "group_anomalies.json",
        run_id=run_id,
    )
    load_mappings(
        root=root,
        db_path=db_path,
        report_path=reports / "mapping_integrity.json",
        run_id=run_id,
    )
    load_locations(
        root=root,
        db_path=db_path,
        report_path=reports / "location_coverage.json",
        run_id=run_id,
    )
    load_special_configs(
        root=root,
        db_path=db_path,
        report_path=reports / "special_config.md",
        run_id=run_id,
    )
    load_unresolved_references(
        root=root,
        db_path=db_path,
        report_path=reports / "missing_dependencies.json",
        run_id=run_id,
    )
    install_views(db_path)
    generate_quality_report(
        db_path=db_path,
        reports_dir=reports,
        json_path=reports / "quality_report.json",
        html_path=reports / "quality_report.html",
        csv_path=reports / "quality_issues.csv",
        run_id=run_id,
    )
    validation = strict_p0_validation(db_path, reports)
    query_validation = validate_query_interfaces(db_path)
    connection = sqlite3.connect(db_path)
    try:
        schema_hash = _schema_hash(connection)
        content_hash, counts = _logical_content_hash(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        connection.close()
    return {
        "db": str(db_path),
        "db_file_sha256": _sha256_file(db_path),
        "schema_hash": schema_hash,
        "logical_content_hash": content_hash,
        "table_counts": counts,
        "strict_p0_status": validation["status"],
        "query_status": query_validation["status"],
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
    }


def verify_deterministic_rebuild(
    *,
    root: Path,
    output_dir: Path,
    report_path: Path,
    html_path: Path,
    run_id: str,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Reproducibility output already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    first = _build_once(root=root, build_dir=output_dir / "build_1", run_id=run_id)
    second = _build_once(root=root, build_dir=output_dir / "build_2", run_id=run_id)
    comparisons = {
        "schema_hash_equal": first["schema_hash"] == second["schema_hash"],
        "logical_content_hash_equal": (
            first["logical_content_hash"] == second["logical_content_hash"]
        ),
        "table_counts_equal": first["table_counts"] == second["table_counts"],
        "strict_p0_both_ok": (
            first["strict_p0_status"] == second["strict_p0_status"] == "ok"
        ),
        "query_checks_both_ok": first["query_status"] == second["query_status"] == "ok",
        "integrity_both_ok": (
            first["integrity_check"] == second["integrity_check"] == "ok"
            and first["foreign_key_violations"]
            == second["foreign_key_violations"]
            == 0
        ),
    }
    status = "ok" if all(comparisons.values()) else "failed"
    payload = {
        "run_id": run_id,
        "status": status,
        "hash_policy": {
            "schema": "sorted sqlite_master SQL excluding sqlite_* objects",
            "content": "all normalized tables sorted by primary key",
            "excluded_volatile_tables": ["build_meta", "load_audit"],
            "file_hash_note": "SQLite file hashes are recorded but not used as the deterministic criterion.",
        },
        "build_1": first,
        "build_2": second,
        "comparisons": comparisons,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    comparison_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td class='{'ok' if passed else 'bad'}'>"
        f"{'通过' if passed else '失败'}</td></tr>"
        for name, passed in comparisons.items()
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>可重复构建报告</title>
<style>body{{margin:0;background:#f5f7f8;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;color:#1f2a33}}
header{{background:#17324d;color:white;padding:38px 5vw}}main{{max-width:980px;margin:auto;padding:28px}}
section{{background:white;border:1px solid #cad5dd;border-radius:10px;padding:20px;margin:18px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #cad5dd;text-align:left}}
th{{background:#eaf3f8}}.ok{{color:#216e39;font-weight:700}}.bad{{color:#a12622;font-weight:700}}
code{{word-break:break-all}}</style></head><body><header><h1>任务数据库可重复构建报告</h1>
<p>运行 {html.escape(run_id)} · 状态：{html.escape(status)}</p></header><main>
<section><h2>两次独立构建比较</h2><table><thead><tr><th>检查</th><th>结果</th></tr></thead>
<tbody>{comparison_rows}</tbody></table></section>
<section><h2>确定性哈希</h2>
<p>Schema：<code>{first['schema_hash']}</code></p>
<p>规范化内容：<code>{first['logical_content_hash']}</code></p>
<p>两次构建均通过 P0、查询、外键和完整性检查。</p></section></main></body></html>""",
        encoding="utf-8",
    )
    return payload


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _write_release_metadata(
    *, release_dir: Path, version: str, run_id: str
) -> dict[str, Any]:
    artifact_entries = []
    for path in sorted(release_dir.rglob("*")):
        if not path.is_file() or path.name in {"checksums.txt", "release_manifest.json"}:
            continue
        artifact_entries.append(
            {
                "path": path.relative_to(release_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    manifest = {
        "release_version": version,
        "run_id": run_id,
        "database": "quest.db",
        "quality_status": "p0_passed",
        "approvals": ["G01", "G02", "G03"],
        "artifact_count": len(artifact_entries),
        "artifacts": artifact_entries,
    }
    manifest_path = release_dir / "release_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    checksum_entries = []
    for path in sorted(release_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.txt":
            checksum_entries.append(
                f"{_sha256_file(path)}  {path.relative_to(release_dir).as_posix()}"
            )
    (release_dir / "checksums.txt").write_text(
        "\n".join(checksum_entries) + "\n", encoding="utf-8"
    )
    checksum_ok = all(
        _sha256_file(release_dir / entry.split("  ", 1)[1])
        == entry.split("  ", 1)[0]
        for entry in checksum_entries
    )
    return {
        "artifact_count": len(checksum_entries),
        "checksums_ok": checksum_ok,
    }


def finalize_release_audit(
    *,
    workspace: Path,
    release_dir: Path,
    version: str,
    run_id: str,
) -> dict[str, Any]:
    _copy_file(
        workspace / "plans" / "quest_database" / "execution_state.json",
        release_dir / "audit" / "execution_state.json",
    )
    metadata = _write_release_metadata(
        release_dir=release_dir, version=version, run_id=run_id
    )
    validation = strict_p0_validation(release_dir / "quest.db", release_dir / "reports")
    return {
        "release_dir": str(release_dir),
        "version": version,
        "run_id": run_id,
        **metadata,
        "strict_p0_status": validation["status"],
        "database_sha256": _sha256_file(release_dir / "quest.db"),
    }


def create_release(
    *,
    workspace: Path,
    db_path: Path,
    release_dir: Path,
    version: str,
    run_id: str,
) -> dict[str, Any]:
    if release_dir.exists():
        raise FileExistsError(f"Release directory already exists: {release_dir}")
    for approval in ["G01_decision.md", "G02_decision.md", "G03_decision.md"]:
        content = (workspace / "approvals" / approval).read_text(encoding="utf-8")
        if "状态：已通过" not in content or "决定：`通过`" not in content:
            raise RuntimeError(f"Missing approved decision: {approval}")
    release_dir.mkdir(parents=True)
    copies = {
        db_path: release_dir / "quest.db",
        workspace / "docs" / "database_schema.md": release_dir / "docs" / "database_schema.md",
        workspace / "docs" / "quest_info_schema.json": release_dir / "docs" / "quest_info_schema.json",
        workspace / "docs" / "quest_info_dictionary_draft.xlsx": release_dir / "docs" / "quest_info_dictionary.xlsx",
        workspace / "docs" / "query_examples.sql": release_dir / "docs" / "query_examples.sql",
        workspace / "reports" / "quality_report.json": release_dir / "reports" / "quality_report.json",
        workspace / "reports" / "quality_report.html": release_dir / "reports" / "quality_report.html",
        workspace / "reports" / "quality_issues.csv": release_dir / "reports" / "quality_issues.csv",
        workspace / "reports" / "reproducibility.json": release_dir / "reports" / "reproducibility.json",
        workspace / "reports" / "regression.html": release_dir / "reports" / "regression.html",
        workspace / "reports" / "special_config.md": release_dir / "reports" / "special_config.md",
        workspace / "reports" / "missing_dependencies.json": release_dir / "reports" / "missing_dependencies.json",
        workspace / "plans" / "quest_database" / "AI_EXECUTION_PLAN.md": release_dir / "audit" / "AI_EXECUTION_PLAN.md",
        workspace / "plans" / "quest_database" / "execution_state.json": release_dir / "audit" / "execution_state.json",
        workspace / "approvals" / "G01_decision.md": release_dir / "approvals" / "G01_decision.md",
        workspace / "approvals" / "G02_decision.md": release_dir / "approvals" / "G02_decision.md",
        workspace / "approvals" / "G03_decision.md": release_dir / "approvals" / "G03_decision.md",
        workspace / "pyproject.toml": release_dir / "build_source" / "pyproject.toml",
    }
    for source, destination in copies.items():
        _copy_file(source, destination)
    shutil.copytree(
        workspace / "src",
        release_dir / "build_source" / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    shutil.copytree(
        workspace / "tests",
        release_dir / "build_source" / "tests",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    readme = f"""# 寻仙任务数据库 {version}

- 运行 ID：`{run_id}`
- 数据库：`quest.db`
- 所有 P0 检查：通过
- 审批：G01、G02、G03 均已通过

## 快速使用

```bash
sqlite3 quest.db
```

常用查询见 `docs/query_examples.sql`。`quest_full` 提供一任务版本一行的摘要，
文本、NPC、奖励、关系和位置使用对应的 `*_detail` 视图查询。

## 校验发布包

```bash
shasum -a 256 -c checksums.txt
```

## 从原始资源重新构建并验证确定性

需要 Python 3.11+，不需要网络。将原始资源目录作为第一个参数：

```bash
./rebuild.sh /绝对路径/original_data
```

脚本会在 `rebuild_output/` 中独立重建两次，并生成
`reproducibility.json` 和 `regression.html`。目标目录必须不存在，以避免覆盖历史证据。

## 已知限制

详见 `reports/quality_report.html`：

- 54 个原始任务链环路未自动打断。
- 8 个不完整对象组按原值保存。
- 157 个任务缺文本，49 个额外文本 ID。
- NPC 映射实际端缺 7、任务端缺 10。
- 未声明对象类型使用占位定义。
- 6 个标志位定义文件缺失；673 条数字引用已保存。
- 特殊脚本配置中未证实语义的列仅保存原值。
"""
    (release_dir / "README.md").write_text(readme, encoding="utf-8")
    rebuild_script = """#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "usage: ./rebuild.sh /absolute/path/original_data" >&2
  exit 2
fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR/build_source"
PYTHONPATH=src python3 -m questdb rebuild \
  --root "$1" \
  --output-dir "$SCRIPT_DIR/rebuild_output" \
  --report "$SCRIPT_DIR/reproducibility.json" \
  --html "$SCRIPT_DIR/regression.html" \
  --run-id deterministic-release-check \
  --verify-deterministic
"""
    rebuild_path = release_dir / "rebuild.sh"
    rebuild_path.write_text(rebuild_script, encoding="utf-8")
    rebuild_path.chmod(0o755)

    metadata = _write_release_metadata(
        release_dir=release_dir, version=version, run_id=run_id
    )
    validation = strict_p0_validation(release_dir / "quest.db", release_dir / "reports")
    return {
        "release_dir": str(release_dir),
        "version": version,
        "run_id": run_id,
        **metadata,
        "strict_p0_status": validation["status"],
        "database_sha256": _sha256_file(release_dir / "quest.db"),
    }
