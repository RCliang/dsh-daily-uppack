"""先选类型或区，再抽 5 张。"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from chouka.categories import list_categories  # noqa: E402
from chouka.engine import draw_card, mark_result  # noqa: E402
from chouka.errors import ChoukaError  # noqa: E402
from chouka.server import bind_preview_server  # noqa: E402
from support import meal, write_project  # noqa: E402

TZ = timezone(timedelta(hours=8))
FIXTURE = ROOT / "tests" / "fixtures" / "bili"


def now(day: str) -> datetime:
    year, month, date = (int(part) for part in day.split("-"))
    return datetime(year, month, date, 12, 0, tzinfo=TZ)


def light_pool() -> list[dict]:
    items = [meal(f"light-{index}", f"清淡{index}", ["清淡"], 12, 1) for index in range(5)]
    items.append(meal("meat", "红烧肉", ["荤"], 30, 1))
    return items


class PackTests(unittest.TestCase):
    def test_five_lunch_cards_stay_in_the_tag(self):
        box = tempfile.TemporaryDirectory()
        try:
            root = write_project(Path(box.name), light_pool(), FIXTURE)
            result = draw_card(
                {"deck": "lunch", "count": 5, "constraints": {"tag": "清淡"}},
                root=root,
                now=now("2026-11-06"),
                seed=1,
            )
            self.assertEqual(len(result["cards"]), 5)
            self.assertEqual(len({card["id"] for card in result["cards"]}), 5)
            for card in result["cards"]:
                self.assertIn("清淡", card["face"]["tags"])
                self.assertNotEqual(card["id"], "meat")
                self.assertIn("你选了「清淡」", card["reason"])
            with self.assertRaises(ChoukaError) as short:
                draw_card(
                    {"deck": "lunch", "count": 5, "constraints": {"tag": "荤"}},
                    root=root,
                    now=now("2026-11-06"),
                )
            self.assertIn("只有 1 张", str(short.exception))
            with self.assertRaises(ChoukaError) as missing:
                draw_card(
                    {"deck": "lunch", "count": 5, "constraints": {"tag": "没有"}},
                    root=root,
                    now=now("2026-11-06"),
                )
            self.assertIn("没有类型", str(missing.exception))
            chosen = result["cards"][0]["id"]
            with self.assertRaises(ChoukaError):
                mark_result(result["draw_id"], "did", root=root)
            marked = mark_result(result["draw_id"], f"picked:{chosen}", root=root)
            self.assertEqual(marked["picked_id"], chosen)
        finally:
            box.cleanup()

    def test_five_videos_stay_in_the_zone(self):
        box = tempfile.TemporaryDirectory()
        try:
            root = write_project(Path(box.name), light_pool(), FIXTURE)
            (root / "data" / "bili_zones.json").write_text(
                json.dumps(
                    {
                        "zones": [
                            {"id": "mix", "name": "样例区", "keywords": ["流程", "课", "手机", "画图", "标题", "时长"]},
                            {"id": "handset", "name": "手机", "keywords": ["手机"]},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            listed = list_categories("bili_featured", root=root)
            by_id = {item["id"]: item for item in listed["categories"]}
            self.assertTrue(by_id["mix"]["ready"])
            self.assertFalse(by_id["handset"]["ready"])
            self.assertEqual(by_id["handset"]["count"], 1)
            result = draw_card(
                {"deck": "bili_featured", "count": 5, "constraints": {"zone": "mix"}},
                root=root,
                now=now("2026-11-06"),
                seed=2,
            )
            self.assertEqual(len(result["cards"]), 5)
            for card in result["cards"]:
                self.assertIn("mix", card["face"]["zones"])
                self.assertNotEqual(card["id"], "BV1X8oKBLEdj")
                self.assertIn("样例区", card["reason"])
            phone = draw_card(
                {"deck": "bili_featured", "count": 1, "constraints": {"zone": "handset"}},
                root=root,
                now=now("2026-11-06"),
                seed=3,
            )
            self.assertEqual(phone["cards"][0]["id"], "BV1HJno6EEDT")
            with self.assertRaises(ChoukaError) as unknown:
                draw_card(
                    {"deck": "bili_featured", "count": 1, "constraints": {"zone": "missing"}},
                    root=root,
                    now=now("2026-11-06"),
                )
            self.assertIn("没有这个区", str(unknown.exception))
        finally:
            box.cleanup()

    def test_preview_server_asks_then_draws_five(self):
        box = tempfile.TemporaryDirectory()
        httpd = None
        try:
            root = write_project(Path(box.name), light_pool(), FIXTURE)
            httpd = bind_preview_server(root, 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            status, listed = _get(base + "/api/categories?deck=lunch")
            self.assertEqual(status, 200)
            ready = {item["id"]: item["ready"] for item in listed["categories"]}
            self.assertTrue(ready["清淡"])
            self.assertFalse(ready["荤"])
            drawn = _post(base + "/api/draw", {"deck": "lunch", "category": "清淡"})
            self.assertEqual(len(drawn["cards"]), 5)
            self.assertTrue(all("清淡" in " ".join(card["lines"]) for card in drawn["cards"]))
            self.assertTrue(drawn["draw_id"])
            with self.assertRaises(urllib.error.HTTPError) as blocked:
                _post(base + "/api/draw", {"deck": "lunch", "category": "荤"})
            body = json.loads(blocked.exception.read().decode("utf-8"))
            self.assertIn("只有 1 张", body["error"])
        finally:
            if httpd is not None:
                httpd.shutdown()
                httpd.server_close()
            box.cleanup()


def _get(url: str) -> tuple[int, dict]:
    last: Exception | None = None
    for _ in range(20):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status, json.load(response)
        except urllib.error.URLError as exc:
            last = exc
            time.sleep(0.05)
    raise AssertionError(last)


class PreviewCardTests(unittest.TestCase):
    def test_card_text_is_capped_and_video_keeps_its_link(self):
        from chouka.preview import payload_from_draw

        payload = payload_from_draw(
            {
                "deck": "bili_featured",
                "cards": [
                    {
                        "id": "BV1TEST",
                        "title": "很长的标题" * 12,
                        "reason": "很长的理由" * 30,
                        "face": {
                            "url": "https://www.bilibili.com/video/BV1TEST",
                            "tier": "值得看",
                            "up": "某人",
                        },
                    }
                ],
            }
        )
        card = payload["cards"][0]
        self.assertLessEqual(len(card["title"]), 32)
        self.assertLessEqual(len(card["reason"]), 72)
        self.assertTrue(card["title"].endswith("…"))
        self.assertTrue(card["reason"].endswith("…"))
        self.assertEqual(card["url"], "https://www.bilibili.com/video/BV1TEST")


def _post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)
