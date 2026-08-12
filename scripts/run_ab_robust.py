#!/usr/bin/env python3
"""quality A/B —— 自包含、判斷全在程式裡的 robust 版。

為什麼這樣寫:執行它的 session 可能不可靠(終端污染 / 會誤讀輸出),
所以把三道防線全部寫死在程式,結論寫進持久檔 ab_verdict.txt,
人只負責原樣讀出,不靠口頭判讀。

三道防線:
1. 覆蓋率閘門:選股池 quality 覆蓋 <85% → 拒跑(避免選樣偏誤),寫明原因。
2. 三組對照:none / fundamental / legacy 的年化(v2.0 欄)全寫進結論檔。
3. 洩漏判定:|fundamental − legacy| < 1pp → 標 FAIL(fundamental 疑似吃到前視),
   因為 legacy 是「有前視」的對照組,兩者接近代表落後機制沒真的擋住前視。

輸出:/home/mdsadmin/Stock/tw-stock-analysis/ab_verdict.txt(持久,非 /tmp)
"""
import json
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
from pymongo import MongoClient

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
PY = "/home/mdsadmin/Stock/.venv/bin/python3"
OUT = f"{ROOT}/ab_verdict.txt"
MIN_COV = 0.85
SAMPLE_DATES = ("2022-06-30", "2023-06-30", "2024-06-28")


def log(lines):
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def coverage():
    from src.strategy.multi_factor_strategy import MultiFactorStrategy
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    s = MultiFactorStrategy(db)
    worst, detail = 1.0, []
    for d in SAMPLE_DATES:
        pool = {p for p in db.stock_factors.distinct(
            "symbol", {"date": datetime.strptime(d, "%Y-%m-%d")})
            if p and len(str(p)) == 4}
        if not pool:
            detail.append((d, 0, 0.0))
            worst = 0.0
            continue
        qmap = s._fundamental_quality(d)
        cov = sum(1 for p in pool if p in qmap and qmap[p].get("roe") is not None) / len(pool)
        detail.append((d, len(pool), cov))
        worst = min(worst, cov)
    return worst, detail


def run_variant(src):
    """跑一組,回傳 v2.0 欄的年化報酬(float, %),失敗回 None。"""
    jf = f"{ROOT}/ab_{src}.json"
    r = subprocess.run([PY, f"{ROOT}/scripts/backtest_integrated_v21.py",
                        "--quality-source", src, "--output", jf],
                       capture_output=True, text=True, cwd=ROOT, timeout=2400)
    # 優先從 JSON 取(比 parse stdout 穩)
    try:
        with open(jf, encoding="utf-8") as f:
            d = json.load(f)
        # 結構:{v20:{metrics:{annual_return}}, ...} 或 {metrics:...};容錯找 annual_return
        def dig(o):
            if isinstance(o, dict):
                if "annual_return" in o:
                    return o["annual_return"]
                for v in o.values():
                    x = dig(v)
                    if x is not None:
                        return x
            return None
        ar = dig(d)
        return round(ar * 100, 2) if ar is not None and abs(ar) < 100 else ar
    except Exception:
        # 退而求其次:從 stdout 抓「年化報酬 X%」第一個(v2.0)
        for line in r.stdout.splitlines():
            if line.strip().startswith("年化報酬"):
                for tok in line.split():
                    if tok.rstrip("%").replace(".", "").replace("-", "").isdigit():
                        return float(tok.rstrip("%"))
        return None


def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [f"quality A/B verdict  ({ts})", "=" * 50]

    worst, detail = coverage()
    out.append("選股池 quality 覆蓋率:")
    for d, n, c in detail:
        out.append(f"  {d}: {n} 檔, 覆蓋 {c:.0%}")
    out.append(f"最低 {worst:.0%} (門檻 {MIN_COV:.0%})")

    if worst < MIN_COV:
        out += ["", f"GATE_FAILED — 覆蓋率 {worst:.0%} < {MIN_COV:.0%},拒跑。",
                "現在跑會是選樣偏誤(反映有無財報資料,非 quality 效果),不執行。"]
        log(out)
        print("GATE_FAILED"); return

    out += ["", "三組年化報酬(v2.0 欄):"]
    res = {}
    for src in ("none", "fundamental", "legacy"):
        ar = run_variant(src)
        res[src] = ar
        out.append(f"  {src:<12} = {ar if ar is not None else '解析失敗'}%")

    f, l = res.get("fundamental"), res.get("legacy")
    out.append("")
    if isinstance(f, (int, float)) and isinstance(l, (int, float)):
        diff = abs(f - l)
        out.append(f"洩漏判定: |fundamental − legacy| = {diff:.2f}pp")
        if diff < 1.0:
            out.append("  → FAIL: fundamental ≈ legacy,fundamental 疑似吃到前視,"
                       "落後機制未擋住。結論不可信,須查 available_from 邏輯。")
        else:
            out.append("  → PASS: 兩組明顯不同,落後機制有生效。")
        n = res.get("none")
        if isinstance(n, (int, float)) and isinstance(f, (int, float)):
            out.append(f"quality 因子貢獻: fundamental({f}%) − none({n}%) = {f - n:+.2f}pp")
    else:
        out.append("洩漏判定: 無法計算(有組別解析失敗)")

    log(out)
    print("DONE")


if __name__ == "__main__":
    main()
