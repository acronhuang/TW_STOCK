#!/usr/bin/env python3
"""
TWSE OpenAPI 補充資料每日同步腳本
=================================
下載 TWSE OpenAPI 中資料庫尚未收集的資料類別。
所有資料寫入同一個 MongoDB: tw_stock_analysis

端點清單（免費、無需 Token、無額度限制）：
  1. 當沖標的統計        TWTB4U
  2. 借券可賣出股數      TWT96U
  3. 處置股票            punish
  4. 注意股票            notice
  5. 重大訊息            ap04_L
  6. 大股東名單          ap02_L
  7. 外資持股 Top20      MI_QFIIS_sort_20
  8. 盤後定價交易        BFT41U
  9. 定期定額排行        ETFRank
 10. 零股交易行情        TWT53U
 11. 內部人持股轉讓      ap12_L
 12. 停資停券預告        BFI84U
 13. 融資融券餘額        MI_MARGN (更新既有)

用法:
    python3 scripts/twse_openapi_sync.py
    python3 scripts/twse_openapi_sync.py --only punish,notice

Author: auto-generated
Date: 2026-04-02
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone, timedelta, date as _date

import requests
import urllib3
from pymongo import MongoClient, ASCENDING, DESCENDING

# 抑制 SSL 警告（TWSE 憑證問題）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE = "https://openapi.twse.com.tw/v1"
NOW = datetime.now(timezone.utc)


def fetch(path: str) -> list[dict]:
    url = f"{BASE}{path}"
    try:
        r = requests.get(url, timeout=30, verify=False)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        log.error(f"  下載失敗 {path}: {e}")
        return []


def roc_to_date(roc_str: str) -> datetime | None:
    """民國日期 (1150401) -> datetime"""
    try:
        s = roc_str.strip()
        if len(s) == 7:
            y = int(s[:3]) + 1911
            m = int(s[3:5])
            d = int(s[5:7])
            return datetime(y, m, d)
    except (ValueError, IndexError):
        pass
    return None


def safe_int(v: str) -> int:
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def safe_float(v: str) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


# ─── 各資料表同步函數 ─────────────────────────────────────

def sync_day_trading(db):
    """當沖標的統計 — TWTB4U"""
    log.info("[1/13] 當沖標的統計 (TWTB4U)...")
    data = fetch("/exchangeReport/TWTB4U")
    if not data:
        return 0
    col = db["day_trading_targets"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    dt = roc_to_date(data[0].get("Date", ""))
    if not dt:
        return 0
    inserted = 0
    for row in data:
        doc = {
            "code": row.get("Code", ""),
            "name": row.get("Name", ""),
            "date": dt,
            "suspension": row.get("Suspension", ""),
            "updated_at": NOW,
        }
        col.update_one({"code": doc["code"], "date": dt}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  日期: {dt.strftime('%Y-%m-%d')}  筆數: {inserted}")
    return inserted


def sync_securities_lending(db):
    """借券可賣出股數 — TWT96U"""
    log.info("[2/13] 借券可賣出股數 (TWT96U)...")
    data = fetch("/SBL/TWT96U")
    if not data:
        return 0
    col = db["securities_lending"]
    col.create_index([("twse_code", ASCENDING), ("date", DESCENDING)])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inserted = 0
    for row in data:
        doc = {
            "twse_code": row.get("TWSECode", ""),
            "twse_volume": safe_int(row.get("TWSEAvailableVolume", "0")),
            "gretai_code": row.get("GRETAICode", ""),
            "gretai_volume": safe_int(row.get("GRETAIAvailableVolume", "0")),
            "date": today,
            "updated_at": NOW,
        }
        col.update_one({"twse_code": doc["twse_code"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_punish(db):
    """處置股票 — punish"""
    log.info("[3/13] 處置股票 (punish)...")
    data = fetch("/announcement/punish")
    if not data:
        return 0
    col = db["punished_stocks"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    inserted = 0
    for row in data:
        dt = roc_to_date(row.get("Date", ""))
        doc = {
            "code": row.get("Code", ""),
            "name": row.get("Name", ""),
            "date": dt,
            "reason": row.get("ReasonsOfDisposition", ""),
            "period": row.get("DispositionPeriod", ""),
            "measures": row.get("DispositionMeasures", ""),
            "detail": row.get("Detail", ""),
            "updated_at": NOW,
        }
        if doc["code"]:
            col.update_one({"code": doc["code"], "date": dt}, {"$set": doc}, upsert=True)
            inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_notice(db):
    """注意股票 — notice"""
    log.info("[4/13] 注意股票 (notice)...")
    data = fetch("/announcement/notice")
    if not data:
        return 0
    col = db["noticed_stocks"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inserted = 0
    for row in data:
        code = row.get("Code", "").strip()
        if not code:
            continue
        doc = {
            "code": code,
            "name": row.get("Name", ""),
            "date": today,
            "announcement_count": safe_int(row.get("NumberOfAnnouncement", "0")),
            "attention_info": row.get("TradingInfoForAttention", ""),
            "closing_price": safe_float(row.get("ClosingPrice", "0")),
            "pe": safe_float(row.get("PE", "0")),
            "updated_at": NOW,
        }
        col.update_one({"code": doc["code"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_major_news(db):
    """重大訊息 — ap04_L"""
    log.info("[5/13] 重大訊息 (ap04_L)...")
    data = fetch("/opendata/t187ap04_L")
    if not data:
        return 0
    col = db["major_news"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    inserted = 0
    for row in data:
        dt = roc_to_date(row.get("發言日期", ""))
        doc = {
            "code": row.get("公司代號", ""),
            "name": row.get("公司名稱", ""),
            "date": dt,
            "time": row.get("發言時間", ""),
            "subject": row.get("主旨 ", row.get("主旨", "")),
            "clause": row.get("符合條款", ""),
            "fact_date": roc_to_date(row.get("事實發生日", "")),
            "detail": row.get("說明", ""),
            "updated_at": NOW,
        }
        if doc["code"]:
            col.update_one({"code": doc["code"], "date": dt, "subject": doc["subject"]},
                           {"$set": doc}, upsert=True)
            inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_major_shareholders(db):
    """大股東名單 — ap02_L"""
    log.info("[6/13] 大股東名單 (ap02_L)...")
    data = fetch("/opendata/t187ap02_L")
    if not data:
        return 0
    col = db["major_shareholders"]
    col.create_index([("code", ASCENDING)])
    inserted = 0
    for row in data:
        doc = {
            "code": row.get("公司代號", ""),
            "name": row.get("公司名稱", ""),
            "shareholder": row.get("大股東名稱", ""),
            "report_date": roc_to_date(row.get("出表日期", "")),
            "updated_at": NOW,
        }
        if doc["code"]:
            col.update_one({"code": doc["code"], "shareholder": doc["shareholder"]},
                           {"$set": doc}, upsert=True)
            inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_foreign_top20(db):
    """外資持股 Top20 — MI_QFIIS_sort_20"""
    log.info("[7/13] 外資持股 Top20 (MI_QFIIS_sort_20)...")
    data = fetch("/fund/MI_QFIIS_sort_20")
    if not data:
        return 0
    col = db["foreign_top20"]
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    inserted = 0
    for row in data:
        doc = {
            "rank": safe_int(row.get("Rank", "0")),
            "code": row.get("Code", ""),
            "name": row.get("Name", ""),
            "shares_held": safe_int(row.get("SharesHeld", "0")),
            "shares_held_pct": safe_float(row.get("SharesHeldPer", "0")),
            "upper_limit": safe_float(row.get("Upperlimit", "0")),
            "date": today,
            "updated_at": NOW,
        }
        col.update_one({"code": doc["code"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_after_hours(db):
    """盤後定價交易 — BFT41U"""
    log.info("[8/13] 盤後定價交易 (BFT41U)...")
    data = fetch("/exchangeReport/BFT41U")
    if not data:
        return 0
    col = db["after_hours_trading"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inserted = 0
    for row in data:
        code = row.get("Code", row.get("股票代號", "")).strip()
        if not code:
            continue
        doc = {
            "code": code,
            "name": row.get("Name", row.get("股票名稱", "")),
            "volume": safe_int(row.get("TradeVolume", row.get("成交股數", "0"))),
            "value": safe_int(row.get("TradeValue", row.get("成交金額", "0"))),
            "close": safe_float(row.get("ClosingPrice", row.get("成交價格", "0"))),
            "date": today,
            "updated_at": NOW,
        }
        col.update_one({"code": doc["code"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_etf_rank(db):
    """定期定額排行 — ETFRank"""
    log.info("[9/13] 定期定額排行 (ETFRank)...")
    data = fetch("/ETFReport/ETFRank")
    if not data:
        return 0
    col = db["etf_dca_rank"]
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    col.create_index([("date", DESCENDING)])
    inserted = 0
    for row in data:
        doc = {
            "rank": safe_int(row.get("No", "0")),
            "stock_code": row.get("STOCKsSecurityCode", ""),
            "stock_name": row.get("STOCKsName", ""),
            "stock_accounts": safe_int(row.get("STOCKsNumberofTradingAccounts", "0")),
            "etf_code": row.get("ETFsSecurityCode", ""),
            "etf_name": row.get("ETFsName", ""),
            "etf_accounts": safe_int(row.get("ETFsNumberofTradingAccounts", "0")),
            "date": today,
            "updated_at": NOW,
        }
        col.update_one({"rank": doc["rank"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_odd_lot(db):
    """零股交易行情 — TWT53U"""
    log.info("[10/13] 零股交易行情 (TWT53U)...")
    data = fetch("/exchangeReport/TWT53U")
    if not data:
        return 0
    col = db["odd_lot_trading"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inserted = 0
    for row in data:
        code = row.get("Code", row.get("股票代號", "")).strip()
        if not code:
            continue
        doc = {
            "code": code,
            "name": row.get("Name", row.get("股票名稱", "")),
            "volume": safe_int(row.get("TradeVolume", row.get("成交股數", "0"))),
            "value": safe_int(row.get("TradeValue", row.get("成交金額", "0"))),
            "close": safe_float(row.get("ClosingPrice", row.get("收盤價", "0"))),
            "date": today,
            "updated_at": NOW,
        }
        col.update_one({"code": doc["code"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_insider_transfer(db):
    """內部人持股轉讓 — ap12_L"""
    log.info("[11/13] 內部人持股轉讓 (ap12_L)...")
    data = fetch("/opendata/t187ap12_L")
    if not data:
        return 0
    col = db["insider_transfer"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    inserted = 0
    for row in data:
        dt = roc_to_date(row.get("出表日期", ""))
        doc = {
            "code": row.get("公司代號", ""),
            "name": row.get("公司名稱", ""),
            "date": dt,
            "insider_name": row.get("申報人姓名", row.get("內部人姓名", "")),
            "identity": row.get("身分別", ""),
            "shares": row.get("預定轉讓股數", ""),
            "reason": row.get("轉讓原因", ""),
            "updated_at": NOW,
        }
        if doc["code"]:
            col.update_one({"code": doc["code"], "date": dt, "insider_name": doc["insider_name"]},
                           {"$set": doc}, upsert=True)
            inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_margin_suspension(db):
    """停資停券預告 — BFI84U"""
    log.info("[12/13] 停資停券預告 (BFI84U)...")
    data = fetch("/exchangeReport/BFI84U")
    if not data:
        return 0
    col = db["margin_suspension"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inserted = 0
    for row in data:
        code = row.get("Code", row.get("股票代號", "")).strip()
        if not code:
            continue
        doc = {
            "code": code,
            "name": row.get("Name", row.get("股票名稱", "")),
            "date": today,
            "detail": json.dumps(row, ensure_ascii=False),
            "updated_at": NOW,
        }
        col.update_one({"code": doc["code"], "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


def sync_margin_trading(db):
    """融資融券餘額 — MI_MARGN (更新既有)"""
    log.info("[13/13] 融資融券餘額 (MI_MARGN)...")
    data = fetch("/exchangeReport/MI_MARGN")
    if not data:
        return 0
    col = db["margin_purchase_short_sale"]
    col.create_index([("code", ASCENDING), ("date", DESCENDING)])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inserted = 0
    for row in data:
        code = row.get("股票代號", "").strip()
        if not code:
            continue
        doc = {
            "code": code,
            "name": row.get("股票名稱", ""),
            "date": today,
            "margin_buy": safe_int(row.get("融資買進", "0")),
            "margin_sell": safe_int(row.get("融資賣出", "0")),
            "margin_cash_repay": safe_int(row.get("融資現金償還", "0")),
            "margin_prev_balance": safe_int(row.get("融資前日餘額", "0")),
            "margin_balance": safe_int(row.get("融資今日餘額", "0")),
            "margin_limit": safe_int(row.get("融資限額", "0")),
            "short_buy": safe_int(row.get("融券買進", "0")),
            "short_sell": safe_int(row.get("融券賣出", "0")),
            "short_cash_repay": safe_int(row.get("融券現券償還", "0")),
            "short_prev_balance": safe_int(row.get("融券前日餘額", "0")),
            "short_balance": safe_int(row.get("融券今日餘額", "0")),
            "short_limit": safe_int(row.get("融券限額", "0")),
            "offset": safe_int(row.get("資券互抵", "0")),
            "note": row.get("註記", ""),
            "updated_at": NOW,
        }
        col.update_one({"code": code, "date": today}, {"$set": doc}, upsert=True)
        inserted += 1
    log.info(f"  筆數: {inserted}")
    return inserted


# ─── 主程式 ─────────────────────────────────────

ALL_SYNCS = {
    "day_trading": sync_day_trading,
    "securities_lending": sync_securities_lending,
    "punish": sync_punish,
    "notice": sync_notice,
    "major_news": sync_major_news,
    "major_shareholders": sync_major_shareholders,
    "foreign_top20": sync_foreign_top20,
    "after_hours": sync_after_hours,
    "etf_rank": sync_etf_rank,
    "odd_lot": sync_odd_lot,
    "insider_transfer": sync_insider_transfer,
    "margin_suspension": sync_margin_suspension,
    "margin_trading": sync_margin_trading,
}


# ─── 資料完整度檢查 ─────────────────────────────────────

# 各資料表的完整度門檻：collection -> (該表最新交易日應有的最低筆數, 最新日期允許落後參考交易日的「交易日」數)
# 參考交易日 = stock_price 最新日期。落後以「交易日」計（依 stock_price 交易日曆），
# 避免週末/連假把正常的 T+1 誤判為落後 3 天。
#   - 最低筆數：抓「當天只下載了一半」（以該表自己的最新日計數，型別安全）。
#   - 容許落後交易日：抓「整天漏掉沒下載」。兩者互補。
# 註：三大法人一律用 institutional_flow（實際使用的 collection）；institutional_trading
#     為已棄用舊表（停在 2026-02），不納入檢查。
# 校準基準：stock_price ~5500/天、stock_factors ~1970/天、institutional_flow ~1224/天。
TABLE_CHECKS = {
    # collection:                  (最低筆數, 容許落後交易日)
    "stock_price":                 (4000, 0),
    "stock_factors":               (1800, 0),
    "institutional_flow":          ( 800, 1),   # T86 法人 T+1 公布，允許落後 1 個交易日
    "margin_purchase_short_sale":  ( 800, 0),
    "day_trading_targets":         ( 800, 0),
    "securities_lending":          ( 800, 0),
    "after_hours_trading":         (1000, 0),
    "odd_lot_trading":             ( 800, 0),
    "major_news":                  (   1, 4),   # 重大訊息非每交易日皆有
    "punished_stocks":             (   0, 5),   # 處置股偶發，可能無資料
    "foreign_top20":               (  20, 0),
    "etf_dca_rank":                (  10, 0),
    "margin_suspension":           (  10, 4),
}

# 參考交易日本身允許落後「今日」的最大日曆天數（涵蓋週末／連假）。
# 超過 → 連 stock_price 都沒更新，代表整條 pipeline 停擺。
PIPELINE_STALE_DAYS = 5

# stock_price 每日會被 macro_sync 塞入一筆 symbol='TAIEX'（加權指數）。
# 計算「參考交易日」「交易日曆」「stock_price 筆數」時必須排除，否則：
#   (1) 全市場股價缺席時，光靠 TAIEX 就讓 stock_price 看似「今天」→ pipeline 停擺偵測失效；
#   (2) 只有 TAIEX 的日子被算進交易日曆 → 其他表虛報落後一天。
_MARKET_FILTER = {"symbol": {"$ne": "TAIEX"}}


def _latest_date_doc(col, extra: dict | None = None):
    """回傳 collection 內 date 最新的一筆文件（無資料則 None）。extra 可加額外過濾（如排除 TAIEX）。"""
    q = {"date": {"$exists": True}}
    if extra:
        q.update(extra)
    return col.find_one(q, sort=[("date", -1)])


def _check_timezone() -> str | None:
    """守衛：系統時區須為 Asia/Taipei。漂移（如退回 UTC）會讓 cron 跑錯時間、資料少抓一天。
    以 /etc/localtime（cron 實際依據的權威來源）判斷，非 /etc/timezone（後者常不同步）。
    回傳問題字串，正常回 None。"""
    import os
    try:
        tz = os.path.realpath("/etc/localtime").split("zoneinfo/")[-1]
        if tz and tz != "Asia/Taipei":
            return f"❌ 系統時區異常：{tz}（應為 Asia/Taipei）→ cron 可能跑錯時間、資料少抓"
        if not tz or "zoneinfo" not in os.path.realpath("/etc/localtime"):
            raise ValueError  # /etc/localtime 非預期 → 落到偏移後備
    except Exception:
        # 後備：以 UTC 偏移判斷（Asia/Taipei = UTC+8）
        off = datetime.now().astimezone().utcoffset()
        if off != timedelta(hours=8):
            return f"❌ 時區偏移異常：{off}（應為 +8:00 Asia/Taipei）"
    return None


# 自適應門檻（B/D）：靜態門檻是「絕對地板」，防呆用；
# 真正的完整判準是「跟近期常態比」——取該表近 N 交易日筆數中位數，
# 門檻抬升到 ADAPT_RATIO × 中位數。只會「往上抬」不會「往下降」到靜態之下：
#   - 修正「門檻太低 → 漏抓」：某表真實日量 5000 但靜態只設 800，跌到 1000 也能揪出。
#   - 不引入「門檻太高 → 誤報」：靜態仍是地板，且中位數會隨真實水位自動跟隨。
# 這就是「真相錨點」：拿系統自己近 20 天的常態當基準，而非跟昨天單點比。
_ADAPT_RATIO = 0.85
_ADAPT_WINDOW = 20
_ADAPT_MIN_SAMPLES = 6
# 自適應只套用在「固定母體、每交易日筆數穩定」的表——一次全市場下載，缺就是真的漏。
# 排除「爆發/稀疏」表（重大訊息、處置股、停資停券預告）：其筆數天生大起大落，
# 用中位數當門檻會誤報；這類表靠靜態低門檻 + 容許落後天數（lag）判斷即可。
_ADAPTIVE_TABLES = {
    "stock_price", "stock_factors", "institutional_flow",
    "margin_purchase_short_sale", "day_trading_targets", "securities_lending",
    "after_hours_trading", "odd_lot_trading", "foreign_top20", "etf_dca_rank",
}


def _adaptive_min(col, static_min: int, trading_days: list, flt: dict) -> tuple[int, int | None]:
    """回傳 (有效門檻, 近期中位數)。歷史樣本不足時退回靜態門檻、中位數 None。
    以「日期區間」計數（相容 date 欄位存 00:00 或 16:00 的時間部分）。
    排除最新一天本身，避免『今天壞掉』把自己的門檻拉低。"""
    prior = trading_days[:-1][-_ADAPT_WINDOW:]  # 近 N 天，排除最新日
    if len(prior) < _ADAPT_MIN_SAMPLES:
        return static_min, None
    counts = []
    for d in prior:
        start = datetime.combine(d, datetime.min.time())
        end = start + timedelta(days=1)
        counts.append(col.count_documents({"date": {"$gte": start, "$lt": end}, **flt}))
    counts = [c for c in counts if c > 0]           # 非交易/無資料日不列入常態
    if len(counts) < _ADAPT_MIN_SAMPLES:
        return static_min, None
    counts.sort()
    median = counts[len(counts) // 2]
    return max(static_min, int(_ADAPT_RATIO * median)), median


# 值合理性（正確錨 A）：完整度只驗「存在」（筆數/落後），不驗「值對」——
# 一個「筆數夠但價格全錯」的日子仍會過關。這裡用零成本的內部不變量（不打外部 API）
# 驗 OHLC 結構是否自洽，抓資料損壞/解析錯欄位。
#   實測校準（2026-07-09）：跨欄位檢查在正常資料上全為 0；唯一的「零價」是 3 檔
#   未成交股（volume==0，OHLC 皆 0）——那是合法「當日無交易」，故 >0 檢查僅對 volume>0 生效。
_VALUE_BAD_MAX = 5  # 容許極少數來源怪列；超過即判值損壞（大規模錯價會是數百上千筆）


def _value_sanity_bad(col, day: _date, flt: dict) -> int:
    """回傳某交易日 OHLC 不自洽的文件數。不變量（皆為結構性、正常解析不可能違反）：
      有成交(volume>0)時 close/high/low/open 須 >0；low≤high；close/open 落在 [low,high]；volume≥0。"""
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    bad_expr = {"$or": [
        {"$and": [{"$gt": ["$volume", 0]},
                  {"$or": [{"$lte": ["$close", 0]}, {"$lte": ["$high", 0]},
                           {"$lte": ["$low", 0]}, {"$lte": ["$open", 0]}]}]},
        {"$gt": ["$low", "$high"]},
        {"$gt": ["$close", "$high"]}, {"$lt": ["$close", "$low"]},
        {"$gt": ["$open", "$high"]}, {"$lt": ["$open", "$low"]},
        {"$lt": ["$volume", 0]},
    ]}
    return col.count_documents(
        {"date": {"$gte": start, "$lt": end}, **flt, "$expr": bad_expr})


def _to_date(v) -> _date | None:
    """將 date 欄位值正規化為 datetime.date，相容 datetime / date / 字串三種型別。"""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    if isinstance(v, str):
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def check_integrity(db) -> tuple[list[str], list[str]]:
    """
    檢查各資料表的完整度，回傳 (ok_list, fail_list)。
    每張表同時驗「最新日期是否落後」與「最新日筆數是否足夠」，兩者互補。
    """
    ok_list = []
    fail_list = []

    # 守衛：系統時區（時區漂移是「pipeline 停擺」最常見根因）
    tz_problem = _check_timezone()
    if tz_problem:
        fail_list.append(tz_problem)

    # 參考交易日：與 run_heal 共用 _reference_day（各表最新日取最大，非 stock_price 自己）
    today = datetime.now().date()
    ref_day = _reference_day(db)
    if ref_day is None:
        fail_list.append("❌ 所有資料表皆查無 date，無法判斷參考交易日")
        return ok_list, fail_list

    # pipeline 停擺檢查：連參考日都落後今日太多（此處用日曆天，含週末/連假緩衝）
    pipeline_lag = (today - ref_day).days
    if pipeline_lag > PIPELINE_STALE_DAYS:
        fail_list.append(
            f"❌ 資料管線停擺：最新交易日 {ref_day} 落後今日 {pipeline_lag} 天 "
            f"(> {PIPELINE_STALE_DAYS} 天)"
        )

    # 交易日曆（近 120 天 stock_price 出現過、且 <= 參考日 的日期）。
    # 用「交易日」而非日曆天衡量落後，避免週末/連假把正常的 T+1 誤判成落後 3 天。
    cal_since = datetime.combine(ref_day - timedelta(days=120), datetime.min.time())
    _cal = {
        d for d in (_to_date(x) for x in db["stock_price"].distinct(
            "date", {"date": {"$gte": cal_since}, **_MARKET_FILTER}))
        if d is not None and d <= ref_day
    }
    # 參考日必須在日曆內：日曆源自 stock_price，若正是 stock_price 缺當日，
    # 日曆就沒有當日 → lag 永遠算 0、偵測不到「今天沒下載」。補進去才測得出。
    _cal.add(ref_day)
    trading_days = sorted(_cal)

    def _trading_day_lag(latest_d: _date) -> int:
        """落後幾個交易日 = 交易日曆中『晚於 latest_d 且 <= 參考日』的天數。"""
        return sum(1 for d in trading_days if d > latest_d)

    for col_name, (min_count, max_lag) in TABLE_CHECKS.items():
        col = db[col_name]
        # stock_price 需排除 TAIEX（否則最新日/筆數被那一筆汙染）
        flt = _MARKET_FILTER if col_name == "stock_price" else {}
        doc = _latest_date_doc(col, flt)
        if not doc:
            fail_list.append(f"❌ {col_name}: 查無 date 欄位資料")
            continue

        latest = _to_date(doc["date"])
        # 以該表「自己的最新日」精準計數（用原始 date 值，型別安全，不需 fallback 全表總數）
        count = col.count_documents({"date": doc["date"], **flt})

        # lag>0 的表（如 institutional_flow：三大法人 T86 T+1 公布）：最新日常是尚未
        # 公布齊的 partial（如 817/2050）。筆數判定改取「最近 (max_lag+1) 個交易日的最高
        # 筆數」——窗內有一天齊即算齊，與 max_lag 落後容許一致，避免把 T+1 當日誤判缺料。
        # ($sort 交給 Mongo，可跨 date 型別排序，不會踩到 Python 混型別排序錯誤)
        check_count, check_date = count, latest
        if max_lag > 0:
            recent = [g["_id"] for g in col.aggregate([
                {"$match": (flt or {"date": {"$exists": True}})},
                {"$group": {"_id": "$date"}}, {"$sort": {"_id": -1}},
                {"$limit": max_lag + 1},
            ])]
            for d in recent:
                c = col.count_documents({"date": d, **flt})
                if c > check_count:
                    check_count, check_date = c, _to_date(d)

        # 自適應門檻：靜態為地板，近期中位數把它往上抬（真相錨點）。
        # 僅限固定母體表；爆發/稀疏表維持靜態（見 _ADAPTIVE_TABLES）。
        if col_name in _ADAPTIVE_TABLES:
            eff_min, median = _adaptive_min(col, min_count, trading_days, flt)
        else:
            eff_min, median = min_count, None

        problems = []
        if latest is not None:
            lag = _trading_day_lag(latest)
            if lag > max_lag:
                problems.append(f"最新 {latest} 落後參考日 {ref_day} {lag} 個交易日 (容許 ≤{max_lag})")
        # 值合理性（正確錨）：僅對 stock_price 驗 OHLC 自洽。與筆數同屬一行 →
        # 走同一條 backfill 自癒路徑（重抓可修復來源暫時錯批；系統性 bug 則複檢仍紅→升級）。
        val_bad = None
        if col_name == "stock_price" and latest is not None:
            val_bad = _value_sanity_bad(col, latest, flt)
            if val_bad > _VALUE_BAD_MAX:
                problems.append(f"值合理性異常 {val_bad} 筆（OHLC 超出範圍/零價卻有量）")
        if check_count < eff_min:
            if median is not None and eff_min > min_count:
                problems.append(f"筆數 {check_count} < 門檻 {eff_min}（近{_ADAPT_WINDOW}日中位 {median}×{_ADAPT_RATIO}）")
            else:
                problems.append(f"筆數 {check_count} < 預期 {eff_min}")

        if problems:
            fail_list.append(f"❌ {col_name}: " + "；".join(problems))
        else:
            hint = f"（門檻{eff_min}｜中位{median}）" if median is not None else ""
            if val_bad is not None:
                hint += f" 值檢✓（{val_bad} 異常）" if val_bad else " 值檢✓"
            ok_list.append(f"✅ {col_name}: {check_count} 筆 @ {check_date} {hint}".rstrip())

    return ok_list, fail_list


def send_line_report(ok_list: list[str], fail_list: list[str]):
    """透過 LINE 發送完整度檢查報告"""
    try:
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        from dotenv import load_dotenv
        load_dotenv(str(project_root / ".env"))
        from src.alerts.line_notifier import LineNotifier

        notifier = LineNotifier()
        if not notifier.enabled:
            log.warning("LINE 通知未設定，跳過報告")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")

        if not fail_list:
            msg = f"📊 {today_str} 資料完整度檢查\n✅ 全部正常 ({len(ok_list)} 項)"
        else:
            msg = f"⚠️ {today_str} 資料完整度異常\n"
            msg += f"正常: {len(ok_list)} 項\n異常: {len(fail_list)} 項\n\n"
            for f in fail_list:
                msg += f + "\n"

        notifier.send(msg)
        log.info("LINE 報告已發送")
    except Exception as e:
        log.error(f"LINE 報告發送失敗: {e}")


# ─── 自癒（P1）─────────────────────────────────────
#
# 設計原則：
#   1. 只自癒「補資料」類（冪等、可逆、低風險）；系統級根因（時區/pipeline停擺）不自動處理，直接升級人工。
#   2. allowlist：只執行下列預定義動作，不跑任意命令。
#   3. 有界：每失敗一次修復；自癒前後各 check 一次；仍失敗才升級。

import subprocess
from pathlib import Path as _Path

# 補充表 collection → ALL_SYNCS key（可同進程呼叫 sync 函式修復）
_COLL_TO_SYNC = {
    "margin_purchase_short_sale": "margin_trading",
    "day_trading_targets": "day_trading",
    "securities_lending": "securities_lending",
    "after_hours_trading": "after_hours",
    "odd_lot_trading": "odd_lot",
    "major_news": "major_news",
    "punished_stocks": "punish",
    "foreign_top20": "foreign_top20",
    "etf_dca_rank": "etf_rank",
    "margin_suspension": "margin_suspension",
}


def _reference_day(db):
    """參考交易日 = 各表最新日的「最大值」（上限今天）。回 datetime.date 或 None。

    不可只用 stock_price 自己 —— 那是循環參照：當日股價整批沒下載時，ref 跟著退回昨天，
    於是 (1) 檢查拿「昨天(完整)」自我比對 → 誤報「全部正常」；(2) heal 也會去補昨天
    （已完整的那天）→ 今天永遠補不到。2026-07-16 實際踩過：20:00 時周邊表已是 07-16、
    stock_price 仍停 07-15，卻報全正常、heal 空轉。
    周邊表(融資/當沖/零股/盤後…)由 17:30 openapi_sync 每交易日更新，可當真相錨。
    check_integrity 與 run_heal 共用本函式，確保「判定的日子」與「補的日子」一致。"""
    today = datetime.now().date()
    cands = []
    for cn in TABLE_CHECKS:
        doc = _latest_date_doc(db[cn], _MARKET_FILTER if cn == "stock_price" else {})
        d = _to_date(doc["date"]) if doc else None
        if d is not None and d <= today:      # 上限今天，防某表有未來日汙染參考日
            cands.append(d)
    return max(cands) if cands else None


def _fail_collection(msg: str):
    """從失敗字串抽 collection 名；停擺/時區類回 None（不可自癒）。
    註：collection 名可能含數字（如 foreign_top20），故 [a-z0-9_]+。"""
    import re
    m = re.match(r"❌\s*([a-z0-9_]+):", msg)
    return m.group(1) if m else None


def _run_script(argv: list, timeout: int = 1800) -> str:
    """在專案根跑 allowlist 內的腳本，回 'ok'/'ERR:...'。"""
    root = _Path(__file__).parent.parent
    try:
        r = subprocess.run([sys.executable] + argv, cwd=str(root),
                           capture_output=True, text=True, timeout=timeout)
        return "ok" if r.returncode == 0 else f"ERR:rc={r.returncode} {r.stderr[-120:]}"
    except subprocess.TimeoutExpired:
        return "ERR:timeout"
    except Exception as e:
        return f"ERR:{e}"


def run_heal(db, fail_list: list) -> tuple[list, list]:
    """對 fail_list 逐項自癒。回 (actions, escalated)。
    actions = [(描述, 結果)]；escalated = 不可自癒、需人工的失敗字串。"""
    ref = _reference_day(db)
    ref_ymd = ref.strftime("%Y%m%d") if ref else None
    ref_dash = ref.strftime("%Y-%m-%d") if ref else None
    actions, escalated = [], []

    for f in fail_list:
        coll = _fail_collection(f)
        if coll is None:                       # 時區 / pipeline 停擺 → 不自癒
            escalated.append(f)
            continue
        if not ref_ymd:
            escalated.append(f + "（無參考日，無法自癒）")
            continue

        if coll == "stock_price":
            r = _run_script(["scripts/backfill_by_date.py", "--date", ref_ymd, "--apply"])
            actions.append((f"stock_price → backfill_by_date {ref_ymd}", r))
        elif coll == "stock_factors":
            r = _run_script(["scripts/parallel_factor_calculation.py", "--workers", "4",
                             "--start-date", ref_dash, "--end-date", ref_dash], timeout=2400)
            actions.append((f"stock_factors → factor_calc {ref_dash}", r))
        elif coll == "institutional_flow":
            r = _run_script(["scripts/twse_daily_update.py", "--no-tpex", "--no-peratio"])
            actions.append(("institutional_flow → twse_daily_update", r))
        elif coll in _COLL_TO_SYNC:            # 補充表：同進程呼叫 sync 函式
            key = _COLL_TO_SYNC[coll]
            try:
                ALL_SYNCS[key](db)
                actions.append((f"{coll} → sync_{key}", "ok"))
            except Exception as e:
                actions.append((f"{coll} → sync_{key}", f"ERR:{e}"))
        else:
            escalated.append(f + "（無對應自癒動作）")

    return actions, escalated


def send_heal_report(orig_fail, actions, escalated, final_ok, final_fail):
    """自癒後的 LINE 報告：修復了什麼、升級了什麼、是否仍有殘留。"""
    try:
        # 與 send_line_report 一致：補專案根到 sys.path（否則 No module named 'src'）＋
        # 載入 .env（否則 LineNotifier 拿不到 token → 「LINE 未設定」靜默跳過）。
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        from dotenv import load_dotenv
        load_dotenv(str(project_root / ".env"))
        from src.alerts.line_notifier import LineNotifier
        notifier = LineNotifier()
        if not notifier.enabled:
            log.warning("LINE 未設定，跳過自癒報告"); return
        d = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not final_fail:
            msg = (f"🔧 {d} 資料自癒完成 ✅\n"
                   f"原 {len(orig_fail)} 項異常，已全數修復。\n"
                   + "\n".join(f"• {a}：{r}" for a, r in actions))
        else:
            msg = (f"🚨 {d} 自癒後仍有異常，需人工介入\n"
                   f"殘留 {len(final_fail)} 項：\n"
                   + "\n".join(f"• {f}" for f in final_fail))
            if actions:
                msg += "\n\n已嘗試自癒：\n" + "\n".join(f"• {a}：{r}" for a, r in actions)
            if escalated:
                msg += "\n\n直接升級（系統級根因，未自動處理）：\n" + "\n".join(f"• {e}" for e in escalated)
            msg += "\n\n處理見 docs/架構規劃/規劃-運維手冊-完整度異常處理.md"
        notifier.send(msg)
        log.info("自癒報告已發送")
    except Exception as e:
        log.error(f"自癒報告發送失敗: {e}")


# ─── 心跳（C · 看門狗基礎）─────────────────────────
#
# 整套 P0–P3 都假設 21:00 的 job「會跑」。若它靜默停了（像當初時區 bug 讓東西在
# 錯的時間跑），沒有任何機制會發現「檢查本身沒執行」。故每次檢查完成寫一枚心跳，
# 由獨立的 watchdog.py 比對「上次執行是否落在應執行的排程窗內」。

def _write_heartbeat(db, status: str, ok: int, fail: int):
    """記錄本次完整度檢查已執行（system_heartbeat 集合，_id='integrity'）。
    另可選：若設 env HEALTHCHECK_URL，成功時 ping 外部（healthchecks.io 之類），
    達成『連本機 cron 都死了也有人知道』的真・外部看門狗。"""
    try:
        db.system_heartbeat.update_one(
            {"_id": "integrity"},
            {"$set": {"last_run": datetime.now(), "status": status,
                      "ok": ok, "fail": fail}},
            upsert=True,
        )
    except Exception as e:
        log.warning(f"心跳寫入失敗: {e}")
    url = os.getenv("HEALTHCHECK_URL", "").strip()
    if url and not fail:  # 只在全綠時 ping；有殘留異常不 ping → 外部服務也會告警
        try:
            requests.get(url, timeout=5)  # 外部 healthcheck 服務憑證正常，保留 TLS 驗證
        except Exception:
            pass


# ─── 主程式 ─────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TWSE OpenAPI 補充資料同步")
    parser.add_argument("--only", help="只執行指定項目（逗號分隔）", default="")
    parser.add_argument("--check-only", action="store_true",
                        help="只做完整度檢查，不下載資料")
    parser.add_argument("--heal", action="store_true",
                        help="完整度檢查 → 自動修復可補項 → 再檢查 → 仍失敗才升級告警")
    args = parser.parse_args()

    client = MongoClient("localhost", 27017)
    db = client["tw_stock_analysis"]

    if args.heal:
        print("=" * 60)
        print(f"  資料完整度檢查 + 自癒  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        ok_list, fail_list = check_integrity(db)
        for item in ok_list + fail_list:
            print(f"  {item}")
        if not fail_list:
            print(f"\n  ✅ 全部正常 ({len(ok_list)} 項)")
            send_line_report(ok_list, fail_list)
            _write_heartbeat(db, "ok", len(ok_list), 0)
            return
        print(f"\n  ⚠️ {len(fail_list)} 項異常 → 嘗試自癒…")
        actions, escalated = run_heal(db, fail_list)
        for a, r in actions:
            print(f"    🔧 {a}：{r}")
        for e in escalated:
            print(f"    🚨 升級（不自癒）：{e}")
        print("\n  ── 自癒後複檢 ──")
        ok2, fail2 = check_integrity(db)
        for item in ok2 + fail2:
            print(f"  {item}")
        if fail2:
            print(f"\n  🚨 自癒後仍 {len(fail2)} 項異常，需人工")
        else:
            print(f"\n  ✅ 自癒成功，全部正常")
        send_heal_report(fail_list, actions, escalated, ok2, fail2)
        _write_heartbeat(db, "healed" if not fail2 else "need_human",
                         len(ok2), len(fail2))
        return

    if args.check_only:
        # 只做完整度檢查
        print("=" * 60)
        print(f"  資料完整度檢查")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        ok_list, fail_list = check_integrity(db)
        for item in ok_list:
            print(f"  {item}")
        for item in fail_list:
            print(f"  {item}")
        print()
        if fail_list:
            print(f"  ⚠️ {len(fail_list)} 項異常")
        else:
            print(f"  ✅ 全部正常 ({len(ok_list)} 項)")
        send_line_report(ok_list, fail_list)
        _write_heartbeat(db, "checked", len(ok_list), len(fail_list))
        return

    targets = ALL_SYNCS
    if args.only:
        keys = [k.strip() for k in args.only.split(",")]
        targets = {k: v for k, v in ALL_SYNCS.items() if k in keys}

    print("=" * 60)
    print(f"  TWSE OpenAPI 補充資料同步")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  項目: {len(targets)} 個")
    print("=" * 60)

    total = 0
    success = 0
    failed_names = []
    for name, func in targets.items():
        try:
            count = func(db)
            total += count
            if count > 0:
                success += 1
        except Exception as e:
            log.error(f"  {name} 失敗: {e}")
            failed_names.append(name)

    print()
    print("=" * 60)
    print(f"  完成！成功: {success}/{len(targets)}  總筆數: {total}")
    print("=" * 60)

    # 下載完成後自動做完整度檢查
    print()
    log.info("執行資料完整度檢查...")
    ok_list, fail_list = check_integrity(db)
    for item in ok_list + fail_list:
        log.info(f"  {item}")

    # 發送 LINE 報告
    send_line_report(ok_list, fail_list)


if __name__ == "__main__":
    main()
