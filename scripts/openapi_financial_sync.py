#!/usr/bin/env python3
"""日常財報同步:走 TWSE / TPEX OpenAPI(JSON、免費、無配額)。

定位(2026-08-13 定案):
    FinMind 配額長期用盡(見 finmind-quota-chronically-exhausted),日常同步實質
    停擺。本腳本接手「最新一季、一般業」這條高頻路徑;MOPS 那支
    (mops_income_backfill.py)只負責低頻的補歷史與金融業。
    這樣把 HTML 解析的脆弱性侷限在低頻任務,日常路徑走穩定的 JSON。

涵蓋與已知限制(皆為實測):
  - 上市一般業 594 家(t187ap06_L_ci / t187ap07_L_ci)
  - 上櫃一般業 371 家(mopsfin_t187ap06_O_ci / _07_)
  - 🔴 **金融/證券/金控端點形同無效**:_basi 只有 1 家台中銀、_bd 那筆欄位全空、
    _mim 那筆竟是和泰車(根本不是金融業);TWSE 與 TPEX 兩側皆然。
    這 100+ 檔只能靠 MOPS 補。
  - 🔴 **只有最新一季**,沒有歷史參數 → 補不了歷史缺季。
  - **只含已申報的公司**:實測 2026-08-13 抓 115Q2,2330 台積電不在內
    (Q2 申報期限 8/14 尚未到)。所以本腳本要**重複跑**才會逐步補齊,
    單次跑完不代表該季完整。

🔴 累計陷阱(與 MOPS 相同,不要以為 JSON 就沒有):
    實測 115Q2,OpenAPI 的「本期淨利（淨損）」與 MOPS 的**累計**值完全相同
    (1101=4,569,799、1216=21,022,083、2454=48,981,437 三者皆分毫不差)
    → OpenAPI 給的是**年初至今累計**,不是單季。
    但它只給最新一季,沒有上一季可相減,故改以本機既有的單季值回推:
        單季_n = 累計_n − Σ(本機 Q1..Q_{n-1} 單季)
    實測三檔與 MOPS 差分結果吻合到個位數。Q1 的累計即單季。
    若同年前面幾季本機不齊 → 無法回推,跳過並計數(不硬寫)。

用法:
    python3 scripts/openapi_financial_sync.py            # dry-run
    python3 scripts/openapi_financial_sync.py --apply
"""
import argparse
from datetime import datetime

import requests
import urllib3
from pymongo import MongoClient, UpdateOne

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_URI = "mongodb://localhost:27017/"
DB_NAME = "tw_stock_analysis"
UA = {"User-Agent": "Mozilla/5.0"}

SOURCES = [
    ("twse", "綜合損益", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci"),
    ("tpex", "綜合損益", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci"),
]

# OpenAPI 中文欄名 → FinMind type 名(下游 build_fundamental_factors 認這個)
FIELD_MAP = {
    "本期淨利（淨損）": "IncomeAfterTaxes",
    "營業收入": "Revenue",
}
# TPEX 用英文鍵放代號/年季,TWSE 用中文
ID_KEYS = ("公司代號", "SecuritiesCompanyCode")
YEAR_KEYS = ("年度", "Year")
SEASON_KEYS = ("季別", "Season")

QEND = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
COL = "financial_statement_detail"


def pick(d, keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def qdate(year, q):
    m, dd = QEND[q]
    return datetime(year, m, dd)


def fetch(url):
    r = requests.get(url, headers=UA, timeout=60, verify=False)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else []


def prior_sum(db, sid, year, q):
    """本機該年 Q1..Q(q-1) 的單季合計(元)。任一季缺 → None(無法回推)。"""
    tot = 0.0
    for k in range(1, q):
        doc = db[COL].find_one({"stock_id": sid, "date": qdate(year, k),
                                "type": "IncomeAfterTaxes"})
        if not doc:
            return None
        tot += doc["value"]
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    db = MongoClient(DB_URI)[DB_NAME]

    ops = []
    stats = {"rows": 0, "written": 0, "no_prior": 0, "exists": 0}
    for market, kind, url in SOURCES:
        try:
            data = fetch(url)
        except Exception as e:
            print(f"  {market} {kind}: 取得失敗 {type(e).__name__}: {e}")
            continue
        if not data:
            print(f"  {market} {kind}: 空清單")
            continue

        y = int(pick(data[0], YEAR_KEYS)) + 1911
        q = int(pick(data[0], SEASON_KEYS))
        dt = qdate(y, q)
        print(f"  {market} {kind}: {len(data)} 家,民國{y-1911}年Q{q}({dt:%Y-%m-%d})")
        stats["rows"] += len(data)

        for row in data:
            sid = str(pick(row, ID_KEYS) or "").strip()
            if len(sid) != 4 or not sid.isdigit():
                continue
            for zh, typ in FIELD_MAP.items():
                raw = str(row.get(zh, "")).replace(",", "").strip()
                if not raw or raw in ("--", "nan"):
                    continue
                try:
                    cum = float(raw)
                except ValueError:
                    continue

                if q == 1:
                    single = cum
                else:
                    if typ != "IncomeAfterTaxes":
                        continue          # 只對淨利做回推;營收的前季合計另需同樣資料
                    prev = prior_sum(db, sid, y, q)
                    if prev is None:
                        stats["no_prior"] += 1
                        continue          # 前面幾季不齊 → 不硬寫
                    single = cum - prev / 1000.0

                exist = db[COL].find_one({"stock_id": sid, "date": dt, "type": typ})
                if exist:
                    stats["exists"] += 1
                    continue              # 已有(多半來自 FinMind)→ 不覆蓋
                ops.append(UpdateOne(
                    {"stock_id": sid, "date": dt, "type": typ},
                    {"$set": {"value": single * 1000, "origin_name": f"{typ}(OpenAPI)",
                              "source": f"OpenAPI:{market}", "updated_at": datetime.now()}},
                    upsert=True))
                stats["written"] += 1

    print(f"\n可寫入 {stats['written']} 筆;已存在跳過 {stats['exists']}、"
          f"前季不齊無法回推 {stats['no_prior']}(共讀 {stats['rows']} 列)")
    if not args.apply:
        print("(dry-run,未寫入。加 --apply 才會實際更新)")
        return
    if ops:
        before = db[COL].count_documents({})
        res = db[COL].bulk_write(ops, ordered=False)
        after = db[COL].count_documents({})
        print(f"寫入:upsert {res.upserted_count} / 更新 {res.modified_count};"
              f"總筆數 {before:,} → {after:,}")
    print("提醒:本腳本只含已申報公司,同一季需重複跑才會補齊(如台積電 Q2 於 8/14 前未報)")


if __name__ == "__main__":
    main()
