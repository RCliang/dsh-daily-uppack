"""把最近一次抽取嵌进可以双击打开的预览页。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from chouka.errors import ChoukaError

_BLOCK = re.compile(
    r'(<script id="chouka-data" type="application/json">)(.*?)(</script>)',
    re.S,
)


def update_preview_file(path: Path, record: dict) -> bool:
    if not path.is_file():
        return False
    payload = payload_from_draw(record)
    body = json.dumps(payload, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    text = path.read_text(encoding="utf-8")
    updated, count = _BLOCK.subn(lambda match: match.group(1) + "\n" + body + "\n" + match.group(3), text, count=1)
    if count != 1:
        raise ChoukaError("预览页缺少 id 为 chouka-data 的脚本块")
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def payload_from_draw(record: dict) -> dict:
    deck = record.get("deck")
    kicker = "午饭" if deck == "lunch" else "精选"
    cards = []
    for card in record.get("cards") or []:
        face = card.get("face") or {}
        lines = _lines(deck, face, card.get("watch_variant"))
        cards.append(
            {
                "id": card.get("id"),
                "title": _clip(card.get("title"), 32),
                "reason": _clip(card.get("reason"), 72),
                "url": _url(face.get("url")),
                "watch_variant": card.get("watch_variant"),
                "kicker": kicker,
                "rarity": _rarity(face),
                "lines": lines,
            }
        )
    constraints = record.get("constraints") or {}
    category = constraints.get("tag") or constraints.get("zone_name") or constraints.get("zone")
    return {
        "source": "draw",
        "draw_id": record.get("draw_id"),
        "deck": deck,
        "drawn_at": record.get("drawn_at"),
        "category": category,
        "cards": cards,
    }


def _clip(text: object, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("https://") or text.startswith("http://"):
        return text
    return None


def _rarity(face: dict) -> str:
    tier = face.get("tier")
    if tier == "值得看":
        return "legendary"
    if tier == "可以看":
        return "rare"
    return "common"


def _lines(deck: str | None, face: dict, watch_variant: str | None) -> list[str]:
    if deck == "bili_featured":
        lines = [
            face.get("up") or "UP 未知",
            "时长 " + (face.get("duration_phrase") or "未知"),
            face.get("tier") or "未标档位",
        ]
    else:
        tags = "、".join(face.get("tags") or [])
        lines = [
            f"预算 {face.get('budget')}",
            f"步行 {face.get('walk_minutes')} 分钟",
        ]
        if tags:
            lines.append(tags)
    if watch_variant == "first_3_min":
        lines.append("只看前 3 分钟")
    return lines
