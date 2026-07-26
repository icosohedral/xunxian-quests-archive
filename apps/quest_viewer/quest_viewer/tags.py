from __future__ import annotations

import re
from typing import Any

from .repository import QuestRepository


TAG_PATTERN = re.compile(
    r"<(?P<kind>enemy|target|item|character|area|c|brief|aim|friend|ic):"
    r"(?P<value>[^>]*)>"
)

HIDDEN_ITEM_HINTS = {
    "（提示：点击带有下划线的文字便可以出现寻路路线。）",
}

TAG_KIND_ALIASES = {
    "targte": "target",
    "targer": "target",
    "taget": "target",
    "taret": "target",
    "traget": "target",
}

# quest_text 中只有这一种 <ic:ID>。index_list 将该编号空间指向全局
# 道具列表；item_list2.txt 中 47791 的名称为“VIP凭证”。
INLINE_ITEM_NAMES = {
    "47791": "VIP凭证",
}


def _normalize_markup(text: str) -> str:
    normalized = text.replace("\\n", "\n")
    normalized = normalized.replace("<c>", "").replace("<name>", "玩家")
    normalized = re.sub(
        r"<(enemy|target|item|character|area|brief|aim|friend|ic)：",
        r"<\1:",
        normalized,
    )
    for typo, canonical in TAG_KIND_ALIASES.items():
        normalized = re.sub(
            rf"<{typo}\s*[:：]",
            f"<{canonical}:",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


def tokenize_text(
    text: str | None,
    *,
    repository: QuestRepository,
    quest_id: int,
    version_no: int,
) -> list[dict[str, Any]]:
    if not text:
        return []
    normalized = _normalize_markup(text)
    tokens: list[dict[str, Any]] = []
    cursor = 0
    for match in TAG_PATTERN.finditer(normalized):
        if match.start() > cursor:
            tokens.append({"type": "text", "value": normalized[cursor : match.start()]})
        kind = match.group("kind")
        value = match.group("value")
        if kind == "c":
            cursor = match.end()
            continue
        if kind == "area":
            if value:
                tokens.append({"type": "text", "value": value})
            cursor = match.end()
            continue
        if kind in {"brief", "aim"}:
            if value:
                tokens.append({"type": "text", "value": value})
            cursor = match.end()
            continue
        if kind == "ic":
            label = INLINE_ITEM_NAMES.get(value.strip())
            if label:
                tokens.append({"type": "text", "value": label})
            cursor = match.end()
            continue
        if kind == "friend":
            resolution = repository.resolve_friend_role(
                quest_id=quest_id,
                version_no=version_no,
                name=value.strip(),
            )
            if resolution:
                tokens.append(
                    {
                        "type": "tag",
                        "value": match.group(0),
                        "resolution": resolution,
                    }
                )
            elif value:
                tokens.append({"type": "text", "value": value})
            cursor = match.end()
            continue
        if kind == "item" and value.strip() in HIDDEN_ITEM_HINTS:
            cursor = match.end()
            continue
        if "提示：" in value or "提示:" in value:
            tokens.append({"type": "text", "value": value})
            cursor = match.end()
            continue
        resolution = repository.resolve_tag(
            quest_id=quest_id,
            version_no=version_no,
            tag_kind=kind,
            value=value,
        )
        if kind == "enemy" and resolution["status"] != "resolved":
            if value:
                tokens.append({"type": "text", "value": value})
        else:
            tokens.append(
                {
                    "type": "tag",
                    "value": match.group(0),
                    "resolution": resolution,
                }
            )
        cursor = match.end()
    if cursor < len(normalized):
        tokens.append({"type": "text", "value": normalized[cursor:]})
    return tokens
