#!/usr/bin/env python3
"""因子 IC 分析 —— 在回測之外,用獨立方法檢驗因子是否真有預測力。

為什麼需要這支:
    A/B 回測是「策略層」的證據,混了權重、再平衡頻率、資金配置與停損規則。
    IC 是「因子層」的證據,只問一件事:t 期的因子排序,能不能預測 t+h 期的
    報酬排序。兩者若同向,結論才站得住;若 IC 說沒用而回測說有用,那超額
    多半來自權重交互作用,只對該組配置成立,不可外推到別的策略。

判定全部寫死在程式裡,結論寫進持久檔 ic_verdict.txt,人只負責原樣讀出。
沿用 run_ab_robust.py 的作法:閘門 → 計算 → 判定,不靠口頭判讀輸出。

用法:
    python3 scripts/factor_ic_analysis.py                    # 全部因子
    python3 scripts/factor_ic_analysis.py --factors quality  # 只跑指定因子
    python3 scripts/factor_ic_analysis.py --start 2018-01    # 縮短期間(除錯用)

輸出:/home/mdsadmin/Stock/tw-stock-analysis/ic_verdict.txt(持久,非 /tmp)
"""
import argparse
import sys
from datetime import datetime

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")

from pymongo import MongoClient

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
OUT = f"{ROOT}/ic_verdict.txt"

# ── 閘門 ───────────────────────────────────────────────────────────────
MIN_COVERAGE = 0.85   # 任一期覆蓋率低於此 → 該因子拒判(選樣偏誤)
MIN_PERIODS = 36      # 有效期數低於此 → 拒判(統計量不可信)
MIN_POOL = 300        # 單期股票數低於此 → 該期跳過

# ── PASS 門檻(四項全過才 PASS)────────────────────────────────────────
TH_IC = 0.02          # |IC 平均|
TH_ICIR = 0.30        # ICIR = IC 平均 / IC 標準差
TH_T = 2.00           # t = ICIR × sqrt(期數)

HORIZONS = (1, 3, 6, 12)   # 前瞻月數
PRIMARY_H = 1              # 判定以 1 個月為準,其餘看衰減

# 受測因子。direction=+1 表示「值越大越好」,-1 表示「越小越好」。
# 取值後一律乘 direction,使 IC 為正代表因子有效,判讀不必再想方向。
FACTORS = {
    "momentum_12m": {"src": "stock_factors", "field": "return_12m", "direction": +1},
    "momentum_6m": {"src": "stock_factors", "field": "return_6m", "direction": +1},
    "value_ey": {"src": "stock_factors", "field": "earnings_yield", "direction": +1},
    "value_pb": {"src": "stock_factors", "field": "pb_ratio", "direction": -1},
    "quality_roe_sf": {"src": "stock_factors", "field": "roe", "direction": +1},
    "quality_opm_sf": {"src": "stock_factors", "field": "operating_margin", "direction": +1},
    # 以下走 MultiFactorStrategy._fundamental_quality(),即帶 available_from
    # 落後的 point-in-time 序列 —— 這正是 A/B 裡 quality_source=fundamental 用的東西。
    "quality_roe_pit": {"src": "fundamental", "field": "roe", "direction": +1},
    "quality_opm_pit": {"src": "fundamental", "field": "op_margin", "direction": +1},
    # 註:fundamental_factors 另有 roic(78% 非空),但 _fundamental_quality() 只回傳
    # roe/roa/profit_margin/debt_ratio/op_margin/fcf_margin 六欄,roic 取不到。
    # 不在此硬測 —— 那要另寫一份落後邏輯,就變成驗證副本而非驗證真正在跑的路徑。
    # 要測 roic 應先讓 _fundamental_quality() 也回傳它。
}


# ── 統計工具(不依賴 scipy,避免環境差異)──────────────────────────────
def _ranks(xs):
    """平均排名法處理同分,回傳與輸入等長的 rank list。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    rk = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rk[order[k]] = avg
        i = j + 1
    return rk


def _pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / (va ** 0.5 * vb ** 0.5)


def spearman(a, b):
    """Spearman rank correlation。輸入等長 list。"""
    return _pearson(_ranks(a), _ranks(b))


def mean_std(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else 0.0), 0.0
    m = sum(xs) / n
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    return m, sd


# ── 資料載入 ───────────────────────────────────────────────────────────
def month_end_dates(db, start, end):
    """從 trading_dates(權威日曆,字串 date)取每月最後交易日。"""
    rows = db.trading_dates.find(
        {"date": {"$gte": start, "$lte": end}}, {"date": 1}
    ).sort("date", 1)
    by_month = {}
    for r in rows:
        d = r["date"]
        by_month[d[:7]] = d          # 同月後來者覆蓋 → 最後一個交易日
    return [by_month[k] for k in sorted(by_month)]


def load_prices(db, dates, log):
    """{date_str: {symbol: adj_close}};只取月底那幾天,不整表掃。"""
    out = {}
    for i, d in enumerate(dates):
        dt = datetime.strptime(d, "%Y-%m-%d")
        cur = db.stock_price.find(
            {"date": dt, "adj_close": {"$ne": None}},
            {"symbol": 1, "adj_close": 1, "_id": 0},
        )
        m = {}
        for r in cur:
            s = str(r.get("symbol", ""))
            if len(s) != 4:          # 排除 6 碼權證/ETF 變體,與回測股票池一致
                continue
            try:
                px = float(str(r["adj_close"]))
            except (TypeError, ValueError):
                continue
            if px > 0:
                m[s] = px
        out[d] = m
        if (i + 1) % 24 == 0:
            log(f"  價格載入 {i + 1}/{len(dates)} 期")
    return out


def load_sf_factors(db, dates, fields, log):
    """{date_str: {symbol: {field: value}}} —— 來自 stock_factors。"""
    out = {}
    proj = {"symbol": 1, "_id": 0}
    for f in fields:
        proj[f] = 1
    for i, d in enumerate(dates):
        dt = datetime.strptime(d, "%Y-%m-%d")
        m = {}
        for r in db.stock_factors.find({"date": dt}, proj):
            s = str(r.get("symbol", ""))
            if len(s) == 4:
                m[s] = r
        out[d] = m
        if (i + 1) % 24 == 0:
            log(f"  stock_factors 載入 {i + 1}/{len(dates)} 期")
    return out


def load_pit_quality(db, dates, log):
    """{date_str: {stock_id: {roe/op_margin/roic...}}}。

    直接呼叫 MultiFactorStrategy._fundamental_quality() —— 刻意不自己重寫
    落後邏輯:要測的就是 production/回測實際在用的那一套。自己寫一份副本
    會變成「驗證副本」,主程式改了測不出來。
    """
    from src.strategy.multi_factor_strategy import MultiFactorStrategy
    s = MultiFactorStrategy(db)
    out = {}
    for i, d in enumerate(dates):
        try:
            out[d] = s._fundamental_quality(d) or {}
        except Exception as e:       # 單期失敗不該讓整份分析掛掉
            out[d] = {}
            log(f"  ⚠ {d} _fundamental_quality 失敗:{type(e).__name__}: {e}")
        if (i + 1) % 24 == 0:
            log(f"  point-in-time quality 載入 {i + 1}/{len(dates)} 期")
    return out


# ── 核心計算 ───────────────────────────────────────────────────────────
def factor_values(name, cfg, d, sf, pit):
    """取某因子在 d 期的 {symbol: 值}(已乘 direction)。"""
    fld, dr = cfg["field"], cfg["direction"]
    src = pit.get(d, {}) if cfg["src"] == "fundamental" else sf.get(d, {})
    vals = {}
    for sym, rec in src.items():
        v = rec.get(fld) if isinstance(rec, dict) else None
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v != v:                   # NaN
            continue
        if cfg["field"] == "pb_ratio" and v <= 0:   # 負淨值無意義
            continue
        vals[str(sym)] = v * dr
    return vals


def analyse(name, cfg, dates, prices, sf, pit):
    """回傳該因子的完整統計,含各 horizon 的 IC 序列與分層結果。"""
    res = {"coverage": [], "ic": {h: [] for h in HORIZONS},
           "quintile": [[] for _ in range(5)], "skipped": 0, "lag_samples": []}

    for i, d in enumerate(dates):
        pool = prices.get(d, {})
        if len(pool) < MIN_POOL:
            res["skipped"] += 1
            continue
        fv = factor_values(name, cfg, d, sf, pit)
        common = [s for s in pool if s in fv]
        # 存成 (期日, 覆蓋率):只存數字的話,索引會與 dates 錯位(有跳過的期),
        # 破洞就會被標到錯的日期上。
        res["coverage"].append((d, len(common) / len(pool)))
        if len(common) < MIN_POOL:
            continue

        for h in HORIZONS:
            if i + h >= len(dates):
                continue
            fut = prices.get(dates[i + h], {})
            xs, ys = [], []
            for s in common:
                p1 = fut.get(s)
                if p1 is None:
                    continue         # 期間下市/停牌 → 該股該期不計入
                xs.append(fv[s])
                ys.append(p1 / pool[s] - 1.0)
            if len(xs) >= MIN_POOL:
                ic = spearman(xs, ys)
                if ic is not None:
                    res["ic"][h].append(ic)
                    if h == PRIMARY_H:      # 只用主 horizon 做分層
                        pairs = sorted(zip(xs, ys))
                        n = len(pairs)
                        for q in range(5):
                            seg = pairs[q * n // 5:(q + 1) * n // 5]
                            if seg:
                                res["quintile"][q].append(
                                    sum(y for _, y in seg) / len(seg))
    return res


def lag_audit(db, pit, dates, log):
    """抽 3 期各 5 檔,核對實際取用那筆的 available_from ≤ 期日。

    ⚠ 必須直接查 fundamental_factors:_fundamental_quality() 只回傳
    roe/roa/profit_margin/debt_ratio/op_margin/fcf_margin 六個數值欄,
    不含 available_from/period_end。早期版本從它的回傳值讀這兩欄,
    一律讀到 None 而把每一筆都標成「前視」—— 那是稽核程式自己的假警報。
    """
    lines = []
    picks = [dates[len(dates) // 4], dates[len(dates) // 2], dates[3 * len(dates) // 4]]
    for d in picks:
        qmap = pit.get(d, {})
        dt = datetime.strptime(d, "%Y-%m-%d")
        lines.append(f"  期日 {d}(共 {len(qmap)} 檔有 point-in-time quality)")
        bad = 0
        for sym in sorted(qmap)[:5]:
            rec = db.fundamental_factors.find_one(
                {"stock_id": sym, "available_from": {"$lte": dt}},
                sort=[("available_from", -1)])
            if not rec:
                lines.append(f"    {sym}: 查無 available_from <= {d} 的紀錄")
                continue
            af, pe = rec.get("available_from"), rec.get("period_end")
            af_s = af.strftime("%Y-%m-%d") if hasattr(af, "strftime") else str(af)
            pe_s = pe.strftime("%Y-%m-%d") if hasattr(pe, "strftime") else str(pe)
            ok = af_s <= d
            if not ok:
                bad += 1
            lines.append(f"    {sym}: 財報期末={pe_s} 可得日={af_s} "
                         f"→ {'OK(落後 %d 天)' % (dt - af).days if ok else '🔴 前視!'}")
        if bad:
            lines.append(f"    🔴 該期有 {bad} 筆前視,落後機制有問題,結論全部作廢。")
    return lines


def coverage_holes(res):
    """列出覆蓋率不足的期別 —— 只印 min/avg 會讓破洞藏起來。"""
    cov = res["coverage"]
    bad = [(d, c) for d, c in cov if c < MIN_COVERAGE]
    if not bad:
        return []
    bad.sort(key=lambda x: x[1])
    out = [f"  ⚠ 覆蓋率不足的期數:{len(bad)}/{len(cov)}"
           f"(最差:{', '.join('%s %.0f%%' % (d, c * 100) for d, c in bad[:3])})"]
    if len(bad) > 3:
        first, last = min(d for d, _ in bad), max(d for d, _ in bad)
        out.append(f"    破洞期間橫跨 {first} ~ {last},查 fundamental_factors 該區段是否漏算")
    return out


def verdict_for(name, res):
    """四級判定,全部寫死。回傳 (等級, 明細行 list)。"""
    out = []
    covs = [c for _, c in res["coverage"]]
    worst = min(covs) if covs else 0.0
    ics = res["ic"][PRIMARY_H]
    n = len(ics)

    out.append(f"  覆蓋率 最低 {worst:.0%} / 平均 {(sum(covs)/len(covs) if covs else 0):.0%}"
               f"(門檻 {MIN_COVERAGE:.0%})  有效期數 {n}(門檻 {MIN_PERIODS})")
    out += coverage_holes(res)

    if worst < MIN_COVERAGE:
        out.append(f"  → GATE_FAILED:覆蓋率 {worst:.0%} < {MIN_COVERAGE:.0%},"
                   f"此時的 IC 反映的是「有沒有資料」而非因子效果,不判定。")
        return "GATE_FAILED", out
    if n < MIN_PERIODS:
        out.append(f"  → GATE_FAILED:有效期數 {n} < {MIN_PERIODS},統計量不可信,不判定。")
        return "GATE_FAILED", out

    m, sd = mean_std(ics)
    icir = m / sd if sd > 0 else 0.0
    t = icir * (n ** 0.5)
    win = sum(1 for x in ics if x > 0) / n

    q = [sum(v) / len(v) if v else 0.0 for v in res["quintile"]]
    spread = q[4] - q[0]
    mono = all(q[i] <= q[i + 1] for i in range(4))

    out.append(f"  IC 平均 {m:+.4f}  標準差 {sd:.4f}  ICIR {icir:+.2f}  "
               f"t {t:+.2f}  勝率 {win:.0%}")
    out.append("  五分層平均 " + str(int(PRIMARY_H)) + "M 報酬: "
               + " | ".join(f"Q{i+1} {v*100:+.2f}%" for i, v in enumerate(q)))
    out.append(f"  Q5−Q1 = {spread*100:+.2f}pp   單調遞增: {'是' if mono else '否'}")
    # 衰減要連 t 一起印。只印 IC 會讓人誤判:判定僅以 PRIMARY_H 為準,
    # 但有些因子(典型是動能)的訊號在較長 horizon 才出現,1M 不顯著不代表沒用。
    decay = []
    for h in HORIZONS:
        xs = res["ic"][h]
        if not xs:
            decay.append(f"{h}M —")
            continue
        mh, sdh = mean_std(xs)
        th = (mh / sdh * (len(xs) ** 0.5)) if sdh > 0 else 0.0
        mark = "*" if abs(th) >= TH_T else " "
        decay.append(f"{h}M {mh:+.4f}(t{th:+.1f}){mark}")
    out.append("  IC 衰減: " + "  ".join(decay) + "   (* = |t|≥2)")
    if any("*" in s for s in decay[1:]) and abs(t) < TH_T:
        out.append(f"  ⚠ 本因子在 {PRIMARY_H}M 不顯著但較長 horizon 顯著 —— "
                   f"上方判定僅以 {PRIMARY_H}M 為準,不代表該因子無用,"
                   f"應改用對應 horizon 的再平衡頻率重測。")

    # 顯著性必須先判。IC 不顯著時它的正負號只是雜訊,拿它去跟分層比對方向
    # 會得到「互相矛盾」的誤判 —— 實際上該說的是「與 0 無法區分」。
    if abs(t) < TH_T:
        note = ""
        if abs(spread) > 0.005:
            note = (f"(註:五分層 Q5−Q1 {spread*100:+.2f}pp 看似有差,但 IC 不顯著,"
                    f"分層差異可能來自少數極端值,不足採信)")
        out.append(f"  → FAIL:|t| {abs(t):.2f} < {TH_T},與 0 無法區分。{note}")
        return "FAIL", out
    if spread * (1 if m >= 0 else -1) < 0:
        out.append("  → FAIL:IC 顯著但 Q5−Q1 與其反號,分層與相關性互相矛盾,結論不可用。")
        return "FAIL", out
    if abs(m) >= TH_IC and icir >= TH_ICIR:
        out.append("  → PASS:IC/ICIR/t 三項達標且分層同向。")
        return "PASS", out
    out.append(f"  → WEAK:方向正確且 t 顯著,但 |IC|{abs(m):.4f} 或 ICIR {icir:.2f} 未達門檻"
               f"({TH_IC} / {TH_ICIR}),不足以單獨支撐加碼。")
    return "WEAK", out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--factors", nargs="*", default=None,
                    help="只跑指定因子(預設全部)")
    args = ap.parse_args()

    buf = []

    def log(msg):
        print(msg, flush=True)

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    buf.append(f"因子 IC 分析  ({ts})")
    buf.append("=" * 72)

    dates = month_end_dates(db, args.start, args.end)
    buf.append(f"期間 {args.start} ~ {args.end},月頻共 {len(dates)} 期"
               f"(取自 trading_dates 每月最後交易日)")
    if len(dates) < MIN_PERIODS + max(HORIZONS):
        buf.append(f"GATE_FAILED:期數 {len(dates)} 太少,無法分析。")
        open(OUT, "w", encoding="utf-8").write("\n".join(buf) + "\n")
        print("GATE_FAILED")
        return

    todo = {k: v for k, v in FACTORS.items()
            if not args.factors or k in args.factors}
    need_sf = sorted({v["field"] for v in todo.values() if v["src"] == "stock_factors"})
    need_pit = any(v["src"] == "fundamental" for v in todo.values())

    log("載入價格…")
    prices = load_prices(db, dates, log)
    log("載入 stock_factors…")
    sf = load_sf_factors(db, dates, need_sf, log) if need_sf else {}
    pit = {}
    if need_pit:
        log("載入 point-in-time quality(逐期呼叫 _fundamental_quality)…")
        pit = load_pit_quality(db, dates, log)

    buf.append(f"股票池:每期取當日有 adj_close 的 4 碼標的,單期不足 {MIN_POOL} 檔則跳過")
    buf.append("")

    grades = {}
    for name, cfg in todo.items():
        log(f"分析 {name}…")
        res = analyse(name, cfg, dates, prices, sf, pit)
        dirtxt = "越大越好" if cfg["direction"] > 0 else "越小越好"
        buf.append(f"── {name}  ({cfg['src']}.{cfg['field']}, {dirtxt}) ──")
        g, lines = verdict_for(name, res)
        grades[name] = g
        buf += lines
        buf.append("")

    if need_pit and pit:
        buf.append("── lag 稽核(抽 3 期各 5 檔,可得日必須 ≤ 期日)──")
        buf += lag_audit(db, pit, dates, log)
        buf.append("")

    buf.append("=" * 72)
    buf.append("總結:")
    for k, g in grades.items():
        buf.append(f"  {k:<20} {g}")
    buf.append("")
    buf.append("怎麼讀:quality 若 PASS → 與 A/B 的 +6.65pp 互相獨立佐證;")
    buf.append("       若 FAIL/WEAK 但回測贏 → 超額多半來自權重交互作用,")
    buf.append("       只對該組配置成立,不可外推到 StockRanker 等其他策略。")

    open(OUT, "w", encoding="utf-8").write("\n".join(buf) + "\n")
    print("DONE")


if __name__ == "__main__":
    main()
