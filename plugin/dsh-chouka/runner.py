"""dsh-chouka 的进程边界：一行 JSON 进，一行 JSON 出。

只转发调用，不复制任何规则 —— 抽卡、保底、权重、卡池全在引擎里。
两种引擎布局，由环境变量决定：

  发布模式（默认）：
    CHOUKA_ENGINE_DIR = <插件>/engine     引擎代码随插件包走
    CHOUKA_ROOT       = ~/.dsh/chouka     用户数据（config/paths.json + data/*）
    首次运行自动播种：config/paths.json、data/lunch.json、data/bili_zones.json
                      （从 <CHOUKA_ENGINE_DIR>/defaults 拷示例）

  开发模式（宿主传入仓库路径时）：
    CHOUKA_ENGINE_DIR = <仓库根>          直接用仓库里的 chouka/
    CHOUKA_ROOT       = <仓库根>          数据也留在仓库 data/

用法：
    python runner.py '{"op":"draw","deck":"lunch","count":1,"constraints":{...}}'
    python runner.py '{"op":"mark","draw_id":"...","result":"did"}'
    python runner.py '{"op":"categories","deck":"lunch"}'
    python runner.py '{"op":"pack","deck":"lunch","category":"清淡"}'
    python runner.py '{"op":"add_lunch","name":"...","tags":["清淡"],...}'
"""

import hashlib
import json
import os
import shutil
import sys


def _setup() -> str:
    """定位引擎与数据根：返回 CHOUKA_ROOT。"""
    engine_dir = os.environ.get("CHOUKA_ENGINE_DIR") or os.getcwd()
    sys.path.insert(0, engine_dir)

    root = os.environ.get("CHOUKA_ROOT") or engine_dir
    both_dirs = os.path.isdir(engine_dir) and os.path.isdir(root)
    if both_dirs and os.path.samefile(engine_dir, root):
        return root  # 开发模式：仓库自带数据，不播种

    # 发布模式：数据根第一次用要播种
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    cfg_path = os.path.join(root, "config", "paths.json")
    if not os.path.exists(cfg_path):
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "lunch_pool": "data/lunch.json",
                "draws": "data/draws.jsonl",
                "bili_zones": "data/bili_zones.json",
                "bili_home": None,
            }, f, ensure_ascii=False, indent=2)
    defaults = os.path.join(engine_dir, "defaults")
    if os.path.isdir(defaults):
        for name in ("lunch.json", "bili_zones.json"):
            dst = os.path.join(root, "data", name)
            if not os.path.exists(dst):
                shutil.copyfile(os.path.join(defaults, name), dst)
    return root


_ROOT = _setup()

from chouka import draw_card, mark_result  # noqa: E402  (引擎路径在上面已插入)
from chouka.categories import list_categories  # noqa: E402
from chouka.lunch import load_lunch  # noqa: E402
from chouka.paths import load_paths  # noqa: E402
from chouka.preview import payload_from_draw  # noqa: E402


def _read_pool(paths):
    raw = json.loads(paths.lunch_pool.read_text(encoding="utf-8-sig"))
    items = raw["items"] if isinstance(raw, dict) else raw
    return raw, items


def _write_pool(paths, raw, items):
    out = {"readme": raw.get("readme"), "items": items} if isinstance(raw, dict) else items
    paths.lunch_pool.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_lunch(paths.lunch_pool)  # 校验：格式不对立刻抛错（文件已写，但能被人看到并修）


def _card_of(req: dict, tags: list) -> dict:
    name = str(req.get("name") or "").strip()
    if not name:
        raise ValueError("name 不能为空")
    return {
        "id": "nearby-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8],
        "name": name,
        "tags": [str(t) for t in tags if str(t).strip()],
        "notes": str(req.get("notes") or ""),
        "budget": int(req.get("budget") or 25),
        "walk_minutes": int(req.get("walk_minutes") or 10),
        "enabled": True,
    }


def _add_lunch(req: dict) -> dict:
    """把一条附近候选写进午饭卡池（路径走 config/paths.json，写入后用 load_lunch 校验）。"""
    tags = req.get("tags") or []
    paths = load_paths(_ROOT)
    raw, items = _read_pool(paths)
    card = _card_of(req, tags)
    if any(str(item.get("name")) == card["name"] for item in items):
        raise ValueError(f"卡池里已有「{card['name']}」")
    items.append(card)
    _write_pool(paths, raw, items)
    return card


def _add_lunch_batch(req: dict) -> dict:
    """批量入池：同名跳过，一次写入一次校验。返回 {added, existed}。"""
    items_in = req.get("items") or []
    tags = req.get("tags") or []
    paths = load_paths(_ROOT)
    raw, items = _read_pool(paths)
    known = {str(item.get("name")) for item in items}
    added, existed = [], []
    for one in items_in:
        try:
            card = _card_of(one, tags)
        except ValueError:
            continue
        if card["name"] in known:
            existed.append(card["name"])
            continue
        items.append(card)
        known.add(card["name"])
        added.append({"id": card["id"], "name": card["name"]})
    if added:
        _write_pool(paths, raw, items)
    return {"added": added, "existed": existed}


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    try:
        req = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"请求不是合法 JSON: {exc}"}, ensure_ascii=False))
        return 1
    op = req.get("op")
    try:
        if op == "draw":
            data = draw_card({
                "deck": req.get("deck"),
                "count": req.get("count", 1),
                "constraints": req.get("constraints"),
            })
        elif op == "mark":
            data = mark_result(str(req.get("draw_id") or ""), str(req.get("result") or ""))
        elif op == "categories":
            data = list_categories(str(req.get("deck") or ""))
        elif op == "pack":
            # 开一包：抽 5 张（category 按牌的类型转成 tag/zone 约束），
            # 再用引擎自己的 payload_from_draw 映射成 preview 卡面格式
            deck = str(req.get("deck") or "")
            category = str(req.get("category") or "")
            constraints = {("tag" if deck == "lunch" else "zone"): category} if category else {}
            if deck == "lunch" and req.get("avoid_yesterday") is not None:
                # avoid_yesterday 是午饭专属约束；精选视频的约束白名单里没有它
                constraints["avoid_yesterday"] = bool(req.get("avoid_yesterday"))
            record = draw_card({"deck": deck, "count": 5, "constraints": constraints})
            data = {"record": record, "payload": payload_from_draw(record)}
        elif op == "add_lunch":
            data = _add_lunch(req)
        elif op == "add_lunch_batch":
            data = _add_lunch_batch(req)
        else:
            print(json.dumps({"ok": False, "error": "op 只能是 draw / mark / categories / pack / add_lunch / add_lunch_batch"}, ensure_ascii=False))
            return 1
    except Exception as exc:  # ChoukaError 与一切意外都按同一种形状返回
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
