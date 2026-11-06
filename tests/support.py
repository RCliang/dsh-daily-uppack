"""测试用的临时项目。"""

from __future__ import annotations

import json
from pathlib import Path


def write_project(root: Path, items: list[dict], bili_home: Path | None = None) -> Path:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    config = {
        "lunch_pool": "data/lunch.json",
        "draws": "data/draws.jsonl",
        "bili_home": str(bili_home) if bili_home else None,
    }
    (root / "config" / "paths.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    (root / "data" / "lunch.json").write_text(
        json.dumps({"items": items}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def meal(card_id: str, name: str, tags: list[str], budget: int, walk: int, enabled: bool = True) -> dict:
    return {
        "id": card_id,
        "name": name,
        "tags": tags,
        "notes": "测试条目",
        "budget": budget,
        "walk_minutes": walk,
        "enabled": enabled,
    }
