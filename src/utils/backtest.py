"""
回測共用 harness
================
集中各 backtest_*.py 重複的「資料解析 / 前向報酬基準 / 規則彙報」。
各腳本仍自行決定『訊號條件』與『樣本收集』(單一職責)，只共用通用機制。

典型用法：
    from src.utils.backtest import tof, dkey, HORIZONS, print_baseline, make_reporter
    base = {h: [] for h in HORIZONS}
    samples = []
    # ... 收集 base[h].append(前向報酬)、samples.append({'rets':{h:..}, ...})
    bm = print_baseline(base)
    rule = make_reporter(samples, bm)
    rule("① 條件A", lambda s: s['x'] > 0)
"""
import numpy as np

HORIZONS = [5, 10, 20]


def tof(v):
    """Decimal128 / 字串 / 數字 → float；無效回 None。"""
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except Exception:
        return None


def dkey(d):
    """date 欄(datetime 或字串) → 'YYYY-MM-DD'。"""
    return d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]


def baseline_means(base, horizons=HORIZONS):
    """各視窗基準平均報酬 {h: mean}。"""
    return {h: float(np.mean(base[h])) for h in horizons}


def print_baseline(base, horizons=HORIZONS):
    """印全體基準均報酬一行並回傳 means dict。"""
    bm = baseline_means(base, horizons)
    print("全體基準: " + "  ".join(f"{h}日 {bm[h]*100:+.2f}%" for h in horizons)
          + f"  (n={len(base[horizons[0]])})")
    return bm


def report(name, rets_by_h, bm, horizons=HORIZONS):
    """印一條規則的各視窗『原始報酬 / 超額(vs基準) / 勝率』。rets_by_h={h:[報酬]}。"""
    n = len(rets_by_h.get(horizons[0], []))
    if not n:
        print(f"{name:<28} 無樣本"); return
    line = f"{name:<28} n={n:<5}"
    for h in horizons:
        r = np.array(rets_by_h[h])
        line += (f"  {h}日{r.mean()*100:+5.2f}%"
                 f"(超額{(r.mean()-bm[h])*100:+5.2f}%,勝{100*(r > 0).mean():.0f}%)")
    print(line)


def make_reporter(samples, bm, horizons=HORIZONS):
    """回一個 rule(name, pred)：以 pred 篩 samples(各含 'rets':{h:報酬})後彙報。"""
    def rule(name, pred):
        sel = [s for s in samples if pred(s)]
        report(name, {h: [s['rets'][h] for s in sel] for h in horizons}, bm, horizons)
    return rule
