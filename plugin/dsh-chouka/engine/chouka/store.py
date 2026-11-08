"""抽取记录。JSONL，一条抽取一行。"""

from __future__ import annotations

import json
from pathlib import Path

from chouka.errors import ChoukaError


def load_draws(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    text = path.read_text(encoding="utf-8-sig")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ChoukaError(f"{path} 第 {lineno} 行不是合法 JSON: {exc}") from exc
        if not isinstance(item, dict) or "draw_id" not in item:
            raise ChoukaError(f"{path} 第 {lineno} 行缺少 draw_id")
        rows.append(item)
    return rows


def write_draws(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)
    _atomic_write(path, body)


def append_draw(path: Path, record: dict) -> None:
    rows = load_draws(path)
    rows.append(record)
    write_draws(path, rows)


def update_draw(path: Path, draw_id: str, mutate) -> dict:
    rows = load_draws(path)
    for index, row in enumerate(rows):
        if row.get("draw_id") == draw_id:
            updated = mutate(row)
            rows[index] = updated
            write_draws(path, rows)
            return updated
    raise ChoukaError(f"没有这条抽取记录: {draw_id}")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    # write_text() 的 newline 参数要 3.10；用 open() 让 3.7 也能跑
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    tmp.replace(path)
