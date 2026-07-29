from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .config import load_settings
from .db import database_health
from .repository import QuestRepository
from .tags import tokenize_text
from .version import SITE_VERSION
from .visitors import DailyVisitorCounter


settings = load_settings()
repository = QuestRepository(settings.database_path, page_size=settings.page_size)
visitor_counter = DailyVisitorCounter(settings.visitor_database_path)
package_dir = __import__("pathlib").Path(__file__).resolve().parent

app = FastAPI(
    title="寻仙任务卷宗台",
    description="本地只读任务信息浏览器",
    version=SITE_VERSION,
)
app.mount("/static", StaticFiles(directory=package_dir / "static"), name="static")
templates = Jinja2Templates(directory=package_dir / "templates")


def compact_number(value: int | float | str | None) -> str:
    if value is None:
        return "0"
    number = int(value)
    absolute = abs(number)
    if absolute >= 1_000_000_000_000:
        rounded_tenths = (
            absolute + 50_000_000_000
        ) // 100_000_000_000
        whole, decimal = divmod(rounded_tenths, 10)
        display = f"{whole}.{decimal}" if decimal else str(whole)
        return f"{'-' if number < 0 else ''}{display}万亿"
    if absolute >= 100_000_000:
        rounded = (absolute + 50_000_000) // 100_000_000
        return f"{'-' if number < 0 else ''}{rounded}亿"
    if absolute >= 10_000:
        rounded = (absolute + 5_000) // 10_000
        return f"{'-' if number < 0 else ''}{rounded}万"
    return str(number)


templates.env.filters["compact_number"] = compact_number


class VisitorPing(BaseModel):
    visitor_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")

TEXT_FIELDS = [
    ("accept_dialogue", "接取对话"),
    ("quest_description", "任务背景"),
    ("hint_text", "提示文字"),
    ("progress_dialogue", "进行中"),
    ("completion_dialogue", "完成对话"),
]


def _prepare_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    quest_id = detail["summary"]["quest_id"]
    version_no = detail["primary"]["version_no"]
    text_row = detail["texts"][0] if detail["texts"] else {}
    sections = []
    default_evidence = None
    for field, label in TEXT_FIELDS:
        raw_text = text_row.get(field, "")
        tokens = tokenize_text(
            raw_text,
            repository=repository,
            quest_id=quest_id,
            version_no=version_no,
        )
        for token in tokens:
            resolution = token.get("resolution")
            if (
                default_evidence is None
                and resolution
                and resolution.get("status") == "resolved"
            ):
                default_evidence = resolution
        sections.append(
            {
                "field": field,
                "label": label,
                "raw_text": raw_text,
                "tokens": tokens,
                "is_empty": not bool(raw_text),
            }
        )
    if default_evidence is None and detail["locations"]:
        location = detail["locations"][0]
        default_evidence = {
            "status": "resolved",
            "kind": "target",
            "label": location["target_name"],
            "namespace": "任务追踪目标",
            "target_id": location["target_id"],
            "area_name": location["area_name"],
            "resource_key": location["resource_key"],
            "source_file": location["source_file"],
            "source_row": location["source_row"],
            "raw_tag": f"<target:{location['target_id']}>",
        }
    detail["text_sections"] = sections
    detail["default_evidence"] = default_evidence
    summary = detail["summary"]
    detail["accept_role"] = (
        repository.resolve_npc_role(
            quest_id=quest_id,
            npc_id=summary["accept_object_id"],
            namespace="接取 NPC",
        )
        if summary.get("accept_object_type") == 3
        and summary.get("accept_object_id") is not None
        else None
    )
    detail["submit_role"] = (
        repository.resolve_npc_role(
            quest_id=quest_id,
            npc_id=summary["submit_object_id"],
            namespace="提交 NPC",
        )
        if summary.get("submit_object_type") == 3
        and summary.get("submit_object_id") is not None
        else None
    )
    for objective in detail["objectives"]:
        objective["role_resolution"] = (
            repository.resolve_npc_role(
                quest_id=quest_id,
                npc_id=objective["object_id"],
                namespace="任务目标 NPC",
            )
            if objective.get("object_type_id") == 3
            and objective.get("object_id") is not None
            else None
        )
    return detail


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
def health() -> JSONResponse:
    try:
        result = database_health(settings.database_path)
    except (FileNotFoundError, OSError) as error:
        return JSONResponse(
            {"status": "failed", "mode": "read-only", "error": str(error)},
            status_code=503,
        )
    return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503)


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    npc: str = "",
    area: str = "",
    category: str = "",
    subcategory: str = "",
    page: int = Query(1, ge=1),
    selected: int | None = Query(None, ge=1),
) -> HTMLResponse:
    visitor_count = visitor_counter.count()
    try:
        search = repository.search(
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
        detail = _prepare_detail(repository.get(selected)) if selected else None
        facets = repository.facets()
    except (FileNotFoundError, OSError) as error:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": str(error)},
            status_code=503,
        )
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "site_version": SITE_VERSION,
            "today_visitors": visitor_count,
            "search": search,
            "detail": detail,
            "facets": facets,
            "filters": {
                "q": q,
                "npc": npc,
                "area": area,
                "category": category,
                "subcategory": subcategory,
            },
            "preserved_query": urlencode(
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
            "prev_url": _query_url(
                q=q,
                npc=npc,
                area=area,
                category=category,
                subcategory=subcategory,
                page=max(1, page - 1),
                selected=selected,
            ),
            "next_url": _query_url(
                q=q,
                npc=npc,
                area=area,
                category=category,
                subcategory=subcategory,
                page=min(search["page_count"], page + 1),
                selected=selected,
            ),
        },
    )
    return response


@app.get("/quests/{quest_id}")
def quest_page(quest_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/?selected={quest_id}", status_code=302)


@app.post("/api/visit")
def api_visit(payload: VisitorPing) -> dict[str, Any]:
    count, visit_day, is_new = visitor_counter.record(payload.visitor_id)
    return {"count": count, "visit_day": visit_day, "is_new": is_new}


@app.get("/api/quests")
def api_quests(
    q: str = "",
    npc: str = "",
    area: str = "",
    category: str = "",
    subcategory: str = "",
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    return repository.search(
        q=q,
        npc=npc,
        area=area,
        category=category,
        subcategory=subcategory,
        page=page,
    )


@app.get("/api/quests/{quest_id}")
def api_quest(quest_id: int) -> dict[str, Any]:
    detail = repository.get(quest_id)
    if not detail:
        raise HTTPException(status_code=404, detail="任务不存在")
    return detail


@app.get("/api/quests/{quest_id}/relations")
def api_relations(
    quest_id: int, depth: int = Query(1, ge=1, le=2)
) -> dict[str, Any]:
    detail = repository.get(quest_id)
    if not detail:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "quest_id": quest_id,
        "depth": depth,
        "relations": detail["relations"],
        "bounded": True,
    }
