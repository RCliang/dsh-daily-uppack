"""命令行：午饭、精选、标记。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from support import meal, write_project  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "bili"


class CliTests(unittest.TestCase):
    def test_draw_lunch_bili_and_mark(self):
        box = tempfile.TemporaryDirectory()
        try:
            root = write_project(
                Path(box.name),
                [
                    meal("noodle", "番茄鸡蛋面", ["清淡", "面"], 18, 5),
                    meal("beef", "牛肉面", ["荤"], 32, 10),
                    meal("soup", "豆腐汤", ["清淡", "素"], 16, 0),
                    meal("veg", "时蔬盖饭", ["清淡", "蔬菜"], 22, 8),
                ],
                FIXTURE,
            )
            lunch = self.run(root, "draw", "lunch", "--count", "1", "--seed", "1")
            self.assertEqual(lunch.returncode, 0, lunch.stderr)
            self.assertIn("draw_id:", lunch.stdout)
            self.assertIn("为什么抽给你:", lunch.stdout)
            self.assertTrue(any(name in lunch.stdout for name in ("番茄鸡蛋面", "牛肉面", "豆腐汤", "时蔬盖饭")))
            draw_id = next(line.split(":", 1)[1].strip() for line in lunch.stdout.splitlines() if line.startswith("draw_id:"))
            marked = self.run(root, "mark", draw_id, "did")
            self.assertEqual(marked.returncode, 0, marked.stderr)
            self.assertIn("did", marked.stdout)

            video = self.run(root, "draw", "bili_featured", "--count", "1", "--seed", "2", "--json")
            self.assertEqual(video.returncode, 0, video.stderr)
            payload = json.loads(video.stdout)
            face = payload["cards"][0]["face"]
            self.assertTrue(face["title"])
            self.assertTrue(face["up"])
            self.assertIn("why", face)
            self.assertTrue(payload["cards"][0]["reason"])

            hand = self.run(root, "draw", "lunch", "--count", "3", "--seed", "3", "--json")
            self.assertEqual(hand.returncode, 0, hand.stderr)
            three = json.loads(hand.stdout)
            picked = three["cards"][0]["id"]
            chosen = self.run(root, "mark", three["draw_id"], f"picked:{picked}")
            self.assertEqual(chosen.returncode, 0, chosen.stderr)
            self.assertIn(picked, chosen.stdout)

            pack_root = write_project(
                Path(box.name) / "pack",
                [meal(f"m{i}", f"菜{i}", ["清淡"], 10, 1) for i in range(5)]
                + [meal("meat", "红烧肉", ["荤"], 30, 1)],
                FIXTURE,
            )
            listed = self.run(pack_root, "categories", "lunch")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn("可以开包", listed.stdout)
            self.assertIn("还差", listed.stdout)
            packed = self.run(pack_root, "draw", "lunch", "--count", "5", "--tag", "清淡", "--json")
            self.assertEqual(packed.returncode, 0, packed.stderr)
            five = json.loads(packed.stdout)
            self.assertEqual(len(five["cards"]), 5)
            self.assertTrue(all("清淡" in card["face"]["tags"] for card in five["cards"]))
            self.assertNotIn("meat", {card["id"] for card in five["cards"]})
        finally:
            box.cleanup()

    def run(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHOUKA_ROOT"] = str(root)
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("BILI_DUTY_HOME", None)
        return subprocess.run(
            [sys.executable, "-m", "chouka", *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
