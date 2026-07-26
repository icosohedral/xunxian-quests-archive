from __future__ import annotations

import base64
import json
import math
import re
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import asgi
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import BaseLoader, Environment, select_autoescape
from workers import WorkerEntrypoint

from generated_facets import AREA_FILTER_MEMBERS, FACETS
from generated_template import TEMPLATE_SOURCE
from generated_version import SITE_VERSION


PAGE_SIZE = 5
CHINA_TIMEZONE = timezone(timedelta(hours=8))
VISITOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,80}$")


def compact_number(value: int | float | str | None) -> str:
    if value is None:
        return "0"
    number = int(value)
    absolute = abs(number)
    if absolute >= 100_000_000:
        rounded = (absolute + 50_000_000) // 100_000_000
        return f"{'-' if number < 0 else ''}{rounded}亿"
    if absolute >= 10_000:
        rounded = (absolute + 5_000) // 10_000
        return f"{'-' if number < 0 else ''}{rounded}万"
    return str(number)


templates = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(default=True),
)
templates.filters["compact_number"] = compact_number
index_template = templates.from_string(TEMPLATE_SOURCE)

app = FastAPI(
    title="寻仙任务存档",
    description="Cloudflare Workers 上的寻仙任务资料库",
    version=SITE_VERSION,
)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)


def _to_python(value: Any) -> Any:
    if hasattr(value, "to_py"):
        return value.to_py()
    return value


def _result_rows(result: Any) -> list[dict[str, Any]]:
    rows = _to_python(result.results)
    return [dict(_to_python(row)) for row in rows]


def _decode_detail(value: str) -> dict[str, Any]:
    compressed = base64.b64decode(value)
    return json.loads(zlib.decompress(compressed).decode("utf-8"))


async def _search(
    database: Any,
    *,
    q: str = "",
    npc: str = "",
    area: str = "",
    category: str = "",
    subcategory: str = "",
    page: int = 1,
    window: int = 0,
) -> dict[str, Any]:
    page = max(1, page)
    window = max(0, min(3, window))
    conditions = ["1=1"]
    parameters: list[Any] = []
    q = q.strip()
    npc = npc.strip()
    area = area.strip()
    category = category.strip()
    subcategory = subcategory.strip()
    if q:
        conditions.append("quest_name LIKE ?")
        parameters.append(f"%{q}%")
    if npc:
        conditions.append("npc_search_text LIKE ?")
        parameters.append(f"%{npc}%")
    if area:
        area_members = AREA_FILTER_MEMBERS.get(area, (area,))
        placeholders = ", ".join("?" for _ in area_members)
        conditions.append(
            f"COALESCE(root_area_name, '') IN ({placeholders})"
        )
        parameters.extend(area_members)
    if category:
        conditions.append("COALESCE(main_category_name, '') = ?")
        parameters.append(category)
    if subcategory:
        conditions.append("COALESCE(sub_category_name, '') = ?")
        parameters.append(subcategory)
    where_sql = " AND ".join(conditions)

    count_statement = database.prepare(
        f"SELECT COUNT(*) AS total FROM web_quest WHERE {where_sql}"
    )
    if parameters:
        count_statement = count_statement.bind(*parameters)
    count_rows = _result_rows(await count_statement.run())
    total = int(count_rows[0]["total"]) if count_rows else 0

    page_count = max(1, math.ceil(total / PAGE_SIZE))
    window_start_page = max(1, page - window)
    window_end_page = min(page_count, page + window)
    list_parameters = [
        *parameters,
        (window_end_page - window_start_page + 1) * PAGE_SIZE,
        (window_start_page - 1) * PAGE_SIZE,
    ]
    list_statement = database.prepare(
        f"""
        SELECT summary_json
        FROM web_quest
        WHERE {where_sql}
        ORDER BY level_requirement IS NULL,
                 level_requirement,
                 quest_id
        LIMIT ? OFFSET ?
        """
    ).bind(*list_parameters)
    rows = _result_rows(await list_statement.run())
    window_items = [json.loads(row["summary_json"]) for row in rows]
    prefetched_pages: dict[str, list[dict[str, Any]]] = {}
    for prefetched_page in range(window_start_page, window_end_page + 1):
        start = (prefetched_page - window_start_page) * PAGE_SIZE
        prefetched_pages[str(prefetched_page)] = window_items[
            start : start + PAGE_SIZE
        ]
    return {
        "items": prefetched_pages.get(str(page), []),
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "page_count": page_count,
        "prefetched_pages": prefetched_pages if window else {},
    }


async def _get_detail(database: Any, quest_id: int) -> dict[str, Any] | None:
    result = await database.prepare(
        """
        SELECT detail_z
        FROM web_quest
        WHERE quest_id=?
        """
    ).bind(quest_id).run()
    rows = _result_rows(result)
    return _decode_detail(rows[0]["detail_z"]) if rows else None


async def _visitor_count(database: Any) -> int:
    today = datetime.now(CHINA_TIMEZONE).date().isoformat()
    existing = _result_rows(
        await database.prepare(
            """
            SELECT visitor_count
            FROM daily_visit
            WHERE visit_day=?
            """
        ).bind(today).run()
    )
    return int(existing[0]["visitor_count"]) if existing else 0


async def _record_visit(database: Any, visitor_id: str) -> tuple[int, str, bool]:
    today = datetime.now(CHINA_TIMEZONE).date().isoformat()
    inserted = _result_rows(
        await database.prepare(
            """
            INSERT OR IGNORE INTO daily_visitor (visit_day, visitor_id)
            VALUES (?, ?)
            RETURNING visitor_id
            """
        ).bind(today, visitor_id).run()
    )
    is_new = bool(inserted)
    if is_new:
        await database.prepare(
            """
            INSERT INTO daily_visit (visit_day, visitor_count)
            VALUES (?, 1)
            ON CONFLICT(visit_day) DO UPDATE
            SET visitor_count=visitor_count + 1
            """
        ).bind(today).run()
    count = await _visitor_count(database)
    return count, today, is_new


def _query_url(
    *,
    q: str,
    npc: str,
    area: str,
    category: str,
    subcategory: str,
    page: int,
    selected: int | None = None,
) -> str:
    values: dict[str, Any] = {
        "q": q,
        "npc": npc,
        "area": area,
        "category": category,
        "subcategory": subcategory,
        "page": page,
    }
    if selected is not None:
        values["selected"] = selected
    return f"/?{urlencode({key: value for key, value in values.items() if value not in ('', None)})}"


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    env = request.scope["env"]
    rows = _result_rows(
        await env.QUEST_DB.prepare(
            """
            SELECT metadata_value
            FROM web_metadata
            WHERE metadata_key='quest_count'
            """
        ).run()
    )
    return JSONResponse(
        {
            "status": "ok" if rows else "failed",
            "mode": "cloudflare-d1",
            "quest_count": int(rows[0]["metadata_value"]) if rows else 0,
        },
        status_code=200 if rows else 503,
    )


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    q: str = "",
    npc: str = "",
    area: str = "",
    category: str = "",
    subcategory: str = "",
    page: int = Query(1, ge=1),
    selected: int | None = Query(None, ge=1),
) -> HTMLResponse:
    env = request.scope["env"]
    search = await _search(
        env.QUEST_DB,
        q=q,
        npc=npc,
        area=area,
        category=category,
        subcategory=subcategory,
        page=page,
    )
    if selected is None:
        if not any([q, npc, area, category, subcategory]):
            selected = 90
        elif search["items"]:
            selected = search["items"][0]["quest_id"]
    detail = await _get_detail(env.QUEST_DB, selected) if selected else None
    visitor_count = await _visitor_count(env.VISITS_DB)
    html = index_template.render(
        request=request,
        site_version=SITE_VERSION,
        today_visitors=visitor_count,
        search=search,
        detail=detail,
        facets=FACETS,
        filters={
            "q": q,
            "npc": npc,
            "area": area,
            "category": category,
            "subcategory": subcategory,
        },
        preserved_query=urlencode(
            {
                key: value
                for key, value in {
                    "q": q,
                    "npc": npc,
                    "area": area,
                    "category": category,
                    "subcategory": subcategory,
                    "page": page,
                }.items()
                if value not in ("", None)
            }
        ),
        prev_url=_query_url(
            q=q,
            npc=npc,
            area=area,
            category=category,
            subcategory=subcategory,
            page=max(1, page - 1),
            selected=selected,
        ),
        next_url=_query_url(
            q=q,
            npc=npc,
            area=area,
            category=category,
            subcategory=subcategory,
            page=min(search["page_count"], page + 1),
            selected=selected,
        ),
    )
    return HTMLResponse(html)


@app.get("/quests/{quest_id}")
async def quest_page(quest_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/?selected={quest_id}", status_code=302)


@app.post("/api/visit")
async def api_visit(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的访问标识") from None
    visitor_id = str(payload.get("visitor_id", ""))
    if not VISITOR_ID_PATTERN.fullmatch(visitor_id):
        raise HTTPException(status_code=422, detail="无效的访问标识")
    count, visit_day, is_new = await _record_visit(
        request.scope["env"].VISITS_DB,
        visitor_id,
    )
    return JSONResponse(
        {"count": count, "visit_day": visit_day, "is_new": is_new}
    )


@app.get("/api/quests")
async def api_quests(
    request: Request,
    q: str = "",
    npc: str = "",
    area: str = "",
    category: str = "",
    subcategory: str = "",
    page: int = Query(1, ge=1),
    window: int = Query(0, ge=0, le=3),
) -> dict[str, Any]:
    return await _search(
        request.scope["env"].QUEST_DB,
        q=q,
        npc=npc,
        area=area,
        category=category,
        subcategory=subcategory,
        page=page,
        window=window,
    )


@app.get("/api/quests/{quest_id}")
async def api_quest(request: Request, quest_id: int) -> dict[str, Any]:
    detail = await _get_detail(request.scope["env"].QUEST_DB, quest_id)
    if not detail:
        raise HTTPException(status_code=404, detail="任务不存在")
    return detail


@app.get("/api/quests/{quest_id}/relations")
async def api_relations(
    request: Request,
    quest_id: int,
    depth: int = Query(1, ge=1, le=2),
) -> dict[str, Any]:
    detail = await _get_detail(request.scope["env"].QUEST_DB, quest_id)
    if not detail:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "quest_id": quest_id,
        "depth": depth,
        "relations": detail["relations"],
        "bounded": True,
    }
