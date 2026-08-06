#!/usr/bin/env python3
"""資料契約稽核（偵測型「防未來」控制）。

補 MongoDB $jsonSchema 檢查不到的東西：跨欄一致性、單位、型別漂移。針對歷次事故：
  - date 三型（datetime 表混入 str）→ 型別漂移檢查
  - 法人 T86 欄位錯位（foreign+trust+dealer≠total）→ 跨欄檢查
  - 月營收 ×1000 單位錯 → 與 last_month_revenue 量級交叉檢查
  - margin 回退（清乾淨的 code 表又冒 stock_id）→ 禁欄檢查
只檢查「最新一批寫入」，不擋寫入（偵測非強制），違約寫 🔴 進 schedule_alerts（網頁可查）。

用法:
  schema_contract_audit.py          dry-run（印報告，不寫警報）
  schema_contract_audit.py --alert  有 🔴 才寫一筆 schedule_alerts
"""
import argparse
from datetime import datetime

from pymongo import MongoClient

SAMPLE_CAP = 5000  # 每表最新一批最多抽查筆數


def _f(v):
    if v is None:
        return None
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else float(v)


# ── 各表契約 ──
# date_type: 'date'（datetime）/ 'string' / None（無 date 欄，如 year_month）
# id: 可接受的識別碼欄（至少一個要存在且非空）
# forbid: 不該出現的欄（如 margin 不該再有 stock_id）
# enum: {欄: 允許值}
# check: 自訂跨欄檢查函式名
CONTRACTS = {
    "stock_price": {"date_type": "date", "id": ["symbol", "stock_id"], "num": ["close"], "check": "close_pos"},
    "institutional_flow": {"date_type": "date", "id": ["stock_id"], "check": "inst_sum"},
    "monthly_revenue": {"date_type": None, "id": ["symbol"], "num": ["revenue"], "check": "rev_batch"},
    "financial_statement_detail": {"date_type": "date", "id": ["stock_id"], "req": ["type", "value"]},
    "margin_purchase_short_sale": {"date_type": "date", "id": ["code"], "forbid": ["stock_id"]},
    "team_analysis": {"date_type": "date", "id": ["symbol"], "coverage": ("final_verdict", 0.7)},
    "noticed_stocks": {"date_type": "date", "id": ["stock_id"], "enum": {"source": ["twse", "tpex"]}},
    "quarterly_earnings": {"date_type": None, "id": ["symbol"], "req": ["year", "season"]},
}


def latest_batch(col, spec):
    """取最新一批文件（date 表=最新日期整批；year_month 表=最新 year_month；否則最後寫入 N 筆）。"""
    if spec.get("date_type") == "date":
        d = col.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
        if not d:
            return []
        return list(col.find({"date": d["date"]}).limit(SAMPLE_CAP))
    # year_month / year+season 類
    d = col.find_one(sort=[("_id", -1)])
    if d and "year_month" in d:
        ym = col.find_one(sort=[("year_month", -1)])["year_month"]
        return list(col.find({"year_month": ym}).limit(SAMPLE_CAP))
    if d and "year" in d and "season" in d:
        top = col.find_one(sort=[("year", -1), ("season", -1)])
        return list(col.find({"year": top["year"], "season": top["season"]}).limit(SAMPLE_CAP))
    return list(col.find(sort=[("_id", -1)]).limit(SAMPLE_CAP))


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def check_close_pos(docs, col):
    return sum(1 for d in docs if (_f(d.get("close")) or 0) <= 0)


def check_inst_sum(docs, col):
    """法人跨欄:foreign+trust+dealer 必須≈total(抓 T86 欄位錯位)。"""
    bad = 0
    for d in docs:
        f, t, de, tot = _f(d.get("foreign_net")), _f(d.get("trust_net")), _f(d.get("dealer_net")), _f(d.get("total_net"))
        if None in (f, t, de, tot):
            continue
        if abs((f + t + de) - tot) > max(abs(tot) * 0.001, 1):
            bad += 1
    return bad


def check_rev_batch(docs, col):
    """批次量級:本月營收中位數 vs 上月中位數,差 >50x = 系統性單位錯(×1000)。
    個股 lumpy 不影響中位數,故不誤報營建/控股股。"""
    cur_ym = docs[0].get("year_month")
    cur_med = _median([_f(d.get("revenue")) for d in docs])
    prev = col.find_one({"year_month": {"$lt": cur_ym}}, sort=[("year_month", -1)])
    if not prev or not cur_med:
        return 0
    prev_ym = prev["year_month"]
    prev_med = _median([_f(d.get("revenue")) for d in col.find({"year_month": prev_ym}).limit(SAMPLE_CAP)])
    if not prev_med:
        return 0
    ratio = cur_med / prev_med
    return 1 if (ratio > 50 or ratio < 0.02) else 0


CHECKS = {"close_pos": check_close_pos, "inst_sum": check_inst_sum, "rev_batch": check_rev_batch}


def audit_table(col, spec):
    docs = latest_batch(col, spec)
    v = {}
    if not docs:
        return {"n": 0, "viol": {"無資料": 1}}
    n = len(docs)
    # id 欄
    idf = spec.get("id", [])
    if idf:
        miss = sum(1 for d in docs if not any(str(d.get(k, "")).strip() for k in idf))
        if miss:
            v[f"id欄({'/'.join(idf)})缺失"] = miss
    # date 型別漂移
    dt = spec.get("date_type")
    if dt == "date":
        bad = sum(1 for d in docs if not isinstance(d.get("date"), datetime))
        if bad:
            v["date非datetime(型別漂移)"] = bad
    # 必填
    for rq in spec.get("req", []):
        m = sum(1 for d in docs if d.get(rq) is None)
        if m:
            v[f"必填{rq}缺"] = m
    # 數值
    for nk in spec.get("num", []):
        b = sum(1 for d in docs if d.get(nk) is not None and _f(d.get(nk)) is None)
        if b:
            v[f"{nk}非數值"] = b
    # 禁欄
    for fb in spec.get("forbid", []):
        b = sum(1 for d in docs if fb in d)
        if b:
            v[f"出現禁欄{fb}"] = b
    # enum
    for ek, allowed in spec.get("enum", {}).items():
        b = sum(1 for d in docs if d.get(ek) is not None and d.get(ek) not in allowed)
        if b:
            v[f"{ek}非法值"] = b
    # 覆蓋率門檻（低於門檻才報,避免零星在跑中的誤報）
    cov = spec.get("coverage")
    if cov:
        field, min_ratio = cov
        present = sum(1 for d in docs if d.get(field) not in (None, ""))
        ratio = present / n if n else 1
        if ratio < min_ratio:
            v[f"{field}覆蓋率{ratio:.0%}<{min_ratio:.0%}"] = n - present
    # 自訂跨欄
    ck = spec.get("check")
    if ck and ck in CHECKS:
        b = CHECKS[ck](docs, col)
        if b:
            v[f"跨欄檢查({ck})"] = b
    return {"n": n, "viol": v}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true", help="有 🔴 才寫 schedule_alerts")
    args = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

    print(f"[{datetime.now():%F %T}] 資料契約稽核（最新批）")
    problems = []
    for t, spec in CONTRACTS.items():
        r = audit_table(db[t], spec)
        if r["viol"]:
            detail = ", ".join(f"{k}={n}" for k, n in r["viol"].items())
            print(f"  🔴 {t:30} (批{r['n']}) {detail}")
            problems.append(f"{t}: {detail}")
        else:
            print(f"  ✅ {t:30} (批{r['n']}) 契約通過")

    if problems and args.alert:
        try:
            db.schedule_alerts.create_index([("ts", -1)])
            db.schedule_alerts.insert_one({
                "ts": datetime.now(), "level": "error", "source": "contract_audit",
                "message": "資料契約違約: " + " | ".join(problems), "resolved": False})
            print(f"[alert] 已寫入 schedule_alerts（{len(problems)} 表違約）")
        except Exception as e:
            print(f"[alert] 寫入失敗:{e!r}")
    elif problems:
        print(f"\n[DRY-RUN] {len(problems)} 表違約（加 --alert 才寫網頁）")
    else:
        print("\n✅ 全部契約通過")


if __name__ == "__main__":
    main()
