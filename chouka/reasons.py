"""把牌面和当次上下文拼成一句「为什么抽给你」。模板，不是模型。"""

from __future__ import annotations

from chouka.rules import is_light


def _say(bits: list[str]) -> str:
    cleaned = [bit.strip().rstrip("。．. ") for bit in bits if bit and bit.strip()]
    return "。".join(cleaned) + "。"


def clip(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _history_bit(ctx: dict) -> str:
    did_count = int(ctx.get("did_count") or 0)
    in_last = bool(ctx.get("in_last_draw"))
    earlier = int(ctx.get("earlier_appearances") or 0)
    if did_count and in_last:
        return f"你之前照做过 {did_count} 次，但这手它刚被抽过，权重先压低后再抽中"
    if did_count and earlier:
        return f"你之前照做过 {did_count} 次，基础权重更高；最近还出现过，所以又乘了惩罚"
    if did_count:
        return f"你之前照做过 {did_count} 次，所以它更靠前"
    if in_last:
        return "它刚被抽过，权重被压低后仍出现在这手里"
    return "按当前权重抽中"


def lunch_reason(card: dict, ctx: dict) -> str:
    bits = [f"抽到「{card['title']}」"]
    if ctx.get("tag"):
        bits.append(f"你选了「{ctx['tag']}」，所以只从这一类午饭里抽")
    if ctx.get("pity_light") and is_light(card.get("tags") or []):
        bits.append("前两天照做的午饭都偏荤，今天把清淡和蔬菜的权重提高了")
    avoided = ctx.get("avoided_names") or []
    if avoided:
        names = "、".join(f"「{name}」" for name in avoided)
        bits.append(f"避开了昨天抽过的{names}")
    budget = ctx.get("budget")
    if budget is not None:
        bits.append(f"预算不超过 {budget}，这份大约 {card.get('budget')}")
    want_walk = ctx.get("want_walk")
    if want_walk is True:
        bits.append(f"你想走一走，步行大约 {card.get('walk_minutes')} 分钟")
    elif want_walk is False:
        bits.append("你这次不想走路，这份不用出门")
    bits.append(_history_bit(ctx))
    tags = "、".join(card.get("tags") or [])
    if tags:
        bits.append(f"标签是{tags}")
    note = str(card.get("notes") or "").strip()
    if note and not note.startswith("示例"):
        bits.append(note)
    return _say(bits)


def bili_reason(card: dict, ctx: dict) -> str:
    bits = [f"抽到「{card['title']}」"]
    if ctx.get("zone_name"):
        bits.append(f"你选了「{ctx['zone_name']}」这个区，所以只从这里面抽")
    up = card.get("up")
    if up:
        bits.append(f"UP 是{up}")
    meta = []
    if card.get("featured_on"):
        meta.append(f"{card['featured_on']} 被标进精选")
    if card.get("tier"):
        meta.append(f"档位是「{card['tier']}」")
    if meta:
        bits.append("，".join(meta))
    why = clip(card.get("why") or "")
    if why:
        bits.append(f"当初进精选是因为：{why}")
    phrase = card.get("duration_phrase")
    if card.get("watch_variant") == "first_3_min":
        shown = phrase or "偏长"
        bits.append(f"时长约 {shown}，这张只标记为「只看前 3 分钟」，不会打开或播放")
    elif phrase:
        seconds = card.get("duration_seconds") or 0
        if seconds <= 15 * 60:
            bits.append(f"时长约 {phrase}，适合一段午休看完")
        else:
            bits.append(f"时长约 {phrase}")
    else:
        bits.append("日报里没有结构化时长，这次不判断长短")
    if ctx.get("pity_short"):
        bits.append("连续三天没有照做，这次保底从较短的里面抽")
    history = _history_bit(ctx)
    if history != "按当前权重抽中":
        bits.append(history)
    comment = clip(card.get("comment") or "", 40)
    if comment:
        bits.append(f"当时的评语：{comment}")
    return _say(bits)
