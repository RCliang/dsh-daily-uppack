"""午饭卡池。只读用户维护的 JSON，不补条目。"""

from __future__ import annotations

import json
from pathlib import Path

from chouka.errors import ChoukaError

REQUIRED = ("id", "name", "tags", "notes", "budget", "walk_minutes", "enabled")


def load_lunch(path: Path) -> list[dict]:
    if not path.is_file():
        raise ChoukaError(f"找不到午饭卡池 {path}。请编辑这个文件，或改 config/paths.json 的 lunch_pool。")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ChoukaError(f"无法解析午饭卡池 {path}: {exc}") from exc
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items")
    else:
        items = None
    if not isinstance(items, list):
        raise ChoukaError(f"{path} 需要是数组，或 {{\"items\": [...]}}")
    cards: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(items, start=1):
        cards.append(_card(path, index, raw, seen))
    if not cards:
        raise ChoukaError(f"{path} 里没有午饭条目")
    return cards


def _card(path: Path, index: int, raw: object, seen: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise ChoukaError(f"{path} 第 {index} 条不是对象")
    missing = [key for key in REQUIRED if key not in raw]
    if missing:
        raise ChoukaError(f"{path} 第 {index} 条缺少字段: {', '.join(missing)}")
    card_id = raw["id"]
    name = raw["name"]
    if not isinstance(card_id, str) or not card_id.strip():
        raise ChoukaError(f"{path} 第 {index} 条的 id 必须是非空字符串")
    if card_id in seen:
        raise ChoukaError(f"{path} 的 id 重复: {card_id}")
    seen.add(card_id)
    if not isinstance(name, str) or not name.strip():
        raise ChoukaError(f"{path} 第 {index} 条的 name 必须是非空字符串")
    tags = raw["tags"]
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ChoukaError(f"{path} 第 {index} 条的 tags 必须是非空字符串数组")
    notes = raw["notes"]
    if not isinstance(notes, str):
        raise ChoukaError(f"{path} 第 {index} 条的 notes 必须是字符串")
    budget = _number(path, index, "budget", raw["budget"])
    walk = _number(path, index, "walk_minutes", raw["walk_minutes"])
    if int(walk) != walk:
        raise ChoukaError(f"{path} 第 {index} 条的 walk_minutes 必须是整数")
    enabled = raw["enabled"]
    if not isinstance(enabled, bool):
        raise ChoukaError(f"{path} 第 {index} 条的 enabled 必须是 true 或 false")
    return {
        "id": card_id,
        "deck": "lunch",
        "title": name,
        "name": name,
        "tags": list(tags),
        "notes": notes,
        "budget": budget,
        "walk_minutes": int(walk),
        "enabled": enabled,
        "duration_seconds": None,
        "watch_variant": None,
    }


def _number(path: Path, index: int, field: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChoukaError(f"{path} 第 {index} 条的 {field} 必须是数字")
    if value < 0:
        raise ChoukaError(f"{path} 第 {index} 条的 {field} 不能是负数")
    return value
