"""用歷史合議樣本重播委員投票，對照 20 日後實際超額報酬，評估換委員模型。"""

import math
import random
from collections import defaultdict

from src.moe import consensus

VOTES = consensus.VOTES
ROLE_LABEL = {
    "macro-analyst": "總經", "technical-analyst": "技術", "fundamental-analyst": "基本面",
    "value-analyst": "價值", "risk-manager": "風險", "chip-analyst": "籌碼",
}
_SCORE = {"買進": 1.0, "持有": 0.0, "賣出": -1.0}


def data_summary(reports):
    return "\n".join(f"【{label}】{(reports.get(role) or '')[:300]}" for role, label in ROLE_LABEL.items() if reports.get(role))


def build_prompt(symbol, name, advisor, reports):
    """與 consensus 第一輪盲投同一份提示（草案取前 1500 字，關鍵數據由已存報告重建）。"""
    return consensus._round1_prompt(symbol, name, (advisor or "")[:1500], data_summary(reports or {}))


def parse_vote(response):
    """回 (票, 理由, 是否空洞票)。"""
    vote, reason = consensus._parse_vote_reason(response)
    return vote, reason, bool(vote) and consensus.is_hollow_reason(reason)


def final_from_votes(votes, draft_rating):
    """多數決；平手尊重顧問草案評級，草案不在平手選項就保守持有（與 consensus._finalize 同規則）。"""
    valid = [v for v in votes if v in VOTES]
    if not valid:
        return draft_rating or "持有"
    tally = {v: valid.count(v) for v in VOTES}
    leaders = [v for v in VOTES if tally[v] == max(tally.values())]
    if len(leaders) == 1:
        return leaders[0]
    return draft_rating if draft_rating in leaders else "持有"


def sample_rows(pool, n, seed, max_dates=20):
    """依日期分層抽樣：取均勻分布的至多 max_dates 個日期，每個日期抽相近筆數，固定種子。"""
    by_date = defaultdict(list)
    for row in pool:
        by_date[row["date"]].append(row)
    dates = sorted(by_date)
    if len(dates) > max_dates:
        step = (len(dates) - 1) / (max_dates - 1)
        dates = [dates[round(i * step)] for i in range(max_dates)]
    per_date = max(1, n // len(dates)) if dates else 0
    rng = random.Random(seed)
    picked = []
    for date in dates:
        rows = sorted(by_date[date], key=lambda r: r["symbol"])
        picked.extend(rng.sample(rows, min(per_date, len(rows))))
    return sorted(picked, key=lambda r: (r["date"], r["symbol"]))


def vote_distribution(votes):
    valid = [v for v in votes if v in VOTES]
    total = len(votes) or 1
    dist = {v: (valid.count(v) / len(valid) if valid else 0.0) for v in VOTES}
    dist["abstain"] = (len(votes) - len(valid)) / total
    return dist


def outcome_stats(rows):
    """rows: {'vote','excess'}。買進與賣出各自的平均超額、命中率，及價差（買進減賣出）。"""
    buy = [r["excess"] for r in rows if r["vote"] == "買進" and r.get("excess") is not None]
    sell = [r["excess"] for r in rows if r["vote"] == "賣出" and r.get("excess") is not None]
    mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    mean_buy, mean_sell = mean(buy), mean(sell)
    return {
        "n_buy": len(buy), "n_sell": len(sell), "mean_buy": mean_buy, "mean_sell": mean_sell,
        "spread": None if mean_buy is None or mean_sell is None else mean_buy - mean_sell,
        "hit_buy": (sum(1 for x in buy if x > 0) / len(buy)) if buy else None,
        "hit_sell": (sum(1 for x in sell if x < 0) / len(sell)) if sell else None,
    }


def cluster_bootstrap_spread(rows, iters=2000, seed=1):
    """以日期為單位重抽（同日多檔高度相關，直接用筆數會高估把握）。回 95% 區間或 None。"""
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    dates = sorted(by_date)
    if len(dates) < 2:
        return None
    rng = random.Random(seed)
    spreads = []
    for _ in range(iters):
        sample = [r for d in (rng.choice(dates) for _ in dates) for r in by_date[d]]
        spread = outcome_stats(sample)["spread"]
        if spread is not None:
            spreads.append(spread)
    if len(spreads) < iters * 0.5:
        return None
    spreads.sort()
    return spreads[int(0.025 * len(spreads))], spreads[min(len(spreads) - 1, int(0.975 * len(spreads)))]


def agreement(a, b):
    """a、b: {鍵: 票}。回 (同票率, 相關)；沒有共同有效票回 (None, None)。"""
    keys = [k for k in a if a[k] in VOTES and b.get(k) in VOTES]
    if not keys:
        return None, None
    same = sum(1 for k in keys if a[k] == b[k]) / len(keys)
    xs, ys = [_SCORE[a[k]] for k in keys], [_SCORE[b[k]] for k in keys]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    corr = None if sx == 0 or sy == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
    return same, corr
