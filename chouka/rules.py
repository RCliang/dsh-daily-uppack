"""抽卡规则。纯函数：不读盘，不访问网络，不调用模型。"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

BASE_WEIGHT = 1.0
DID_WEIGHT_STEP = 0.8
DID_WEIGHT_CAP = 4.0
RECENT_DRAW_FACTOR = 0.25
REPEAT_WINDOW = 4
REPEAT_FACTOR = 0.6
SKIP_STREAK_TO_CHILL = 2
CHILL_DAYS = 3
LIGHT_BOOST = 4.0
BILI_NO_DID_DAYS = 3
SHORT_SECONDS = 8 * 60
LONG_SECONDS = 15 * 60

MEAT_TAGS = frozenset({"荤", "重口"})
LIGHT_TAGS = frozenset({"清淡", "蔬菜", "素"})


def is_meat(tags: list[str] | tuple[str, ...] | set[str]) -> bool:
    got = set(tags)
    return bool(got & MEAT_TAGS) and not (got & LIGHT_TAGS)


def is_light(tags: list[str] | tuple[str, ...] | set[str]) -> bool:
    return bool(set(tags) & LIGHT_TAGS)


def watch_variant_for(duration_seconds: int | None) -> str | None:
    if duration_seconds is not None and duration_seconds >= LONG_SECONDS:
        return "first_3_min"
    return None


def parse_day(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def wall_day(now: datetime) -> date:
    return now.date()


def card_tags(stored: dict) -> list[str]:
    face = stored.get("face") if isinstance(stored.get("face"), dict) else stored
    tags = face.get("tags") or []
    return list(tags)


def card_duration(stored: dict) -> int | None:
    face = stored.get("face") if isinstance(stored.get("face"), dict) else stored
    raw = face.get("duration_seconds")
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def _did_card(record: dict) -> dict | None:
    if record.get("result") != "did":
        return None
    cards = record.get("cards") or []
    picked = record.get("picked_id")
    if picked:
        for card in cards:
            if card.get("id") == picked:
                return card
        return None
    if len(cards) == 1:
        return cards[0]
    return None


def _picked_card(record: dict) -> dict | None:
    picked = record.get("picked_id")
    if record.get("result") not in {"picked", "did"} or not picked:
        return None
    for card in record.get("cards") or []:
        if card.get("id") == picked:
            return card
    return None


def outcome_marks(records: list[dict], deck: str) -> list[dict]:
    """每条抽取最终只算一次结果。did / skipped 进权重，picked 只用来打断连续跳过。"""
    marks: list[dict] = []
    for record in records:
        if record.get("deck") != deck:
            continue
        result = record.get("result")
        drawn_at = str(record.get("drawn_at") or "")
        day = parse_day(drawn_at) if drawn_at else None
        if day is None or result not in {"did", "skipped", "picked"}:
            continue
        if result == "did":
            card = _did_card(record)
            if card is not None:
                marks.append({"day": day, "at": drawn_at, "id": card["id"], "kind": "did"})
        elif result == "skipped":
            for card in record.get("cards") or []:
                marks.append({"day": day, "at": drawn_at, "id": card["id"], "kind": "skipped"})
        else:
            card = _picked_card(record)
            if card is not None:
                marks.append({"day": day, "at": drawn_at, "id": card["id"], "kind": "picked"})
    marks.sort(key=lambda item: item["at"])
    return marks


def did_counts(marks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for mark in marks:
        if mark["kind"] == "did":
            counts[mark["id"]] = counts.get(mark["id"], 0) + 1
    return counts


def chilled_ids(marks: list[dict], today: date) -> set[str]:
    by_card: dict[str, list[dict]] = {}
    for mark in marks:
        by_card.setdefault(mark["id"], []).append(mark)
    chilled: set[str] = set()
    for card_id, seq in by_card.items():
        streak: list[dict] = []
        for mark in reversed(seq):
            if mark["kind"] in {"did", "picked"}:
                break
            if mark["kind"] == "skipped":
                streak.append(mark)
        if len(streak) < SKIP_STREAK_TO_CHILL:
            continue
        newest = max(streak, key=lambda item: item["at"])
        if today < newest["day"] + timedelta(days=CHILL_DAYS):
            chilled.add(card_id)
    return chilled


def _deck_records(records: list[dict], deck: str) -> list[dict]:
    rows = [record for record in records if record.get("deck") == deck and record.get("drawn_at")]
    rows.sort(key=lambda record: str(record["drawn_at"]))
    return rows


def repeat_penalties(records: list[dict], deck: str) -> tuple[set[str], dict[str, int]]:
    """返回（上一次抽中的 id，更早的最近几次里每个 id 出现的次数）。"""
    rows = _deck_records(records, deck)
    if not rows:
        return set(), {}
    last_ids = {card["id"] for card in rows[-1].get("cards") or []}
    earlier = rows[-(REPEAT_WINDOW + 1):-1]
    counts: dict[str, int] = {}
    for record in earlier:
        seen: set[str] = set()
        for card in record.get("cards") or []:
            card_id = card.get("id")
            if card_id and card_id not in seen:
                counts[card_id] = counts.get(card_id, 0) + 1
                seen.add(card_id)
    return last_ids, counts


def base_weight(did_count: int, *, in_last_draw: bool, earlier_appearances: int) -> float:
    weight = BASE_WEIGHT + min(DID_WEIGHT_CAP, DID_WEIGHT_STEP * did_count)
    if in_last_draw:
        weight *= RECENT_DRAW_FACTOR
    elif earlier_appearances:
        weight *= REPEAT_FACTOR ** earlier_appearances
    return weight


def lunch_light_boost(records: list[dict], today: date) -> bool:
    """昨天和前天都照做了偏荤的午饭时，今天提高清淡牌权重。"""
    needed = (today - timedelta(days=2), today - timedelta(days=1))
    latest: dict[date, dict] = {}
    for record in _deck_records(records, "lunch"):
        if record.get("result") != "did":
            continue
        day = parse_day(str(record["drawn_at"]))
        card = _did_card(record)
        if card is not None:
            latest[day] = card
    for day in needed:
        card = latest.get(day)
        if card is None or not is_meat(card_tags(card)):
            return False
    return True


def bili_short_pity(records: list[dict], today: date) -> bool:
    """连续三个有抽取、且日历相连的日子都没有 did，则下次保底短视频。"""
    by_day: dict[date, bool] = {}
    for record in _deck_records(records, "bili_featured"):
        day = parse_day(str(record["drawn_at"]))
        if day >= today:
            continue
        did = by_day.get(day, False) or record.get("result") == "did"
        by_day[day] = did
    if not by_day:
        return False
    ordered = sorted(by_day)
    run = [ordered[-1]]
    for day in reversed(ordered[:-1]):
        if run[-1] - day == timedelta(days=1):
            run.append(day)
        else:
            break
    if len(run) < BILI_NO_DID_DAYS:
        return False
    return all(not by_day[day] for day in run[:BILI_NO_DID_DAYS])


def yesterday_ids(records: list[dict], deck: str, today: date) -> list[str]:
    yesterday = today - timedelta(days=1)
    found: list[str] = []
    for record in _deck_records(records, deck):
        if parse_day(str(record["drawn_at"])) != yesterday:
            continue
        for card in record.get("cards") or []:
            card_id = card.get("id")
            if card_id and card_id not in found:
                found.append(card_id)
    return found


def compute_weights(cards: list[dict], records: list[dict], deck: str, today: date) -> dict[str, float]:
    marks = outcome_marks(records, deck)
    chilled = chilled_ids(marks, today)
    dids = did_counts(marks)
    last_ids, earlier = repeat_penalties(records, deck)
    boost_light = deck == "lunch" and lunch_light_boost(records, today)
    weights: dict[str, float] = {}
    for card in cards:
        card_id = card["id"]
        if card_id in chilled:
            weights[card_id] = 0.0
            continue
        weight = base_weight(
            dids.get(card_id, 0),
            in_last_draw=card_id in last_ids,
            earlier_appearances=earlier.get(card_id, 0),
        )
        if boost_light and is_light(card.get("tags") or []):
            weight *= LIGHT_BOOST
        weights[card_id] = weight
    return weights


def short_subset(cards: list[dict]) -> list[dict]:
    known = [card for card in cards if isinstance(card.get("duration_seconds"), int)]
    under = [card for card in known if card["duration_seconds"] <= SHORT_SECONDS]
    if under:
        return under
    if not known:
        return []
    least = min(card["duration_seconds"] for card in known)
    return [card for card in known if card["duration_seconds"] == least]


def weighted_pick(cards: list[dict], weights: dict[str, float], count: int, rng: random.Random) -> list[dict]:
    pool = [card for card in cards if weights.get(card["id"], 0) > 0]
    if count > len(pool):
        raise ValueError("可用的卡不够")
    chosen: list[dict] = []
    for _ in range(count):
        total = sum(weights[card["id"]] for card in pool)
        roll = rng.random() * total
        acc = 0.0
        index = len(pool) - 1
        for i, card in enumerate(pool):
            acc += weights[card["id"]]
            if roll < acc:
                index = i
                break
        chosen.append(pool.pop(index))
    return chosen


def pick_cards(
    cards: list[dict],
    weights: dict[str, float],
    count: int,
    rng: random.Random,
    *,
    guarantee_short: bool,
) -> tuple[list[dict], bool]:
    """返回 (抽中的卡, 短视频保底是否真的放进了结果)。"""
    ordered = sorted(cards, key=lambda card: card["id"])
    if not guarantee_short:
        return weighted_pick(ordered, weights, count, rng), False
    shorts = [card for card in short_subset(ordered) if weights.get(card["id"], 0) > 0]
    if not shorts:
        return weighted_pick(ordered, weights, count, rng), False
    first = weighted_pick(shorts, weights, 1, rng)
    if count == 1:
        return first, True
    rest_pool = [card for card in ordered if card["id"] != first[0]["id"]]
    rest = weighted_pick(rest_pool, weights, count - 1, rng)
    return first + rest, True
