from __future__ import annotations

import argparse
import base64
import json
import multiprocessing
import shutil
import sqlite3
import sys
import time
import zlib
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
LOCAL_VIEWER_ROOT = WORKSPACE_ROOT / "apps" / "quest_viewer"
WORKER_ROOT = WORKSPACE_ROOT / "apps" / "quest_viewer_cloudflare"
SOURCE_DATABASE = (
    WORKSPACE_ROOT
    / "outputs"
    / "quest_database"
    / "releases"
    / "1.0.1"
    / "quest.db"
)
OUTPUT_DIRECTORY = WORKER_ROOT / "data"
OUTPUT_DATABASE = OUTPUT_DIRECTORY / "quest_web.db"
OUTPUT_SQL = OUTPUT_DIRECTORY / "quest_web.sql"
GENERATED_TEMPLATE = WORKER_ROOT / "src" / "generated_template.py"
GENERATED_FACETS = WORKER_ROOT / "src" / "generated_facets.py"
GENERATED_VERSION = WORKER_ROOT / "src" / "generated_version.py"
VERSION_FILE = LOCAL_VIEWER_ROOT / "VERSION"

sys.path.insert(0, str(LOCAL_VIEWER_ROOT))

from quest_viewer.app import _prepare_detail, repository  # noqa: E402
from quest_viewer.repository import AREA_FILTER_MEMBERS  # noqa: E402


def _encode_detail(detail: dict[str, Any]) -> str:
    raw = json.dumps(
        detail,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")


def _build_one(quest_id: int) -> tuple[int, str, str]:
    detail = _prepare_detail(repository.get(quest_id))
    if not detail:
        raise RuntimeError(f"任务 {quest_id} 无法读取")
    summary = detail["summary"]
    search_summary = {
        "quest_id": quest_id,
        "version_no": detail["primary"]["version_no"],
        "conflict_flag": summary.get("conflict_flag", 0),
        "quest_name": summary["quest_name"],
        "category_name": summary.get("category_name"),
        "main_category_name": summary.get("main_category_name"),
        "sub_category_name": summary.get("sub_category_name"),
        "level_requirement": summary.get("level_requirement"),
        "max_level": summary.get("max_level"),
        "accept_object_name": summary.get("accept_object_name"),
        "submit_object_name": summary.get("submit_object_name"),
        "area_name": summary.get("area_name"),
        "root_area_name": summary.get("root_area_name"),
        "subarea_name": summary.get("subarea_name"),
        "text_row_count": summary.get("text_row_count", 0),
        "objective_count": summary.get("objective_count", 0),
        "reward_count": summary.get("reward_count", 0),
        "source_variant_count": len(detail.get("variants", [])),
    }
    return (
        quest_id,
        json.dumps(search_summary, ensure_ascii=False, separators=(",", ":")),
        _encode_detail(detail),
    )


def _npc_search_text() -> dict[int, str]:
    with sqlite3.connect(SOURCE_DATABASE) as connection:
        return {
            int(row[0]): row[1] or ""
            for row in connection.execute(
                """
                SELECT quest_id, GROUP_CONCAT(DISTINCT object_name)
                FROM quest_npc_detail
                GROUP BY quest_id
                """
            )
        }


def _quest_ids(limit: int | None) -> list[int]:
    with sqlite3.connect(SOURCE_DATABASE) as connection:
        query = """
            SELECT DISTINCT quest_id
            FROM quest_full
            ORDER BY quest_id
        """
        if limit:
            query += " LIMIT ?"
            return [row[0] for row in connection.execute(query, (limit,))]
        return [row[0] for row in connection.execute(query)]


def _create_output_database() -> sqlite3.Connection:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATABASE.unlink(missing_ok=True)
    connection = sqlite3.connect(OUTPUT_DATABASE)
    connection.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE web_quest (
            quest_id INTEGER PRIMARY KEY,
            quest_name TEXT NOT NULL,
            npc_search_text TEXT NOT NULL DEFAULT '',
            root_area_name TEXT,
            main_category_name TEXT,
            sub_category_name TEXT,
            level_requirement INTEGER,
            summary_json TEXT NOT NULL,
            detail_z TEXT NOT NULL
        );
        CREATE INDEX idx_web_quest_area
            ON web_quest(root_area_name, quest_id);
        CREATE INDEX idx_web_quest_category
            ON web_quest(main_category_name, sub_category_name, quest_id);
        CREATE TABLE web_metadata (
            metadata_key TEXT PRIMARY KEY,
            metadata_value TEXT NOT NULL
        );
        """
    )
    return connection


def _write_generated_modules() -> None:
    template_path = (
        LOCAL_VIEWER_ROOT / "quest_viewer" / "templates" / "index.html"
    )
    template_source = template_path.read_text(encoding="utf-8")
    template_source = template_source.replace(
        "{{ url_for('static', path='/favicon.svg') }}",
        "/static/favicon.svg",
    ).replace(
        "{{ url_for('static', path='/styles.css') }}",
        "/static/styles.css",
    ).replace(
        "{{ url_for('static', path='/app.js') }}",
        "/static/app.js",
    )
    GENERATED_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_TEMPLATE.write_text(
        "TEMPLATE_SOURCE = " + repr(template_source) + "\n",
        encoding="utf-8",
    )
    site_version = VERSION_FILE.read_text(encoding="utf-8").strip()
    GENERATED_VERSION.write_text(
        "SITE_VERSION = " + repr(site_version) + "\n",
        encoding="utf-8",
    )
    facets = repository.facets()
    GENERATED_FACETS.write_text(
        "FACETS = "
        + repr(facets)
        + "\nAREA_FILTER_MEMBERS = "
        + repr(AREA_FILTER_MEMBERS)
        + "\n",
        encoding="utf-8",
    )
    public_static = WORKER_ROOT / "public" / "static"
    if public_static.exists():
        shutil.rmtree(public_static)
    shutil.copytree(
        LOCAL_VIEWER_ROOT / "quest_viewer" / "static",
        public_static,
    )


def _write_d1_dump(connection: sqlite3.Connection) -> None:
    statements = [
        statement
        for statement in connection.iterdump()
        if statement not in {"BEGIN TRANSACTION;", "COMMIT;"}
    ]
    longest = max(map(len, statements), default=0)
    if longest > 100_000:
        raise RuntimeError(
            f"D1 单条 SQL 超过 100KB：{longest} bytes"
        )
    OUTPUT_SQL.write_text("\n".join(statements) + "\n", encoding="utf-8")


def build(limit: int | None, processes: int) -> None:
    started = time.monotonic()
    quest_ids = _quest_ids(limit)
    npc_names = _npc_search_text()
    connection = _create_output_database()
    insert_sql = """
        INSERT INTO web_quest (
            quest_id, quest_name, npc_search_text,
            root_area_name, main_category_name, sub_category_name,
            level_requirement, summary_json, detail_z
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    if processes == 1:
        results = map(_build_one, quest_ids)
    else:
        pool = multiprocessing.Pool(processes=processes)
        results = pool.imap_unordered(_build_one, quest_ids, chunksize=8)

    try:
        for completed, (quest_id, summary_json, detail_z) in enumerate(
            results, start=1
        ):
            summary = json.loads(summary_json)
            connection.execute(
                insert_sql,
                (
                    quest_id,
                    summary["quest_name"],
                    npc_names.get(quest_id, ""),
                    summary.get("root_area_name"),
                    summary.get("main_category_name"),
                    summary.get("sub_category_name"),
                    summary.get("level_requirement"),
                    summary_json,
                    detail_z,
                ),
            )
            if completed % 100 == 0 or completed == len(quest_ids):
                connection.commit()
                elapsed = time.monotonic() - started
                print(
                    f"{completed}/{len(quest_ids)} "
                    f"({elapsed:.1f}s)",
                    flush=True,
                )
    finally:
        if processes != 1:
            pool.close()
            pool.join()

    connection.execute(
        """
        INSERT INTO web_metadata (metadata_key, metadata_value)
        VALUES ('quest_count', ?)
        """,
        (str(len(quest_ids)),),
    )
    connection.commit()
    connection.execute("VACUUM")
    _write_d1_dump(connection)
    connection.close()
    _write_generated_modules()
    print(
        f"数据库：{OUTPUT_DATABASE} "
        f"({OUTPUT_DATABASE.stat().st_size / 1024 / 1024:.1f} MB)"
    )
    print(
        f"D1 导入文件：{OUTPUT_SQL} "
        f"({OUTPUT_SQL.stat().st_size / 1024 / 1024:.1f} MB)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--processes",
        type=int,
        default=max(1, min(4, multiprocessing.cpu_count())),
    )
    args = parser.parse_args()
    build(args.limit, max(1, args.processes))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
