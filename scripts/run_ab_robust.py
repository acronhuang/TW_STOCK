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

verdict 檔自帶稽核軌跡(取值路徑 + 三個 JSON 的檔案時間),不需要另一支
腳本來驗這支 —— 那種寫法會複製一份取值邏輯,主程式改了副本不會跟著改,
最後驗的是舊副本、給出假綠燈。

用法:
  python3 scripts/run_ab_robust.py                # 完整重跑(三組回測,約數十分鐘)
  python3 scripts/run_ab_robust.py --parse-only   # 不跑回測,只重新解析既有 JSON

輸出:/home/mdsadmin/Stock/tw-stock-analysis/ab_verdict.txt(持久,非 /tmp)
"""
import json
import os
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

# 年化報酬在 JSON 裡的**明確**位置。刻意不用遞迴搜尋:JSON 內同時有
# v2.0 與 v2.1 兩組 annual_return,「找第一個」會在欄位順序一變時
# 靜默抓到 v2.1,產出一份看起來完全正常、數字卻來自另一欄的 verdict。
# 寫死路徑後,結構一變就 KeyError 大聲炸掉,不會悄悄給錯數字。
AR_PATH = ("v2.0", "metrics", "annual_return")


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


def extract_ar(jf):
    """依 AR_PATH 明確取值,回傳年化報酬(float, %)。

    任何一層取不到就直接拋例外 —— 刻意不做 fallback。舊版在 JSON 解析
    失敗時會退去 parse stdout 的「年化報酬 X%」第一行,那同樣可能撈到
    v2.1 的數字,等於換個地方靜默出錯。寧可整組標成失敗,也不要一個
    來路不明的數字混進結論。
    """
    with open(jf, encoding="utf-8") as f:
        d = json.load(f)
    node = d
    for k in AR_PATH:
        if not isinstance(node, dict) or k not in node:
            raise KeyError(f"{jf} 找不到 {'.'.join(AR_PATH)}(斷在 '{k}')")
        node = node[k]
    if not isinstance(node, (int, float)):
        raise TypeError(f"{jf} 的 annual_return 不是數字:{node!r}")
    # JSON 存的是小數(0.2389 = 23.89%)。若已是百分比會得到荒謬值,
    # 與其默默寫進 verdict,不如在這裡就炸掉。
    if abs(node) > 1.5:
        raise ValueError(f"{jf} 的 annual_return={node} 疑似已是百分比,單位假設有變")
    return round(node * 100, 2)


def mtime(jf):
    return datetime.fromtimestamp(os.path.getmtime(jf)).strftime("%m-%d %H:%M:%S")


def run_variant(src, parse_only=False):
    """跑一組(或只解析既有 JSON),回傳 (年化%, 錯誤訊息)。成功時錯誤為 None。"""
    jf = f"{ROOT}/ab_{src}.json"
    if not parse_only:
        subprocess.run([PY, f"{ROOT}/scripts/backtest_integrated_v21.py",
                        "--quality-source", src, "--output", jf],
                       capture_output=True, text=True, cwd=ROOT, timeout=2400)
    try:
        return extract_ar(jf), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def main():
    parse_only = "--parse-only" in sys.argv
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [f"quality A/B verdict  ({ts})"
           + ("  [--parse-only:未重跑回測,只重新解析既有 JSON]" if parse_only else ""),
           "=" * 50]

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
    res, errs = {}, {}
    for src in ("none", "fundamental", "legacy"):
        ar, err = run_variant(src, parse_only=parse_only)
        res[src] = ar
        if err:
            errs[src] = err
        out.append(f"  {src:<12} = {ar if ar is not None else '取值失敗'}%")

    # 稽核軌跡:取值路徑寫死在此,JSON 檔案時間可看出某組是否其實沒跑成
    # (數字合理但檔案是上一輪的舊檔,光看數字看不出來)。
    path_expr = "d" + "".join('["%s"]' % k for k in AR_PATH)
    out += ["", f"取值來源: {path_expr}(明確路徑,取不到即報錯)", "JSON 檔案時間:"]
    for src in ("none", "fundamental", "legacy"):
        jf = f"{ROOT}/ab_{src}.json"
        stamp = mtime(jf) if os.path.exists(jf) else "檔案不存在"
        out.append("  %-22s %s" % (f"ab_{src}.json", stamp))
    if errs:
        out.append("")
        out.append("🔴 取值錯誤(該組結論不可用):")
        for src, e in errs.items():
            out.append(f"  {src}: {e}")

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
