"""精选适配：夹具按 dsh-bili-scroll 的真实写法，另读本机 bili-duty（在的话）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chouka.bili_adapter import load_featured  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "bili"


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.cards = {card["id"]: card for card in load_featured(FIXTURE)}

    def test_picked_rows_only(self):
        self.assertNotIn("BV1X8oKBLEdj", self.cards)
        self.assertIn("BV1HJno6EEDT", self.cards)
        self.assertIn("BV1LONGVIDEO", self.cards)

    def test_duration_ignores_footer_and_marks_long_videos(self):
        self.assertEqual(self.cards["BV1HJno6EEDT"]["duration_seconds"], 90)
        self.assertEqual(self.cards["BV1HJno6EEDT"]["duration_phrase"], "1 分半")
        self.assertEqual(self.cards["BV1DTnS6VESr"]["duration_seconds"], 210)
        self.assertIsNone(self.cards["BV1FOOTER001"]["duration_seconds"])
        self.assertIsNone(self.cards["BV154426xEha"]["duration_seconds"])
        long = self.cards["BV1LONGVIDEO"]
        self.assertEqual(long["duration_seconds"], 70 * 60)
        self.assertEqual(long["watch_variant"], "first_3_min")
        self.assertIsNone(self.cards["BV1HJno6EEDT"]["watch_variant"])

    def test_fields_from_daily_report(self):
        phone = self.cards["BV1HJno6EEDT"]
        self.assertEqual(phone["title"], "手机")
        self.assertEqual(phone["up"], "兔子Jarvis")
        self.assertEqual(phone["tier"], "可以看")
        self.assertIn("1 分半", phone["why"])
        self.assertIn("瓶颈", phone["comment"])
        self.assertEqual(phone["play"], "1613")
        self.assertEqual(phone["url"], "https://www.bilibili.com/video/BV1HJno6EEDT")
        self.assertEqual(phone["featured_on"], "2026-10-27")
        self.assertEqual(phone["tags"], [])
        self.assertIsNone(phone["cover"])
        self.assertIn("seen.md", phone["sources"])
        self.assertTrue(any(source.startswith("out/") for source in phone["sources"]))
        workshop = self.cards["BV154426xEha"]
        self.assertEqual(workshop["tier"], "值得看")
        self.assertEqual(workshop["up"], "马克的技术工作坊")
        self.assertIn("值得抄", workshop["comment"])
        self.assertEqual(workshop["play"], "32.8万")

    def test_report_file_fills_missing_why(self):
        card = self.cards["BV1REPORT001"]
        self.assertIn("5 分钟", card["why"])
        self.assertEqual(card["duration_seconds"], 300)
        self.assertEqual(card["tier"], "可以看")
        self.assertTrue(any(source.startswith("reports/") for source in card["sources"]))

    def test_local_cover_file_is_used_when_present(self):
        cover = FIXTURE / "covers" / "BV1HJno6EEDT.jpg"
        cover.parent.mkdir(exist_ok=True)
        cover.write_bytes(b"not-a-real-image")
        try:
            cards = {card["id"]: card for card in load_featured(FIXTURE)}
            self.assertEqual(cards["BV1HJno6EEDT"]["cover"], str(cover))
            self.assertIsNone(cards["BV1DTnS6VESr"]["cover"])
        finally:
            cover.unlink()
            cover.parent.rmdir()

    def test_missing_seen_explains_where_to_point(self):
        from chouka.errors import ChoukaError

        with self.assertRaises(ChoukaError) as caught:
            load_featured(FIXTURE / "missing")
        self.assertIn("seen.md", str(caught.exception))


class LiveBiliTests(unittest.TestCase):
    def test_real_duty_home_when_present(self):
        home = Path.home() / ".dsh" / "bili-duty"
        if not (home / "seen.md").is_file():
            self.skipTest("这台机器没有 bili-duty 判重表")
        cards = {card["id"]: card for card in load_featured(home)}
        self.assertGreaterEqual(len(cards), 1)
        self.assertNotIn("BV1X8oKBLEdj", cards)
        for card in cards.values():
            self.assertTrue(card["bvid"].startswith("BV"))
            self.assertTrue(card["title"])
            self.assertTrue(card["url"].startswith("https://www.bilibili.com/video/"))
            self.assertEqual(card["tags"], [])
            self.assertIsNone(card["cover"])
            self.assertIn("seen.md", card["sources"])
        phone = cards.get("BV1HJno6EEDT")
        if phone:
            self.assertEqual(phone["duration_seconds"], 90)
            self.assertEqual(phone["up"], "兔子Jarvis")
            self.assertEqual(phone["tier"], "可以看")
            self.assertIn("1 分半", phone["why"])
        drawing = cards.get("BV1DTnS6VESr")
        if drawing:
            self.assertEqual(drawing["duration_seconds"], 210)
            self.assertNotEqual(drawing["duration_seconds"], 3 * 3600)
        tutorial = cards.get("BV1sZMq6qEko")
        if tutorial:
            self.assertIsNone(tutorial["duration_seconds"])
        review = cards.get("BV1PznU6YEZE")
        if review:
            self.assertEqual(review["tier"], "值得看")
            self.assertIn("马克", review["up"])
            self.assertTrue(review["why"])


if __name__ == "__main__":
    unittest.main()
