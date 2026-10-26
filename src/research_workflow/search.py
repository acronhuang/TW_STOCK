import itertools
import json
import random

from .registry import canonical

WINDOWS = (5, 10, 20, 60, 120, 250)
HOLDS = (3, 5, 10, 20, 40, 60)
FACTORS = ("momentum", "ma_bias", "volatility", "volume_ratio")
THRESHOLDS = (-0.1, -0.05, 0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15)


def generate(seed, count, occupied):
    grid = list(itertools.product(FACTORS, WINDOWS, HOLDS, (3, 5, 10), (5, 20), (False, True), THRESHOLDS))
    random.Random(seed).shuffle(grid)
    result = []
    seen = set(occupied)
    for factor, window, hold, slots, rebalance, reverse, threshold in grid:
        config = {"factor": factor, "window": window, "hold": hold, "slots": slots,
                  "rebalance": rebalance, "reverse": reverse, "threshold": threshold}
        key = canonical(config)
        legacy_key = json.dumps(config, sort_keys=True)
        if key in seen or legacy_key in seen:
            continue
        seen.add(key)
        result.append(config)
        if len(result) == count:
            return result
    raise ValueError("configuration grid exhausted; do not reduce control budgets silently")


def neighbors(config):
    result = []
    for name, levels in (("window", WINDOWS), ("hold", HOLDS), ("threshold", THRESHOLDS)):
        location = levels.index(config[name])
        for offset in (-1, 1):
            if 0 <= location + offset < len(levels):
                result.append({**config, name: levels[location + offset]})
    return result