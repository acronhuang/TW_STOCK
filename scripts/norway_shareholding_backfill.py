#!/usr/bin/env python3
"""
大戶持股歷史回補（norway.twsthr.info，一次性）
================================================
來源：https://norway.twsthr.info/StockHolders.aspx?stock=XXXX
      每檔一頁，約 170 週（2023-03 起）、296KB。

為什麼需要這支（不能只靠 tdcc_shareholding_sync.py）：
  集保開放資料 id=1-5 **只提供當週**一個資料日，沒有歷史可回補。
  shareholding 因此只能從 2026-07-07 首跑當天起往前累積 —— 漏掉的週永久遺失，
  且在累積夠週數前，大戶佔比既畫不成線、也無法回測其預測力。
  norway 是目前唯一有歷史的來源，故以此回補一次，之後仍由 TDCC 每週接續。

欄位對照（norway → shareholding）：
  >1000張大股東持有百分比 → big_pct       （千張大戶佔比，核心欄位）
  >1000張人數             → big_holders
  >400張大股東持有百分比  → big400_pct
  總股東人數              → total_holders
  收盤價                  → close_price   （norway 額外提供，僅供核對）
  retail_pct（散戶<5張）  → **無**。norway 只統計 400 張以上級距。
                            歷史列不含 retail_pct，僅 TDCC 起算日後才有。

與 TDCC 的關係（重要）：
  TDCC 為權威來源，本腳本**只填空缺、不覆蓋**（$setOnInsert）。
  兩者同一資料日會有 ~0.01–0.03pp 差異：TDCC CSV 各級距百分比已四捨五入到 2 位，
  tdcc_shareholding_sync 是相加故累積誤差；norway 以原始股數重算。差異可忽略。

用法：
    python3 scripts/norway_shareholding_backfill.py --stocks 2330,2317 --dry-run
    python3 scripts/norway_shareholding_backfill.py --limit 50      # 先試跑 50 檔
    python3 scripts/norway_shareholding_backfill.py                 # 全市場回補
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from datetime import datetime

import requests
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

URL = "https://norway.twsthr.info/StockHolders.aspx?stock={sym}"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# 一列 = 資料日期 + 後續 12 欄（見模組 docstring 欄位對照）
_ROW_FIELDS = 12
_DATE_RE = re.compile(r"^20\d{6}$")
_SYMBOL_RE = re.compile(r"[0-9]{4,6}[A-Z]?")   # 台股代號：4–6 位數字，債券ETF 等可帶單一字尾字母
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

# norway 是個人維護的免費站，務必節流；勿調低於 1 秒。
DEFAULT_SLEEP = 1.2


def fetch(sym: str, retries: int = 3, timeout: int = 60) -> str:
    """抓單檔頁面，指數退避重試（norway 偶有慢回應）。"""
    last = None
    for i in range(retries):
        try:
            r = requests.get(URL.format(sym=sym), timeout=timeout, headers=UA)
            r.raise_for_status()
            return r.content.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - 連線層各種例外一律重試
            last = e
            if i < retries - 1:
                time.sleep(2 * (2 ** i))
    raise RuntimeError(f"{sym} 抓取失敗（{retries} 次）：{last}")


def _cells(text: str) -> list[str]:
    out = []
    for c in _CELL_RE.findall(text):
        t = _TAG_RE.sub("", c)
        out.append(html.unescape(t).replace("\xa0", " ").strip())
    return out


def _num(s: str):
    s = s.replace(",", "").strip()
    if not s or s in ("-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse(text: str) -> dict:
    """回傳 {datetime: {big_pct, big_holders, big400_pct, total_holders, close_price}}。

    不依賴 <tr> 邊界：該頁 HTML 的列標籤不完整（多個資料日會落在同一個 <tr> 內），
    故改為攤平所有儲存格後，掃描 yyyymmdd 並取其後 12 欄。

    同一資料日在頁面出現 3 次（歷史表、週比較表頭、底部「持股張數分級」表），
    後兩者欄位排列不同 —— 若不設防會抓到分級表的數字（2330 曾解析出
    千張大戶 1.44%、收盤 1.06，實為 85.02% / 2415）。故雙重防護：
      1. 只取第一次出現（歷史表在文件最前）；
      2. 驗證不變量「集保總張數 ÷ 總股東人數 = 平均張數/人」，分級表不滿足。
    """
    cells = _cells(text)
    out = {}
    for i, c in enumerate(cells):
        if not _DATE_RE.match(c):
            continue
        row = cells[i + 1: i + 1 + _ROW_FIELDS]
        if len(row) < _ROW_FIELDS:
            continue
        total_shares = _num(row[0])
        total_holders = _num(row[1])
        avg_lots = _num(row[2])
        big400_pct = _num(row[4])
        big_holders = _num(row[9])
        big_pct = _num(row[10])
        close_price = _num(row[11])
        # 大戶佔比是核心欄位，缺了這列就沒意義；同時濾掉誤判的日期字串
        if big_pct is None or big400_pct is None:
            continue
        # 結構驗證：確認抓到的是歷史表而非同頁其他表
        if not (total_shares and total_holders and avg_lots):
            continue
        if abs(total_shares / total_holders - avg_lots) > max(0.05, avg_lots * 0.02):
            continue
        if not (0 <= big_pct <= 100 and 0 <= big400_pct <= 100):
            continue
        try:
            d = datetime.strptime(c, "%Y%m%d")
        except ValueError:
            continue
        if d in out:          # 首次出現＝歷史表，後續重複一律忽略
            continue
        out[d] = {
            "big_pct": round(big_pct, 2),
            "big_holders": int(big_holders) if big_holders is not None else None,
            "big400_pct": round(big400_pct, 2),
            "total_holders": int(total_holders) if total_holders is not None else None,
            "close_price": close_price,
        }
    return out


def symbols(db, limit: int | None) -> list[str]:
    """回補對象＝集保有股權資料 ∩ 有股價（可畫圖）的真實個股。

    刻意不用 taiwan_stock_info 交集（dashboard/pages/charts.py 的做法）：該表僅 3453 筆
    且未跟上新掛牌，連 0050 都不在裡面（stock_price 有 2552 筆價格卻查無此表），
    用它當清單會漏掉台灣最大的 ETF。shareholding 的 stock_id 來自 TDCC 全市場，較可靠。

    另濾掉 stock_price 內混入的非個股代號（產業指數 Electronic/Food/TPEx、
    特別股 2887Z1）—— 這些在 norway 沒有頁面，爬了只是白打人家的站。
    """
    tdcc = set(db.shareholding.distinct("stock_id"))
    have = set(db.stock_price.distinct("symbol", {"symbol": {"$ne": "TAIEX"}}))
    syms = sorted(s for s in (tdcc & have) if _SYMBOL_RE.fullmatch(s))
    return syms[:limit] if limit else syms


def main():
    ap = argparse.ArgumentParser(description="大戶持股歷史回補（norway）")
    ap.add_argument("--stocks", help="逗號分隔股號；預設全市場")
    ap.add_argument("--limit", type=int, help="只跑前 N 檔（試跑用）")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help=f"每檔間隔秒數（預設 {DEFAULT_SLEEP}，勿低於 1）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)[os.getenv("MONGODB_DATABASE", "tw_stock_analysis")]
    col = db.shareholding
    syms = [s.strip() for s in args.stocks.split(",")] if args.stocks else symbols(db, args.limit)

    print(f"回補 norway 大戶持股歷史｜{len(syms)} 檔｜間隔 {args.sleep}s"
          f"｜預估 {len(syms) * args.sleep / 60:.0f} 分鐘")
    if not args.dry_run:
        col.create_index([("stock_id", ASCENDING), ("date", DESCENDING)], unique=True)

    ins = skipped = failed = 0
    for n, sym in enumerate(syms, 1):
        try:
            recs = parse(fetch(sym))
        except Exception as e:  # noqa: BLE001 - 單檔失敗不應中斷整批回補
            print(f"  ⚠️ {sym} 失敗：{e}")
            failed += 1
            continue
        if not recs:
            print(f"  – {sym} 無歷史資料")
            skipped += 1
            continue

        if args.dry_run:
            ds = sorted(recs)
            x = recs[ds[-1]]
            print(f"  {sym}: {len(recs)} 週（{ds[0]:%Y-%m-%d}～{ds[-1]:%Y-%m-%d}）"
                  f" 最新 千張大戶 {x['big_pct']}%（{x['big_holders']}人）"
                  f" 400張+ {x['big400_pct']}% 收盤 {x['close_price']}")
        else:
            # $setOnInsert：TDCC 已寫入的資料日維持原值，本腳本只填空缺
            ops = [UpdateOne(
                {"stock_id": sym, "date": d},
                {"$setOnInsert": {"stock_id": sym, "date": d, "data_source": "NORWAY",
                                  "updated_at": datetime.now(), **x}},
                upsert=True) for d, x in recs.items()]
            res = col.bulk_write(ops, ordered=False)
            ins += res.upserted_count
            if n % 50 == 0 or n == len(syms):
                print(f"  [{n}/{len(syms)}] {sym} 累計新增 {ins} 列")

        time.sleep(args.sleep)

    tail = "（DRY-RUN 未寫入）" if args.dry_run else f"新增 {ins} 列"
    print(f"✅ 完成：{tail}｜無資料 {skipped} 檔｜失敗 {failed} 檔")


if __name__ == "__main__":
    main()
