"""所有数据路径都从这里走。业务代码不另写死目录。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from chouka.errors import ChoukaError


@dataclass(frozen=True)
class Paths:
    root: Path
    lunch_pool: Path
    draws: Path
    bili_zones: Path
    bili_home: Path
    preview_html: Path


def project_root() -> Path:
    env = os.environ.get("CHOUKA_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def load_paths(root: Path | None = None) -> Paths:
    root = Path(root).resolve() if root is not None else project_root()
    cfg_path = root / "config" / "paths.json"
    cfg: dict = {}
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ChoukaError(f"无法解析 {cfg_path}: {exc}") from exc
        if not isinstance(cfg, dict):
            raise ChoukaError(f"{cfg_path} 必须是 JSON 对象")

    lunch_pool = _resolve(root, cfg.get("lunch_pool") or "data/lunch.json")
    draws = _resolve(root, cfg.get("draws") or "data/draws.jsonl")
    bili_zones = _resolve(root, cfg.get("bili_zones") or "data/bili_zones.json")
    bili_home = _bili_home(root, cfg.get("bili_home"))
    return Paths(
        root=root,
        lunch_pool=lunch_pool,
        draws=draws,
        bili_zones=bili_zones,
        bili_home=bili_home,
        preview_html=root / "preview" / "index.html",
    )


def _resolve(root: Path, raw: object) -> Path:
    path = Path(str(raw))
    if not path.is_absolute():
        path = root / path
    return path


def _bili_home(root: Path, configured: object) -> Path:
    if isinstance(configured, str) and configured.strip():
        return _resolve(root, configured.strip())
    env = os.environ.get("BILI_DUTY_HOME")
    if env and env.strip():
        return Path(env.strip())
    return Path.home() / ".dsh" / "bili-duty"
