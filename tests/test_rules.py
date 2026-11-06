"""规则：权重、冷藏、午饭清淡保底、视频短片保底。"""

from __future__ import annotations

import random
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chouka.rules import (  # noqa: E402
    LONG_SECONDS,
    SHORT_SECONDS,
    base_weight,
    bili_short_pity,
    chilled_ids,
    compute_weights,
    is_light,
    is_meat,
    lunch_light_boost,
    outcome_marks,
    pick_cards,
    watch_variant_for,
    weighted_pick,
)

TZ = timezone(timedelta(hours=8))


def at(day: str) -> str:
    return f"{day}T12:00:00+08:00"


def lunch_card(card_id: str, tags: list[str], title: str | None = None) -> dict:
    return {
        "id": card_id,
        "title": title or card_id,
        "tags": tags,
        "duration_seconds": None,
    }


def stored(card: dict) -> dict:
    return {
        "id": card["id"],
        "title": card["title"],
        "face": {"tags": card["tags"], "duration_seconds": card.get("duration_seconds")},
    }


def record(deck: str, day: str, cards: list[dict], result: str | None, picked_id: str | None = None) -> dict:
    return {
        "draw_id": f"d-{day}-{cards[0]['id']}-{result}",
        "deck": deck,
        "count": len(cards),
        "drawn_at": at(day),
        "cards": [stored(card) for card in cards],
        "result": result,
        "picked_id": picked_id,
    }


class WeightTests(unittest.TestCase):
    def test_meat_and_light_tags(self):
        self.assertTrue(is_meat(["荤"]))
        self.assertTrue(is_meat(["重口", "面"]))
        self.assertFalse(is_meat(["荤", "蔬菜"]))
        self.assertTrue(is_light(["清淡"]))
        self.assertTrue(is_light(["素"]))
        self.assertFalse(is_light(["荤"]))

    def test_did_raises_weight_and_same_roll_switches_card(self):
        plain = base_weight(0, in_last_draw=False, earlier_appearances=0)
        boosted = base_weight(1, in_last_draw=False, earlier_appearances=0)
        self.assertGreater(boosted, plain)
        cards = [lunch_card("a", ["荤"]), lunch_card("b", ["清淡"])]
        weights_before = {"a": plain, "b": plain}
        weights_after = {"a": boosted, "b": plain}
        roll = random.Random()
        roll.random = lambda: 0.5  # type: ignore[method-assign]
        before = weighted_pick(list(cards), weights_before, 1, roll)
        roll.random = lambda: 0.5  # type: ignore[method-assign]
        after = weighted_pick(list(cards), weights_after, 1, roll)
        self.assertEqual(before[0]["id"], "b")
        self.assertEqual(after[0]["id"], "a")

    def test_just_drawn_card_is_penalized_but_did_still_compares(self):
        fresh = base_weight(0, in_last_draw=False, earlier_appearances=0)
        repeated = base_weight(0, in_last_draw=True, earlier_appearances=1)
        repeated_did = base_weight(1, in_last_draw=True, earlier_appearances=1)
        self.assertLess(repeated, fresh)
        self.assertGreater(repeated_did, repeated)
        self.assertLess(repeated_did, fresh)

    def test_two_skips_chill_then_release(self):
        card = lunch_card("a", ["荤"])
        records = [
            record("lunch", "2026-11-04", [card], "skipped"),
            record("lunch", "2026-11-05", [card], "skipped"),
        ]
        marks = outcome_marks(records, "lunch")
        self.assertIn("a", chilled_ids(marks, date(2026, 11, 5)))
        self.assertIn("a", chilled_ids(marks, date(2026, 11, 7)))
        self.assertNotIn("a", chilled_ids(marks, date(2026, 11, 8)))

    def test_picked_or_did_breaks_skip_streak(self):
        card = lunch_card("a", ["荤"])
        skipped = [
            record("lunch", "2026-11-03", [card], "skipped"),
            record("lunch", "2026-11-04", [card], "skipped"),
            record("lunch", "2026-11-05", [card], "picked", picked_id="a"),
        ]
        marks = outcome_marks(skipped, "lunch")
        self.assertNotIn("a", chilled_ids(marks, date(2026, 11, 5)))
        did = [
            record("lunch", "2026-11-03", [card], "skipped"),
            record("lunch", "2026-11-04", [card], "skipped"),
            record("lunch", "2026-11-05", [card], "did"),
        ]
        self.assertNotIn("a", chilled_ids(outcome_marks(did, "lunch"), date(2026, 11, 5)))

    def test_one_skip_does_not_chill(self):
        card = lunch_card("a", ["荤"])
        records = [record("lunch", "2026-11-05", [card], "skipped")]
        self.assertEqual(chilled_ids(outcome_marks(records, "lunch"), date(2026, 11, 5)), set())


class PityTests(unittest.TestCase):
    def test_two_meat_days_boost_light_cards(self):
        beef = lunch_card("beef", ["荤"], "牛肉面")
        veg = lunch_card("veg", ["清淡", "蔬菜"], "时蔬")
        other = lunch_card("mala", ["荤", "重口"], "香锅")
        records = [
            record("lunch", "2026-11-04", [beef], "did"),
            record("lunch", "2026-11-05", [beef], "did"),
        ]
        today = date(2026, 11, 6)
        self.assertTrue(lunch_light_boost(records, today))
        weights = compute_weights([beef, veg, other], records, "lunch", today)
        self.assertEqual(weights["veg"], 4.0)
        self.assertAlmostEqual(weights["beef"], (1 + 0.8 * 2) * 0.25)
        self.assertEqual(weights["mala"], 1.0)

    def test_skipped_meat_does_not_boost(self):
        beef = lunch_card("beef", ["荤"])
        records = [
            record("lunch", "2026-11-04", [beef], "did"),
            record("lunch", "2026-11-05", [beef], "skipped"),
        ]
        self.assertFalse(lunch_light_boost(records, date(2026, 11, 6)))

    def test_gap_between_meat_days_does_not_boost(self):
        beef = lunch_card("beef", ["荤"])
        records = [
            record("lunch", "2026-11-03", [beef], "did"),
            record("lunch", "2026-11-04", [beef], "did"),
        ]
        self.assertFalse(lunch_light_boost(records, date(2026, 11, 6)))

    def test_latest_did_same_day_wins(self):
        beef = lunch_card("beef", ["荤"])
        veg = lunch_card("veg", ["清淡"])
        records = [
            record("lunch", "2026-11-04", [beef], "did"),
            record("lunch", "2026-11-05", [beef], "did"),
            {
                **record("lunch", "2026-11-05", [veg], "did"),
                "drawn_at": "2026-11-05T18:00:00+08:00",
                "draw_id": "later",
            },
        ]
        self.assertFalse(lunch_light_boost(records, date(2026, 11, 6)))

    def test_bili_three_days_without_did_guarantees_a_short_card(self):
        short = {"id": "short", "title": "短", "tags": [], "duration_seconds": 90}
        medium = {"id": "mid", "title": "中", "tags": [], "duration_seconds": 300}
        long = {"id": "long", "title": "长", "tags": [], "duration_seconds": 70 * 60}
        history = [record("bili_featured", day, [long], None) for day in ("2026-11-03", "2026-11-04", "2026-11-05")]
        today = date(2026, 11, 6)
        self.assertTrue(bili_short_pity(history, today))
        weights = {card["id"]: 1.0 for card in (short, medium, long)}
        weights["long"] = 50.0
        for seed in range(12):
            chosen, applied = pick_cards([short, medium, long], weights, 1, random.Random(seed), guarantee_short=True)
            self.assertTrue(applied)
            self.assertLessEqual(chosen[0]["duration_seconds"], SHORT_SECONDS)
            self.assertNotEqual(chosen[0]["id"], "long")

    def test_bili_count_three_puts_the_short_card_first(self):
        short = {"id": "short", "title": "短", "tags": [], "duration_seconds": 90}
        other = {"id": "other", "title": "别的", "tags": [], "duration_seconds": 3000}
        third = {"id": "third", "title": "第三", "tags": [], "duration_seconds": 4000}
        weights = {"short": 0.1, "other": 9, "third": 9}
        chosen, applied = pick_cards(
            [short, other, third],
            weights,
            3,
            random.Random(1),
            guarantee_short=True,
        )
        self.assertTrue(applied)
        self.assertEqual(chosen[0]["id"], "short")
        self.assertEqual({card["id"] for card in chosen}, {"short", "other", "third"})

    def test_did_in_the_run_or_a_gap_cancels_bili_pity(self):
        card = {"id": "v", "title": "v", "tags": [], "duration_seconds": 90}
        days = ["2026-11-03", "2026-11-04", "2026-11-05"]
        with_did = [record("bili_featured", day, [card], "did" if day == "2026-11-04" else None) for day in days]
        self.assertFalse(bili_short_pity(with_did, date(2026, 11, 6)))
        gapped = [
            record("bili_featured", "2026-11-01", [card], None),
            record("bili_featured", "2026-11-02", [card], None),
            record("bili_featured", "2026-11-04", [card], None),
        ]
        self.assertFalse(bili_short_pity(gapped, date(2026, 11, 6)))

    def test_no_duration_falls_back_and_long_threshold_marks_variant(self):
        unknown = {"id": "u", "title": "未知", "tags": [], "duration_seconds": None}
        chosen, applied = pick_cards([unknown], {"u": 1}, 1, random.Random(0), guarantee_short=True)
        self.assertFalse(applied)
        self.assertEqual(chosen[0]["id"], "u")
        only_long = [
            {"id": "a", "duration_seconds": 20 * 60},
            {"id": "b", "duration_seconds": 40 * 60},
        ]
        from chouka.rules import short_subset

        self.assertEqual([card["id"] for card in short_subset(only_long)], ["a"])
        self.assertIsNone(watch_variant_for(14 * 60))
        self.assertEqual(watch_variant_for(LONG_SECONDS), "first_3_min")
        self.assertEqual(watch_variant_for(None), None)


if __name__ == "__main__":
    unittest.main()
