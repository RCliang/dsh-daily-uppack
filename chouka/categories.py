"""开包前的选项：午饭按标签，精选按关键词分区。"""

from __future__ import annotations

import json
from pathlib import Path

from chouka.bili_adapter import load_featured
from chouka.errors import ChoukaError
from chouka.lunch import load_lunch
from chouka.paths import load_paths

PACK_SIZE = 5
LUNCH_TAG_ORDER = ("清淡", "荤", "素", "蔬菜", "面", "重口")


def load_zone_defs(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ChoukaError(f"无法解析 {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("zones"), list):
        raise ChoukaError(f"{path} 必须是含 zones 数组的 JSON 对象")
    zones = []
    seen: set[str] = set()
    for item in raw["zones"]:
        if not isinstance(item, dict):
            raise ChoukaError(f"{path} 里的区必须是对象")
        zone_id = item.get("id")
        name = item.get("name")
        keywords = item.get("keywords")
        if not isinstance(zone_id, str) or not zone_id.strip():
            raise ChoukaError(f"{path} 里有区缺少 id")
        zone_id = zone_id.strip()
        if not isinstance(name, str) or not name.strip():
            raise ChoukaError(f"{path} 里的区 {zone_id} 缺少 name")
        if (
            not isinstance(keywords, list)
            or not keywords
            or not all(isinstance(word, str) and word.strip() for word in keywords)
        ):
            raise ChoukaError(f"{path} 里的区 {zone_id} 需要至少 1 个关键词")
        if zone_id in seen:
            raise ChoukaError(f"{path} 里的区 id 重复: {zone_id}")
        seen.add(zone_id)
        zones.append(
            {
                "id": zone_id,
                "name": name.strip(),
                "keywords": [word.strip() for word in keywords],
            }
        )
    return zones


def zone_ids_for(card: dict, zones: list[dict]) -> list[str]:
    text = " ".join(str(card.get(key) or "") for key in ("title", "why", "comment")).casefold()
    found = []
    for zone in zones:
        if any(word.casefold() in text for word in zone["keywords"]):
            found.append(zone["id"])
    return found


def apply_zones(cards: list[dict], zones: list[dict]) -> list[dict]:
    names = {zone["id"]: zone["name"] for zone in zones}
    annotated = []
    for card in cards:
        copy = dict(card)
        ids = zone_ids_for(copy, zones)
        copy["zones"] = ids
        copy["zone_names"] = [names[zone_id] for zone_id in ids]
        annotated.append(copy)
    return annotated


def list_categories(deck: str, *, root: Path | None = None) -> dict:
    if deck not in ("lunch", "bili_featured"):
        raise ChoukaError("deck 只能是 lunch 或 bili_featured")
    paths = load_paths(root)
    if deck == "lunch":
        cards = [card for card in load_lunch(paths.lunch_pool) if card.get("enabled", True)]
        counts: dict[str, int] = {}
        for card in cards:
            for tag in card.get("tags") or []:
                if isinstance(tag, str) and tag:
                    counts[tag] = counts.get(tag, 0) + 1
        ordered = [tag for tag in LUNCH_TAG_ORDER if tag in counts]
        ordered.extend(sorted(tag for tag in counts if tag not in LUNCH_TAG_ORDER))
        categories = [_category(tag, tag, counts[tag]) for tag in ordered]
    else:
        zones = load_zone_defs(paths.bili_zones)
        cards = load_featured(paths.bili_home)
        categories = [
            _category(zone["id"], zone["name"], sum(zone["id"] in zone_ids_for(card, zones) for card in cards))
            for zone in zones
        ]
    return {"deck": deck, "pack_size": PACK_SIZE, "categories": categories}


def _category(category_id: str, name: str, count: int) -> dict:
    return {
        "id": category_id,
        "name": name,
        "count": count,
        "ready": count >= PACK_SIZE,
        "short": max(0, PACK_SIZE - count),
    }
