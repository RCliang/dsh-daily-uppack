"""只读适配 dsh-bili-scroll 已经写下的精选结果。

真实文件（插件家目录，默认 ~/.dsh/bili-duty）：

- seen.md          判重表。精选 = 状态列「挑了」（与插件 parseSeenTable 的 picked 同一套判断）
- out/YYYY-MM-DD.md  日报。`### BV…` 一块一条，补标题、UP、链接、播放、档位、为什么值得、评语
- reports/BV-日期.md 单条笔记。日报里缺「为什么值得」时才用来补

插件不落盘封面，也不写结构化时长。封面只在请求时向 B 站要，这里不联网。
时长从标题 / 为什么值得 / 评语里的「N分钟」「N分半」「N小时」解析；没有就留空。
若 bili_home/covers/<BV>.jpg|png|webp 已经存在，才把本地路径填进 cover。
"""

from __future__ import annotations

import re
from pathlib import Path

from chouka.errors import ChoukaError
from chouka.rules import watch_variant_for

_BV = re.compile(r"^BV[0-9A-Za-z]{10}$")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_BLOCK = re.compile(r"\n(?=###\s*BV)")
_URL = re.compile(r"https://www\.bilibili\.com/video/(BV[0-9A-Za-z]+)/?")
_PLAY = re.compile(r"播放\s*([0-9]+(?:\.[0-9]+)?万?)")
_TIER = re.compile(r"(值得看|可以看|不值当)")
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(小时|分半|分钟|分)")
_SKIPPED = re.compile(r"跳过|跳了|没挑")
_PICKED = re.compile(r"挑|收|选|值得看|可以看")
_LABELS = (
    ("为什么值得", "why"),
    ("我的一句话", "comment"),
    ("我的话", "comment"),
    ("档位", "tier"),
    ("标题", "title"),
    ("UP", "up"),
)
_STOP = ("其余", "因无字幕", "本轮", "总结", "跳过的", "还没发过")


def load_featured(home: Path) -> list[dict]:
    home = Path(home)
    seen_path = home / "seen.md"
    if not seen_path.is_file():
        raise ChoukaError(
            f"找不到精选判重表 {seen_path}。"
            "dsh-bili-scroll 会把它写在 bili-duty 家目录的 seen.md。"
            "请在 config/paths.json 设置 bili_home，或设置环境变量 BILI_DUTY_HOME。"
        )
    picked = _parse_seen(seen_path.read_text(encoding="utf-8-sig"))
    out_meta = _parse_out_dir(home / "out")
    report_meta = _parse_reports(home / "reports")
    cards: list[dict] = []
    for row in picked:
        bvid = row["bvid"]
        fields = _merge(out_meta.get(bvid), report_meta.get(bvid))
        cards.append(_card(home, row, fields))
    cards.sort(key=lambda card: card["id"])
    return cards


def _parse_seen(text: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        bv_at = next((i for i, cell in enumerate(cells) if _BV.fullmatch(cell)), -1)
        if bv_at < 0:
            continue
        day_raw = cells[bv_at - 1] if bv_at > 0 else ""
        day_match = _DATE.search(day_raw)
        if not day_match:
            continue
        status = cells[-1]
        if _SKIPPED.search(status) or not _PICKED.search(status):
            continue
        bvid = cells[bv_at]
        row = {
            "bvid": bvid,
            "day": day_match.group(0),
            "title": cells[bv_at + 1] if bv_at + 1 < len(cells) else "",
            "up": cells[bv_at + 2] if bv_at + 2 < len(cells) else "",
            "status": status,
        }
        prev = latest.get(bvid)
        if prev is None or row["day"] >= prev["day"]:
            latest[bvid] = row
    return list(latest.values())


def _parse_out_dir(out_dir: Path) -> dict[str, dict]:
    found: dict[str, list[tuple[str, dict]]] = {}
    if not out_dir.is_dir():
        return {}
    for path in sorted(out_dir.glob("*.md")):
        day_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.md", path.name)
        file_day = day_match.group(1) if day_match else ""
        text = path.read_text(encoding="utf-8-sig")
        for bvid, fields in _blocks(text).items():
            fields["source"] = f"out/{path.name}"
            found.setdefault(bvid, []).append((file_day, fields))
    chosen: dict[str, dict] = {}
    for bvid, options in found.items():
        dated = [item for item in options if item[0]]
        pool = dated or options
        chosen[bvid] = sorted(pool, key=lambda item: item[0])[-1][1]
    return chosen


def _parse_reports(reports_dir: Path) -> dict[str, dict]:
    chosen: dict[str, dict] = {}
    if not reports_dir.is_dir():
        return chosen
    for path in sorted(reports_dir.glob("BV*.md")):
        bvid = path.name.split("-", 1)[0]
        if not _BV.fullmatch(bvid):
            continue
        fields = _fields(path.read_text(encoding="utf-8-sig"))
        fields["source"] = f"reports/{path.name}"
        chosen[bvid] = fields
    return chosen


def _blocks(text: str) -> dict[str, dict]:
    parts = _BLOCK.split("\n" + text)
    found: dict[str, dict] = {}
    for part in parts:
        match = re.match(r"###\s*(BV[0-9A-Za-z]+)", part.lstrip())
        if not match:
            continue
        bvid = match.group(1)
        if not _BV.fullmatch(bvid):
            continue
        found[bvid] = _fields(part)
    return found


def _fields(text: str) -> dict:
    data = {"title": "", "up": "", "tier": "", "why": "", "comment": "", "play": "", "url": ""}
    mode: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal mode
        if mode in {"why", "comment"} and buf:
            data[mode] = " ".join(buf).strip()
        buf.clear()
        mode = None

    for raw in text.splitlines():
        plain = _plain(raw)
        if not plain:
            flush()
            continue
        if plain.startswith(_STOP) or plain.startswith("#"):
            flush()
            continue
        label, rest = _label(plain)
        if label:
            flush()
            if label in {"why", "comment"}:
                mode = label
                if rest:
                    buf.append(rest)
            elif label == "tier":
                tier = _TIER.search(rest)
                data["tier"] = tier.group(1) if tier else ""
            elif label == "up":
                data["up_line"] = rest
                data["up"] = re.split(r"\s*[·•|｜]\s*", rest)[0].strip()
            else:
                data[label] = rest.strip()
            continue
        if mode in {"why", "comment"}:
            buf.append(plain)
    flush()
    url = _URL.search(text)
    if url:
        data["url"] = url.group(0).rstrip("/")
    up_line = data.get("up_line") or ""
    play = _PLAY.search(up_line)
    if play:
        data["play"] = play.group(1).replace(" ", "")
    data.pop("up_line", None)
    return data


def _plain(raw: str) -> str:
    text = raw.strip()
    if text.startswith("- "):
        text = text[2:].strip()
    return text.replace("**", "").strip()


def _label(plain: str) -> tuple[str | None, str]:
    for label, key in _LABELS:
        if plain.startswith(label):
            return key, plain[len(label):].lstrip("：: \t")
    return None, ""


def _merge(primary: dict | None, fallback: dict | None) -> dict:
    merged = {
        "title": "",
        "up": "",
        "tier": "",
        "why": "",
        "comment": "",
        "play": "",
        "url": "",
        "sources": [],
    }
    for source in (fallback, primary):
        if not source:
            continue
        for key in ("title", "up", "tier", "why", "comment", "play", "url"):
            if source.get(key):
                merged[key] = source[key]
        if source.get("source"):
            merged["sources"].append(source["source"])
    return merged


def _card(home: Path, row: dict, fields: dict) -> dict:
    bvid = row["bvid"]
    title = fields.get("title") or row.get("title") or bvid
    up = fields.get("up") or row.get("up") or ""
    prose = " ".join(part for part in (title, fields.get("why") or "", fields.get("comment") or "") if part)
    seconds, phrase = _duration(prose)
    sources = ["seen.md", *fields.get("sources", [])]
    return {
        "id": bvid,
        "deck": "bili_featured",
        "title": title,
        "bvid": bvid,
        "up": up,
        "duration_seconds": seconds,
        "duration_phrase": phrase,
        "tier": fields.get("tier") or "",
        "why": fields.get("why") or "",
        "comment": fields.get("comment") or "",
        "tags": [],
        "url": fields.get("url") or f"https://www.bilibili.com/video/{bvid}",
        "cover": _local_cover(home, bvid),
        "play": fields.get("play") or "",
        "status": row.get("status") or "挑了",
        "featured_on": row.get("day") or "",
        "sources": sources,
        "watch_variant": watch_variant_for(seconds),
        "enabled": True,
    }


def _duration(text: str) -> tuple[int | None, str | None]:
    match = _DURATION.search(text)
    if not match:
        return None, None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit == "小时":
        seconds = int(round(amount * 3600))
    elif unit == "分半":
        seconds = int(amount) * 60 + 30
    else:
        seconds = int(round(amount * 60))
    return seconds, match.group(0).strip()


def _local_cover(home: Path, bvid: str) -> str | None:
    folder = home / "covers"
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = folder / f"{bvid}{ext}"
        if path.is_file():
            return str(path)
    return None
