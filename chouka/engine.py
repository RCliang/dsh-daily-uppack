"""抽卡与事后标记。没有交互式输入。"""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from pathlib import Path

from chouka.bili_adapter import load_featured
from chouka.categories import apply_zones, load_zone_defs
from chouka.errors import ChoukaError
from chouka.lunch import load_lunch
from chouka.paths import load_paths
from chouka.preview import update_preview_file
from chouka.reasons import bili_reason, lunch_reason
from chouka.rules import (
    bili_short_pity,
    compute_weights,
    did_counts,
    lunch_light_boost,
    outcome_marks,
    pick_cards,
    repeat_penalties,
    wall_day,
    yesterday_ids,
)
from chouka.store import append_draw, load_draws, update_draw

DECKS = ("lunch", "bili_featured")


def draw_card(
    request: dict,
    *,
    root: Path | None = None,
    now: datetime | None = None,
    seed: int | None = None,
) -> dict:
    if not isinstance(request, dict):
        raise ChoukaError("draw_card 的参数必须是字典，例如 {\"deck\": \"lunch\", \"count\": 1}")
    deck = request.get("deck")
    if deck not in DECKS:
        raise ChoukaError("deck 只能是 lunch 或 bili_featured")
    count = _count(request.get("count", 1))
    constraints = _constraints(deck, request.get("constraints"))
    moment = _ensure_now(now)
    today = wall_day(moment)
    paths = load_paths(root)
    records = load_draws(paths.draws)
    pool = _load_deck(deck, paths)
    if not pool:
        raise ChoukaError("这副牌是空的")
    constraints = _name_category(deck, constraints, pool, paths)
    filtered = _filter_pool(deck, pool, constraints, records, today)
    if len(filtered) < count:
        label = constraints.get("tag") or constraints.get("zone_name")
        if label:
            raise ChoukaError(f"「{label}」里只有 {len(filtered)} 张能抽，这次要 {count} 张")
        raise ChoukaError("符合约束的卡不够，放宽预算、走路或「避开昨天」后再抽")
    weights = compute_weights(filtered, records, deck, today)
    active = [card for card in filtered if weights.get(card["id"], 0) > 0]
    if len(active) < count:
        raise ChoukaError("能抽的卡不够：连续跳过的牌还在冷藏")
    guarantee = deck == "bili_featured" and bili_short_pity(records, today)
    rng = random.Random(seed) if seed is not None else random.Random()
    try:
        chosen, short_applied = pick_cards(
            active,
            weights,
            count,
            rng,
            guarantee_short=guarantee,
        )
    except ValueError as exc:
        raise ChoukaError(str(exc)) from exc
    light_boost = deck == "lunch" and lunch_light_boost(records, today)
    pity = _pity(deck, light_boost, guarantee, short_applied)
    ctx_base = _reason_context(deck, constraints, records, today, light_boost)
    last_ids, earlier = repeat_penalties(records, deck)
    dids = did_counts(outcome_marks(records, deck))
    cards_out = []
    for index, card in enumerate(chosen):
        ctx = dict(ctx_base)
        ctx["did_count"] = dids.get(card["id"], 0)
        ctx["in_last_draw"] = card["id"] in last_ids
        ctx["earlier_appearances"] = earlier.get(card["id"], 0)
        ctx["pity_short"] = short_applied and index == 0
        reason = lunch_reason(card, ctx) if deck == "lunch" else bili_reason(card, ctx)
        cards_out.append(_present(card, reason, weights.get(card["id"], 0)))
    result = {
        "draw_id": "d" + uuid.uuid4().hex[:12],
        "deck": deck,
        "count": count,
        "drawn_at": moment.isoformat(timespec="seconds"),
        "constraints": constraints,
        "pity": pity,
        "cards": cards_out,
        "weights": {card_id: round(value, 4) for card_id, value in sorted(weights.items())},
        "result": None,
        "picked_id": None,
        "marked_at": None,
    }
    if seed is not None:
        result["seed"] = seed
    try:
        if update_preview_file(paths.preview_html, result):
            result["preview"] = str(paths.preview_html)
    except Exception as exc:
        result["preview_warning"] = str(exc)
    append_draw(paths.draws, result)
    return result


def mark_result(
    draw_id: str,
    result: str,
    *,
    root: Path | None = None,
    now: datetime | None = None,
) -> dict:
    if not isinstance(draw_id, str) or not draw_id.strip():
        raise ChoukaError("draw_id 不能为空")
    kind, picked_id = _parse_mark(result)
    paths = load_paths(root)
    marked_at = _ensure_now(now).isoformat(timespec="seconds")

    def mutate(row: dict) -> dict:
        updated = dict(row)
        ids = [card.get("id") for card in updated.get("cards") or []]
        if kind == "picked":
            if updated.get("count") == 1:
                raise ChoukaError("抽 1 张时不用标记 picked")
            if picked_id not in ids:
                raise ChoukaError(f"这张卡不在该次抽取里: {picked_id}")
            updated["result"] = "picked"
            updated["picked_id"] = picked_id
        elif kind == "did":
            if updated.get("count") != 1 and not updated.get("picked_id"):
                raise ChoukaError("抽了多张时，先 mark picked:<id>，再 mark did")
            updated["result"] = "did"
        else:
            updated["result"] = "skipped"
        updated["marked_at"] = marked_at
        return updated

    return update_draw(paths.draws, draw_id.strip(), mutate)


def _present(card: dict, reason: str, weight: float) -> dict:
    face = {key: value for key, value in card.items() if key != "deck"}
    return {
        "id": card["id"],
        "deck": card["deck"],
        "title": card["title"],
        "reason": reason,
        "weight": round(weight, 4),
        "watch_variant": card.get("watch_variant"),
        "face": face,
    }


def _pity(deck: str, light_boost: bool, guarantee: bool, short_applied: bool) -> dict:
    if deck == "lunch" and light_boost:
        return {
            "applied": True,
            "rule": "lunch_light",
            "detail": "前两天都照做了偏荤，今天提高了清淡和蔬菜的权重",
        }
    if deck == "bili_featured" and guarantee and short_applied:
        return {
            "applied": True,
            "rule": "bili_short",
            "detail": "连续三天没有 did，这次保底抽一条较短的",
        }
    if deck == "bili_featured" and guarantee and not short_applied:
        return {
            "applied": False,
            "rule": "bili_short",
            "detail": "连续三天没有 did，但没有可抽的较短视频，保底没有生效",
        }
    return {"applied": False, "rule": None, "detail": None}


def _reason_context(deck: str, constraints: dict, records: list[dict], today, light_boost: bool) -> dict:
    if deck != "lunch":
        ctx = {}
        if constraints.get("zone"):
            ctx["zone_name"] = constraints.get("zone_name") or constraints.get("zone")
        return ctx
    names = []
    if constraints.get("avoid_yesterday"):
        skipped = set(yesterday_ids(records, deck, today))
        for record in records:
            if record.get("deck") != deck:
                continue
            for card in record.get("cards") or []:
                title = card.get("title")
                if card.get("id") in skipped and title and title not in names:
                    names.append(title)
    return {
        "pity_light": light_boost,
        "avoided_names": names,
        "budget": constraints.get("budget"),
        "want_walk": constraints.get("want_walk"),
        "tag": constraints.get("tag"),
    }


def _filter_pool(deck: str, cards: list[dict], constraints: dict, records: list[dict], today) -> list[dict]:
    if deck == "lunch":
        banned = set(yesterday_ids(records, deck, today)) if constraints.get("avoid_yesterday") else set()
        budget = constraints.get("budget")
        want_walk = constraints.get("want_walk")
        kept = []
        for card in cards:
            if not card.get("enabled", True):
                continue
            if card["id"] in banned:
                continue
            if budget is not None and card.get("budget", budget + 1) > budget:
                continue
            walk = int(card.get("walk_minutes") or 0)
            if want_walk is True and walk <= 0:
                continue
            if want_walk is False and walk > 0:
                continue
            tag = constraints.get("tag")
            if tag and tag not in (card.get("tags") or []):
                continue
            kept.append(card)
        return kept
    kept = []
    max_seconds = constraints.get("max_duration_seconds")
    tier = constraints.get("tier")
    zone = constraints.get("zone")
    for card in cards:
        if zone and zone not in (card.get("zones") or []):
            continue
        if tier and card.get("tier") != tier:
            continue
        if max_seconds is not None:
            duration = card.get("duration_seconds")
            if not isinstance(duration, int) or duration > max_seconds:
                continue
        kept.append(card)
    return kept


def _load_deck(deck: str, paths) -> list[dict]:
    if deck == "lunch":
        return load_lunch(paths.lunch_pool)
    return apply_zones(load_featured(paths.bili_home), load_zone_defs(paths.bili_zones))


def _name_category(deck: str, constraints: dict, pool: list[dict], paths) -> dict:
    if deck == "lunch":
        tag = constraints.get("tag")
        if not tag:
            return constraints
        known = {
            item
            for card in pool
            if card.get("enabled", True)
            for item in (card.get("tags") or [])
            if isinstance(item, str)
        }
        if tag not in known:
            raise ChoukaError(f"午饭卡池里没有类型「{tag}」。可用类型见 python -m chouka categories lunch")
        return constraints
    zone = constraints.get("zone")
    if not zone:
        return constraints
    names = {item["id"]: item["name"] for item in load_zone_defs(paths.bili_zones)}
    if zone not in names:
        raise ChoukaError(f"没有这个区: {zone}。可用区见 python -m chouka categories bili_featured")
    named = dict(constraints)
    named["zone_name"] = names[zone]
    return named


def _constraints(deck: str, raw: object) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ChoukaError("constraints 必须是字典")
    if deck == "lunch":
        unknown = set(raw) - {"avoid_yesterday", "budget", "want_walk", "tag"}
        if unknown:
            raise ChoukaError("午饭约束只接受 avoid_yesterday、budget、want_walk、tag")
        parsed = {
            "avoid_yesterday": _bool(raw.get("avoid_yesterday", True), "avoid_yesterday"),
            "budget": _optional_number(raw.get("budget"), "budget"),
            "want_walk": None if "want_walk" not in raw or raw.get("want_walk") is None else _bool(raw.get("want_walk"), "want_walk"),
        }
        if raw.get("tag") is not None:
            parsed["tag"] = _plain_text(raw.get("tag"), "tag")
        return parsed
    unknown = set(raw) - {"max_duration_seconds", "tier", "zone"}
    if unknown:
        raise ChoukaError("精选约束只接受 max_duration_seconds、tier、zone")
    tier = raw.get("tier")
    if tier is not None and tier not in {"值得看", "可以看", "不值当"}:
        raise ChoukaError("tier 只能是 值得看、可以看 或 不值当")
    parsed = {
        "max_duration_seconds": _optional_int(raw.get("max_duration_seconds"), "max_duration_seconds"),
        "tier": tier,
    }
    if raw.get("zone") is not None:
        parsed["zone"] = _plain_text(raw.get("zone"), "zone")
    return parsed


def _count(value: object) -> int:
    if isinstance(value, bool):
        raise ChoukaError("count 只能是 1、3 或 5")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ChoukaError("count 只能是 1、3 或 5") from exc
    if count not in (1, 3, 5):
        raise ChoukaError("count 只能是 1、3 或 5")
    return count


def _plain_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChoukaError(f"{name} 必须是非空字符串")
    return value.strip()


def _bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "要", "想"}:
            return True
        if text in {"0", "false", "no", "n", "不", "不想"}:
            return False
    raise ChoukaError(f"{name} 只能是 true 或 false")


def _optional_number(value: object, name: str):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ChoukaError(f"{name} 必须是数字")
    try:
        number = float(value) if isinstance(value, str) else value
    except ValueError as exc:
        raise ChoukaError(f"{name} 必须是数字") from exc
    if isinstance(value, str) and "." not in value:
        return int(value)
    if isinstance(number, float) and number.is_integer():
        return int(number)
    return number


def _optional_int(value: object, name: str) -> int | None:
    number = _optional_number(value, name)
    if number is None:
        return None
    if int(number) != number:
        raise ChoukaError(f"{name} 必须是整数")
    return int(number)


def _parse_mark(result: str) -> tuple[str, str | None]:
    if not isinstance(result, str):
        raise ChoukaError("result 只能是 did、skipped 或 picked:<id>")
    text = result.strip()
    if text in {"did", "skipped"}:
        return text, None
    if text.startswith("picked:"):
        picked = text.split(":", 1)[1].strip()
        if not picked:
            raise ChoukaError("picked 需要卡片 id，例如 picked:beef-noodle")
        return "picked", picked
    raise ChoukaError("result 只能是 did、skipped 或 picked:<id>")


def _ensure_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now().astimezone()
    if now.tzinfo is None:
        return now.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return now
