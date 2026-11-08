"""薄命令行。不提问，失败时用退出码 1。"""

from __future__ import annotations

import argparse
import json
import sys

from chouka.categories import list_categories
from chouka.engine import draw_card, mark_result
from chouka.errors import ChoukaError
from chouka.paths import load_paths
from chouka.preview import update_preview_file
from chouka.server import serve_preview
from chouka.store import load_draws


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "draw":
            result = draw_card(_request(args), seed=args.seed)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                _print_draw(result)
            return 0
        if args.command == "mark":
            updated = mark_result(args.draw_id, args.result)
            if args.json:
                print(json.dumps(updated, ensure_ascii=False, indent=2))
            else:
                picked = f"  选中: {updated.get('picked_id')}" if updated.get("picked_id") else ""
                print(f"已标记 {updated['draw_id']} → {updated['result']}{picked}")
            return 0
        if args.command == "categories":
            listed = list_categories(args.deck)
            if args.json:
                print(json.dumps(listed, ensure_ascii=False, indent=2))
            else:
                _print_categories(listed)
            return 0
        if args.command == "preview":
            if args.file:
                _print_preview_file()
                return 0
            serve_preview(port=args.port)
            return 0
    except ChoukaError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    parser.error(f"未知命令: {args.command}")
    return 2


def _request(args) -> dict:
    constraints: dict = {}
    if args.deck == "lunch":
        if args.max_minutes is not None or args.tier:
            raise ChoukaError("时长和档位约束只用于 bili_featured")
        if args.zone:
            raise ChoukaError("视频区只用于 bili_featured")
        if args.budget is not None:
            constraints["budget"] = args.budget
        if args.walk == "yes":
            constraints["want_walk"] = True
        elif args.walk == "no":
            constraints["want_walk"] = False
        if args.allow_yesterday:
            constraints["avoid_yesterday"] = False
        if args.tag:
            constraints["tag"] = args.tag
    else:
        if args.budget is not None or args.walk or args.allow_yesterday or args.tag:
            raise ChoukaError("预算、走路、昨天、类型这些约束只用于 lunch")
        if args.max_minutes is not None:
            constraints["max_duration_seconds"] = args.max_minutes * 60
        if args.tier:
            constraints["tier"] = args.tier
        if args.zone:
            constraints["zone"] = args.zone
    return {"deck": args.deck, "count": args.count, "constraints": constraints}


def _print_draw(result: dict) -> None:
    print(f"draw_id: {result['draw_id']}")
    label = "午饭" if result["deck"] == "lunch" else "精选视频"
    print(f"{label}  抽 {result['count']} 张")
    constraints = result.get("constraints") or {}
    if constraints.get("tag"):
        print(f"类型: {constraints['tag']}")
    if constraints.get("zone_name") or constraints.get("zone"):
        print(f"区: {constraints.get('zone_name') or constraints['zone']}")
    if result["pity"]["applied"]:
        print(f"保底: {result['pity']['detail']}")
    for index, card in enumerate(result["cards"], start=1):
        face = card["face"]
        print(f"\n[{index}] {card['title']}")
        if result["deck"] == "bili_featured":
            print(f"    UP: {face.get('up') or '未知'}")
            print(f"    时长: {face.get('duration_phrase') or '未知'}")
            print(f"    精选: {face.get('tier') or '未标档位'}")
            print(f"    精选原因: {face.get('why') or '（日报里没有写为什么值得）'}")
            if card.get("watch_variant") == "first_3_min":
                print("    变体: 只看前 3 分钟（仅标记，不会播放）")
            if face.get("url"):
                print(f"    链接: {face['url']}")
        else:
            print(f"    预算: {face.get('budget')}  步行: {face.get('walk_minutes')} 分钟")
            print(f"    标签: {'、'.join(face.get('tags') or [])}")
        print(f"    为什么抽给你: {card['reason']}")
    print("\n已写入抽取记录。")
    if result.get("preview"):
        print(f"预览页: {result['preview']}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m chouka",
        description="本地抽卡。同一套规则，午饭和精选视频两副牌。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    draw = sub.add_parser("draw", help="抽 1 张、3 张，或开一包 5 张")
    draw.add_argument("deck", choices=["lunch", "bili_featured"])
    draw.add_argument("--count", type=int, default=1, choices=[1, 3, 5])
    draw.add_argument("--tag", default=None, help="午饭类型，对应 tags 里的一项")
    draw.add_argument("--zone", default=None, help="精选视频的区 id，见 categories")
    draw.add_argument("--budget", type=int, default=None, help="午饭预算上限")
    draw.add_argument("--walk", choices=["yes", "no"], default=None, help="午饭是否想走路")
    draw.add_argument("--allow-yesterday", action="store_true", help="午饭允许和昨天重复")
    draw.add_argument("--max-minutes", type=int, default=None, help="精选时长上限（分钟）")
    draw.add_argument("--tier", choices=["值得看", "可以看", "不值当"], default=None)
    draw.add_argument("--seed", type=int, default=None)
    draw.add_argument("--json", action="store_true")

    categories = sub.add_parser("categories", help="列出午饭类型或视频区，以及够不够开一包")
    categories.add_argument("deck", choices=["lunch", "bili_featured"])
    categories.add_argument("--json", action="store_true")

    mark = sub.add_parser("mark", help="标记 did、skipped 或 picked:<id>")
    mark.add_argument("draw_id")
    mark.add_argument("result", help="did、skipped 或 picked:<卡片 id>")
    mark.add_argument("--json", action="store_true")

    preview = sub.add_parser("preview", help="启动选类型再开包的页面")
    preview.add_argument("--port", type=int, default=8765)
    preview.add_argument("--file", action="store_true", help="只打印预览文件路径，不启动页面")
    return parser


def _print_categories(listed: dict) -> None:
    title = "午饭类型" if listed["deck"] == "lunch" else "视频区"
    print(f"{title}  一包 {listed['pack_size']} 张")
    if not listed["categories"]:
        print("还没有可选项。")
        return
    for item in listed["categories"]:
        state = "可以开包" if item["ready"] else f"还差 {item['short']} 张"
        print(f"  {item['name']}  {item['count']} 张  {state}")


def _print_preview_file() -> None:
    paths = load_paths()
    rows = load_draws(paths.draws)
    if rows and paths.preview_html.is_file():
        update_preview_file(paths.preview_html, rows[-1])
        print(f"预览页已写入最近一次抽取 {rows[-1]['draw_id']}")
    elif not rows:
        print("还没有抽取记录，预览页打开后是内置示例。")
    print(paths.preview_html)


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
