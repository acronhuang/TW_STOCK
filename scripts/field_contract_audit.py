#!/usr/bin/env python3
"""稽核「設定宣告的欄位」與「資料庫實際欄位」是否對得上。

起因(2026-08-13):
    MultiFactorStrategy.factor_config 的 quality 用 op_margin(0.40)/
    fcf_margin(0.30)/roe(0.30),但 stock_factors 根本沒有前兩欄(只有
    operating_margin)。calculate_composite_score 對不存在的欄位執行
    `if factor_name not in factors_df.columns: continue` **靜默跳過**
    → 佔 quality 權重 70% 的兩個因子從未生效。修好後十年年化
    21.04% → 26.64%(commit 5ec2e4b)。

    這種 bug 讀程式碼看不出來:語法正確、不拋例外、沒有 log。只有把
    「設定說要用什麼」與「資料真的有什麼」擺在一起比對才會現形。

═══════════════════════════════════════════════════════════════════════
🔴 為什麼這支自己帶對照組(2026-08-13,第一版就是這樣錯的)

    第一版用 `find({}).sort("_id", -1).limit(800)` 取樣,結果把
    pe_ratio / pb_ratio / earnings_yield 全報成 MISSING —— 但它們實際各有
    388 萬 / 551 萬 / 502 萬筆非空。

    原因:`_id` 倒序取到的是**最新寫入**那批,而 pe/pb 是每晚全表重算、
    最新交易日要等下一晚才補齊(evening_pipeline 3b 步驟)。取樣正好落在
    尚未補齊的區段 → 取樣偏誤 → 假警報。

    這是同一晚第 7 次犯同類錯誤:用未經驗證的代理指標推論全域結論。
    而同晚唯二**沒出錯**的檢查(mops/income backfill 的 sanity_check),
    共同點就是都拿「已知答案」當基準 —— 其中一支還兩度攔下口徑陷阱。

    因此本支強制帶雙向對照組,且**對照組失敗就拒絕輸出任何結論**:
      正向對照 return_6m  —— 已知存在,若被判 MISSING 表示取樣有問題
      反向對照 op_margin  —— 已知不存在,若被判 OK 表示判定失效
    只有正向亮綠、反向亮紅,本次結果才可信。

    另外三項防呆(對應同晚踩過的其他變形):
      ① 按**業務主鍵(date)**抽樣,不按儲存順序 —— 儲存順序反映的是寫入
         批次,不是資料分布。
      ② 直接 import 策略類別讀 factor_config,不用正規表示式掃原始碼 ——
         設定可能被 update_config() 於執行期改過。
      ③ 以「取用端怎麼讀」為準:StockRanker 是取近 30 天每欄首個非 null,
         所以覆蓋率取**多日的最大值**而非最新日 —— 只看最新日會把
         「今天還沒補」誤判成「欄位不存在」。
═══════════════════════════════════════════════════════════════════════

用法:
    python3 scripts/field_contract_audit.py
    python3 scripts/field_contract_audit.py --sparse-threshold 0.5
"""
import argparse
import sys
from datetime import datetime

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")

from pymongo import MongoClient

from src.audit.guard import AuditGuard

SPARSE_THRESHOLD = 0.30   # 覆蓋率低於此 → SPARSE(權重實際被稀釋)
SAMPLE_DATES = 8          # 抽幾個交易日(跨日抽樣,避開單日未補齊的偏誤)

# 各 collection 的日期欄名不同 —— fundamental_factors 用 period_end 而非 date。
# 第二版就是漏了這點,把 fundamental_factors 的六個欄位全報成 MISSING。
DATE_FIELD = {
    "stock_factors": "date",
    "fundamental_factors": "period_end",
}

# 雙向對照組,**每個 collection 各要有一組**。
# 第二版只設了 stock_factors 的對照,於是 fundamental_factors 那條路徑
# 完全沒被驗證就直接輸出假警報 —— 對照組只保護到它涵蓋的範圍。
CONTROLS = [
    ("stock_factors", "return_6m", "OK"),        # 已知存在(全表 593 萬筆非空)
    ("stock_factors", "op_margin", "MISSING"),   # 已知不存在(全表 0 筆)
    ("fundamental_factors", "roe", "OK"),        # 已知存在(84,184 筆非空)
    ("fundamental_factors", "nonexistent_xyz", "MISSING"),  # 保證不存在的假欄位
]


def declared_fields(db):
    """收集各設定宣告要用的欄位 → [(來源, collection, 欄位), ...]

    刻意 import 真正的類別去讀 config,而不是用正規表示式掃原始碼 ——
    設定可能在執行期被 update_config() 改過,掃字串會看到過期內容。
    """
    out = []
    from src.strategy.multi_factor_strategy import MultiFactorStrategy
    s = MultiFactorStrategy(db)
    for cat, cfg in s.factor_config.items():
        for f in cfg.get("factors", {}):
            out.append((f"MultiFactorStrategy.{cat}", "stock_factors", f))

    # 🔴 讀不到欄位必須拋錯,不能當成「沒問題」。
    # 第三版就是這裡出錯:原本寫 getattr(sr_module, "FIELDS", []),但 FIELDS 是
    # _load_candidates 內的**區域變數**,getattr 拿到空清單、又有預設值不拋錯
    # → StockRanker 從頭到尾沒被稽核,而報告看起來一切正常。
    # 「我什麼都沒檢查」與「我檢查了且沒問題」在輸出上必須可區分。
    from src.analysis.stock_ranker import StockRanker
    ranker_fields = list(getattr(StockRanker, "FIELDS", []))
    if not ranker_fields:
        raise RuntimeError(
            "StockRanker.FIELDS 讀不到(空清單)。稽核不能在『沒讀到設定』的情況下"
            "回報正常 —— 那與『檢查過且無問題』無法區分。請確認 FIELDS 在類別層級。")
    for f in ranker_fields:
        out.append(("StockRanker.FIELDS", "stock_factors", f))

    for f in ("roe", "roa", "profit_margin", "debt_ratio", "op_margin", "fcf_margin"):
        out.append(("_fundamental_quality 回傳", "fundamental_factors", f))
    return out


def pick_dates(db, coll, n):
    """取最近 n 個有資料的期別(跨期抽樣的基礎)。日期欄名依 collection 而異。"""
    df = DATE_FIELD.get(coll, "date")
    ds = db[coll].distinct(df, {})
    return sorted([d for d in ds if d], reverse=True)[:n]


def coverage(db, coll, field, dates):
    """回傳 (最佳單日覆蓋率, 各日覆蓋率 list)。

    取**最大值**而非最新日:取用端(StockRanker)是「近 30 天取每欄首個非 null」,
    只要窗內任一日有值就取得到。只看最新日會把「今晚還沒補」誤判成「不存在」。
    """
    df = DATE_FIELD.get(coll, "date")
    per = []
    for d in dates:
        tot = db[coll].count_documents({df: d})
        if not tot:
            continue
        n = db[coll].count_documents({df: d, field: {"$ne": None}})
        per.append(n / tot)
    return (max(per) if per else 0.0), per


def grade(cov, threshold):
    if cov == 0.0:
        return "MISSING"
    return "SPARSE" if cov < threshold else "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sparse-threshold", type=float, default=SPARSE_THRESHOLD)
    ap.add_argument("--dates", type=int, default=SAMPLE_DATES)
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    print(f"欄位契約稽核  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    print("=" * 74)

    date_cache = {}

    def dates_for(coll):
        if coll not in date_cache:
            date_cache[coll] = pick_dates(db, coll, args.dates)
        return date_cache[coll]

    # ── 對照組:交由 AuditGuard 強制執行 ────────────────────────────
    # 刻意不自己寫這段迴圈:第二版就是自己寫、只涵蓋一個 collection,
    # 另一條路徑沒被驗證就吐假警報。護欄會在 finish() 檢查涵蓋完整性。
    guard = AuditGuard("欄位契約稽核")
    for coll, field, expect in CONTROLS:
        guard.add_control(coll, field, expect)
    guard.verify(lambda coll, field: grade(
        coverage(db, coll, field, dates_for(coll))[0], args.sparse_threshold))

    # ── 正式稽核 ────────────────────────────────────────────────────
    buckets = {"MISSING": [], "SPARSE": [], "OK": []}
    seen = set()
    for src, coll, field in declared_fields(db):
        if (coll, field) in seen:
            continue
        seen.add((coll, field))
        guard.audited(coll)            # 登記:這個來源有被稽核 → finish() 會查它有無對照
        cov, per = coverage(db, coll, field, dates_for(coll))
        buckets[grade(cov, args.sparse_threshold)].append((src, coll, field, cov, per))

    for g, icon in (("MISSING", "🔴"), ("SPARSE", "🟡"), ("OK", "✅")):
        items = buckets[g]
        print(f"\n{icon} {g}({len(items)} 項)")
        if g == "OK":
            print("   " + ", ".join(f"{f}({c:.0%})" for _, _, f, c, _ in items))
            continue
        for src, coll, field, cov, per in items:
            detail = ("該欄在抽樣的所有日期都不存在 → **該因子從未生效**"
                      if g == "MISSING" else
                      f"最佳單日覆蓋僅 {cov:.0%} → 多數標的取不到,權重實際被稀釋")
            print(f"   {coll}.{field}  ({src})")
            print(f"     {detail}")
            if per:
                print(f"     各日覆蓋:{', '.join(f'{p:.0%}' for p in per)}")

    # 收尾檢查:每個被稽核的來源都要有雙向對照,缺一個就拋 ControlCoverageGap。
    # 這才是護欄的核心 —— 2026-08-13 的失敗不是「沒對照」,是「對照漏了一個來源」。
    guard.finish()

    print("\n" + "=" * 74)
    if buckets["MISSING"]:
        print("🔴 有設定引用了不存在的欄位。這類錯誤不拋例外、不留 log,")
        print("   只會讓該因子被靜默跳過 —— 權重照算但貢獻為零。")
        raise SystemExit(2)
    print("✅ 所有設定宣告的欄位都存在。")


if __name__ == "__main__":
    main()
