"""抽取、标记，以及标记之后的下一次权重。"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from chouka.engine import draw_card, mark_result  # noqa: E402
from chouka.errors import ChoukaError  # noqa: E402
from chouka.lunch import load_lunch  # noqa: E402
from chouka.reasons import bili_reason, lunch_reason  # noqa: E402
from chouka.rules import is_light, is_meat  # noqa: E402
from chouka.store import load_draws, write_draws  # noqa: E402
from support import meal, write_project  # noqa: E402

TZ = timezone(timedelta(hours=8))
FIXTURE = ROOT / "tests" / "fixtures" / "bili"


def now(day: str, hour: int = 12) -> datetime:
    year, month, date = (int(part) for part in day.split("-"))
    return datetime(year, month, date, hour, 0, tzinfo=TZ)


class SampleFileTests(unittest.TestCase):
    def test_lunch_file_is_user_maintained_examples(self):
        cards = load_lunch(ROOT / "data" / "lunch.json")
        self.assertGreaterEqual(len(cards), 11)
        enabled = [card for card in cards if card["enabled"]]
        self.assertGreaterEqual(sum("清淡" in card["tags"] for card in enabled), 5)
        self.assertGreaterEqual(sum("荤" in card["tags"] for card in enabled), 5)
        for card in cards:
            for key in ("id", "name", "tags", "notes", "budget", "walk_minutes", "enabled"):
                self.assertIn(key, card)
            self.assertTrue(card["notes"].startswith("示例"))
        self.assertTrue(any(is_meat(card["tags"]) for card in cards))
        self.assertTrue(any(is_light(card["tags"]) for card in cards))
        self.assertTrue(any(card["walk_minutes"] == 0 for card in cards))
        spoken = lunch_reason(
            {"title": "面", "tags": ["清淡"], "notes": "示例：别念出来", "budget": 1, "walk_minutes": 0},
            {},
        )
        self.assertNotIn("示例", spoken)
        penalized = lunch_reason(
            {"title": "沙拉", "tags": ["清淡"], "notes": "示例", "budget": 1, "walk_minutes": 1},
            {"did_count": 1, "in_last_draw": True},
        )
        self.assertIn("压低", penalized)
        self.assertNotIn("更靠前", penalized)
        ahead = lunch_reason(
            {"title": "沙拉", "tags": ["清淡"], "notes": "示例", "budget": 1, "walk_minutes": 1},
            {"did_count": 1, "in_last_draw": False},
        )
        self.assertIn("更靠前", ahead)
        video = bili_reason(
            {
                "title": "画图",
                "up": "也无风雨也雾晴",
                "comment": "更像产品更新公告，信息密度一般。",
                "why": "3 分半的工具更新速览。",
                "tier": "可以看",
                "featured_on": "2026-10-27",
                "duration_phrase": "3 分半",
                "duration_seconds": 210,
            },
            {},
        )
        self.assertNotIn("。。", video)
        self.assertIn("3 分半", video)
        again = bili_reason(
            {"title": "画图", "up": "某人", "why": "短", "comment": "", "tier": "", "duration_seconds": None},
            {"in_last_draw": True},
        )
        self.assertIn("刚被抽过", again)


class DrawTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.root = write_project(
            Path(self.tmp.name),
            [
                meal("noodle", "番茄鸡蛋面", ["清淡", "面"], 18, 5),
                meal("veg", "时蔬盖饭", ["清淡", "蔬菜"], 22, 8),
                meal("soup", "豆腐汤", ["清淡", "素"], 16, 0),
                meal("beef", "牛肉面", ["荤"], 32, 10),
                meal("spicy", "麻辣香锅", ["荤", "重口"], 40, 15, enabled=False),
            ],
            FIXTURE,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_draw_one_writes_reason_and_record(self):
        result = draw_card({"deck": "lunch", "count": 1}, root=self.root, now=now("2026-11-06"), seed=2)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["draw_id"].startswith("d"))
        self.assertIn("抽到", result["cards"][0]["reason"])
        self.assertNotEqual(result["cards"][0]["id"], "spicy")
        saved = load_draws(self.root / "data" / "draws.jsonl")
        self.assertEqual(saved[0]["draw_id"], result["draw_id"])
        self.assertIsNone(saved[0]["result"])

    def test_same_seed_is_stable_and_count_three_is_distinct(self):
        import tempfile

        other = tempfile.TemporaryDirectory()
        try:
            second = write_project(Path(other.name), json.loads((self.root / "data" / "lunch.json").read_text(encoding="utf-8"))["items"], FIXTURE)
            one = draw_card({"deck": "lunch", "count": 3}, root=self.root, now=now("2026-11-06"), seed=7)
            two = draw_card({"deck": "lunch", "count": 3}, root=second, now=now("2026-11-06"), seed=7)
        finally:
            other.cleanup()
        self.assertEqual([card["id"] for card in one["cards"]], [card["id"] for card in two["cards"]])
        self.assertEqual(len({card["id"] for card in one["cards"]}), 3)

    def test_constraints_and_bad_count(self):
        cheap = draw_card(
            {"deck": "lunch", "count": 1, "constraints": {"budget": 20}},
            root=self.root,
            now=now("2026-11-06"),
            seed=1,
        )
        self.assertIn(cheap["cards"][0]["id"], {"noodle", "soup"})
        stay = draw_card(
            {"deck": "lunch", "count": 1, "constraints": {"want_walk": False, "avoid_yesterday": False}},
            root=self.root,
            now=now("2026-11-06"),
            seed=1,
        )
        self.assertEqual(stay["cards"][0]["id"], "soup")
        with self.assertRaises(ChoukaError):
            draw_card({"deck": "lunch", "count": 2}, root=self.root)

    def test_avoid_yesterday(self):
        first = draw_card({"deck": "lunch", "count": 1}, root=self.root, now=now("2026-11-05"), seed=3)
        second = draw_card({"deck": "lunch", "count": 1}, root=self.root, now=now("2026-11-06"), seed=3)
        self.assertNotEqual(second["cards"][0]["id"], first["cards"][0]["id"])
        self.assertIn(first["cards"][0]["title"], second["cards"][0]["reason"])

    def test_mark_did_changes_next_weight(self):
        first = draw_card(
            {"deck": "lunch", "count": 1, "constraints": {"avoid_yesterday": False}},
            root=self.root,
            now=now("2026-11-05"),
            seed=1,
        )
        card_id = first["cards"][0]["id"]
        plain = first["weights"][card_id]
        mark_result(first["draw_id"], "did", root=self.root, now=now("2026-11-05", 13))
        second = draw_card(
            {"deck": "lunch", "count": 1, "constraints": {"avoid_yesterday": False}},
            root=self.root,
            now=now("2026-11-06"),
            seed=1,
        )
        self.assertGreater(second["weights"][card_id], plain * 0.25)
        self.assertAlmostEqual(second["weights"][card_id], (1 + 0.8) * 0.25)
        untouched = next(key for key, value in second["weights"].items() if key != card_id and value == 1)
        self.assertGreater(untouched and second["weights"][card_id], 0)
        self.assertLess(second["weights"][card_id], second["weights"][untouched])

    def test_two_skips_chill_the_card(self):
        import tempfile

        box = tempfile.TemporaryDirectory()
        try:
            root = write_project(
                Path(box.name),
                [meal("only", "唯一", ["荤"], 10, 1), meal("other", "另一份", ["清淡"], 10, 1)],
                FIXTURE,
            )
            write_draws(
                root / "data" / "draws.jsonl",
                [
                    {
                        "draw_id": "s1",
                        "deck": "lunch",
                        "count": 1,
                        "drawn_at": "2026-11-04T12:00:00+08:00",
                        "cards": [{"id": "only", "title": "唯一", "face": {"tags": ["荤"]}}],
                        "result": "skipped",
                        "picked_id": None,
                    },
                    {
                        "draw_id": "s2",
                        "deck": "lunch",
                        "count": 1,
                        "drawn_at": "2026-11-05T12:00:00+08:00",
                        "cards": [{"id": "only", "title": "唯一", "face": {"tags": ["荤"]}}],
                        "result": "skipped",
                        "picked_id": None,
                    },
                ],
            )
            result = draw_card(
                {"deck": "lunch", "count": 1, "constraints": {"avoid_yesterday": False}},
                root=root,
                now=now("2026-11-05", 18),
                seed=0,
            )
            self.assertEqual(result["cards"][0]["id"], "other")
            self.assertEqual(result["weights"]["only"], 0)
        finally:
            box.cleanup()

    def test_lunch_pity_weights_on_draw(self):
        write_draws(
            self.root / "data" / "draws.jsonl",
            [
                _did("2026-11-04", "beef", ["荤"], "牛肉面"),
                _did("2026-11-05", "beef", ["荤"], "牛肉面"),
            ],
        )
        result = draw_card({"deck": "lunch", "count": 1}, root=self.root, now=now("2026-11-06"), seed=0)
        self.assertTrue(result["pity"]["applied"])
        self.assertEqual(result["pity"]["rule"], "lunch_light")
        self.assertEqual(result["weights"]["veg"], 4.0)
        self.assertEqual(result["weights"]["noodle"], 4.0)
        self.assertEqual(result["weights"]["soup"], 4.0)
        self.assertNotIn("spicy", result["weights"])

    def test_picked_then_did_on_three_cards(self):
        result = draw_card({"deck": "lunch", "count": 3}, root=self.root, now=now("2026-11-06"), seed=4)
        chosen = result["cards"][1]["id"]
        with self.assertRaises(ChoukaError):
            mark_result(result["draw_id"], "did", root=self.root)
        marked = mark_result(result["draw_id"], f"picked:{chosen}", root=self.root, now=now("2026-11-06", 13))
        self.assertEqual(marked["result"], "picked")
        self.assertEqual(marked["picked_id"], chosen)
        did = mark_result(result["draw_id"], "did", root=self.root, now=now("2026-11-06", 14))
        self.assertEqual(did["result"], "did")
        self.assertEqual(did["picked_id"], chosen)
        with self.assertRaises(ChoukaError):
            mark_result(result["draw_id"], "picked:missing", root=self.root)

    def test_bili_draw_prints_fields_via_api_and_pity(self):
        result = draw_card({"deck": "bili_featured", "count": 1}, root=self.root, now=now("2026-11-06"), seed=1)
        face = result["cards"][0]["face"]
        self.assertTrue(face["title"])
        self.assertTrue(face["up"])
        self.assertIn("featured_on", face)
        self.assertTrue(result["cards"][0]["reason"])
        write_draws(
            self.root / "data" / "draws.jsonl",
            [
                {
                    "draw_id": f"b{day}",
                    "deck": "bili_featured",
                    "count": 1,
                    "drawn_at": f"{day}T21:00:00+08:00",
                    "cards": [{"id": "BV1LONGVIDEO", "title": "很长的课", "face": {"tags": [], "duration_seconds": 4200}}],
                    "result": None,
                    "picked_id": None,
                }
                for day in ("2026-11-03", "2026-11-04", "2026-11-05")
            ],
        )
        pity = draw_card({"deck": "bili_featured", "count": 1}, root=self.root, now=now("2026-11-06"), seed=9)
        self.assertTrue(pity["pity"]["applied"])
        self.assertLessEqual(pity["cards"][0]["face"]["duration_seconds"], 8 * 60)
        self.assertNotEqual(pity["cards"][0]["id"], "BV1LONGVIDEO")


def _did(day: str, card_id: str, tags: list[str], title: str) -> dict:
    return {
        "draw_id": f"h-{day}",
        "deck": "lunch",
        "count": 1,
        "drawn_at": f"{day}T12:00:00+08:00",
        "cards": [{"id": card_id, "title": title, "face": {"tags": tags}}],
        "result": "did",
        "picked_id": None,
    }


class LunchFileErrorTests(unittest.TestCase):
    def test_missing_field_names_the_file(self):
        import tempfile

        box = tempfile.TemporaryDirectory()
        try:
            path = Path(box.name) / "lunch.json"
            path.write_text(json.dumps([{"id": "x", "name": "y"}]), encoding="utf-8")
            with self.assertRaises(ChoukaError) as caught:
                load_lunch(path)
            self.assertIn("tags", str(caught.exception))
        finally:
            box.cleanup()


if __name__ == "__main__":
    unittest.main()
