#!/usr/bin/env python3
"""全市場總表同步（TWSE RWD，免費無配額）—— 取代 FinMind 的兩個 Total 資料集。

  total_margin                   ← MI_MARGN?selectType=MS   信用交易統計
  total_institutional_investors  ← BFI82U                   三大法人買賣金額統計

用法:
  twse_market_totals_sync.py                      同步最近一個交易日
  twse_market_totals_sync.py --date 20260814      指定日
  twse_market_totals_sync.py --backfill 20200102 20260814   區間回填
  twse_market_totals_sync.py --dry-run            只印不寫

為什麼換掉 FinMind
------------------
FinMind 這兩個資料集回 402（配額用盡）已持續 14 天、累積 130 則告警，而資料
其實靠每小時重試 24 次硬撈回來 —— 拿得到但極度浪費配額，且告警疲勞會讓
schedule_alerts 整頁失去意義。實測 TWSE 與 FinMind 同日數值**逐位元相同**
（法人合計 511,271,838,131 完全一致；融資金額差 1000 倍純粹是仟元 vs 元），
故換源不改變任何語意。

🔴 同時修掉一個靜默資料遺失
--------------------------
原 table_config 的 unique_keys 只有 ["date"]，但兩個資料集每日各回 3 列／6 列
（融資/融券/融資金額；六類法人）。同日多列互相覆蓋，**每天只活下來一列，而且
是哪一列隨機**——total_margin 遺失 67%、total_institutional_investors 遺失 83%，
且同一欄 buy 在不同日期代表不同語意，跨日比較毫無意義（影響 2020-01-02 起 6.4 年）。
本腳本以 (date, name) 為鍵，保留全部列。
"""
import sys, json, time, argparse, datetime
import urllib.request
from urllib.error import HTTPError, URLError

from pymongo import MongoClient, UpdateOne, DESCENDING

DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; tw-stock-analysis/1.0)"}

MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d}&selectType=MS&response=json"
INST_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate={d}&type=day&response=json"

# TWSE 項目名 → FinMind 既有 name（保持相容，下游與歷史資料才對得起來）
MARGIN_MAP = {
    "融資(交易單位)": ("MarginPurchase", 1),
    "融券(交易單位)": ("ShortSale", 1),
    "融資金額(仟元)": ("MarginPurchaseMoney", 1000),   # 仟元 → 元
}
INST_MAP = {
    "自營商(自行買賣)": "Dealer_self",
    "自營商(避險)": "Dealer_Hedging",
    "投信": "Investment_Trust",
    "外資及陸資(不含外資自營商)": "Foreign_Investor",
    "外資自營商": "Foreign_Dealer_Self",
    "合計": "total",
}


def _num(s):
    """'32,821,706' → 32821706；空字串/破折號 → 0。"""
    if s is None:
        return 0
    t = str(s).replace(",", "").replace(" ", "").strip()
    if t in ("", "-", "--"):
        return 0
    try:
        return int(float(t))
    except ValueError:
        return 0


def fetch(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError) as e:
            if i == retries - 1:
                return {"stat": f"ERR:{e}"}
            time.sleep(2 * (i + 1))
    return {"stat": "ERR"}


def parse_margin(js, dstr):
    """回 [{date,name,buy,sell,Return,YesBalance,TodayBalance}, ...]（3 列）"""
    out = []
    for t in (js.get("tables") or []):
        for row in (t.get("data") or []):
            if not row:
                continue
            key = str(row[0]).strip()
            if key not in MARGIN_MAP:
                continue
            name, mul = MARGIN_MAP[key]
            out.append({
                "date": dstr, "name": name,
                "buy": _num(row[1]) * mul,
                "sell": _num(row[2]) * mul,
                "Return": _num(row[3]) * mul,
                "YesBalance": _num(row[4]) * mul,
                "TodayBalance": _num(row[5]) * mul,
            })
    return out


def parse_inst(js, dstr):
    """回 [{date,name,buy,sell}, ...]（6 列）"""
    out = []
    for row in (js.get("data") or []):
        if not row:
            continue
        name = INST_MAP.get(str(row[0]).strip())
        if not name:
            continue
        out.append({"date": dstr, "name": name,
                    "buy": _num(row[1]), "sell": _num(row[2])})
    return out


def sync_day(d, dry=False, quiet=False):
    """d: datetime.date。回 (margin列數, inst列數)。非交易日回 (0,0)。"""
    ymd = d.strftime("%Y%m%d")
    dstr = d.strftime("%Y-%m-%d")

    mj = fetch(MARGIN_URL.format(d=ymd))
    ij = fetch(INST_URL.format(d=ymd))
    mrows = parse_margin(mj, dstr) if mj.get("stat") == "OK" else []
    irows = parse_inst(ij, dstr) if ij.get("stat") == "OK" else []

    if not quiet:
        print(f"  {dstr}: margin {len(mrows)} 列 / inst {len(irows)} 列"
              + ("" if (mrows or irows) else "  (非交易日或無資料)"))
    if dry or not (mrows or irows):
        return len(mrows), len(irows)

    now = datetime.datetime.now()
    for coll, rows in (("total_margin", mrows), ("total_institutional_investors", irows)):
        if not rows:
            continue
        c = DB[coll]
        # 🔴 鍵一定要含 name。只用 date 會讓同日各列互相覆蓋（原本的 bug）
        c.create_index([("date", DESCENDING), ("name", 1)], name="date_name")
        c.bulk_write([UpdateOne({"date": r["date"], "name": r["name"]},
                                {"$set": {**r, "updated_at": now,
                                          "source": "twse_rwd"}}, upsert=True)
                      for r in rows], ordered=False)
    return len(mrows), len(irows)


def sanity_check():
    """已知答案對照：2026-08-14 的法人合計買進必須是 511,271,838,131。

    這個數字同時出現在 TWSE 網頁與 FinMind 舊資料，兩個來源獨立吻合，
    可當成解析正確性的錨。對不上就代表欄位順序或單位換算改了，直接中止。
    """
    d = datetime.date(2026, 8, 14)
    ij = fetch(INST_URL.format(d="20260814"))
    rows = parse_inst(ij, "2026-08-14") if ij.get("stat") == "OK" else []
    tot = next((r for r in rows if r["name"] == "total"), None)
    mj = fetch(MARGIN_URL.format(d="20260814"))
    mrows = parse_margin(mj, "2026-08-14") if mj.get("stat") == "OK" else []
    mm = next((r for r in mrows if r["name"] == "MarginPurchaseMoney"), None)

    ok = True
    print("=== 已知答案對照（2026-08-14）===")
    if tot and tot["buy"] == 511271838131 and tot["sell"] == 459609095937:
        print(f"  ✅ 法人合計 買 {tot['buy']:,} / 賣 {tot['sell']:,}")
    else:
        print(f"  🔴 法人合計對不上：{tot}")
        ok = False
    if mm and mm["buy"] == 32821706000 and mm["TodayBalance"] == 547059318000:
        print(f"  ✅ 融資金額 買 {mm['buy']:,} / 今日餘額 {mm['TodayBalance']:,}")
    else:
        print(f"  🔴 融資金額對不上：{mm}")
        ok = False
    print(f"  列數：margin {len(mrows)}（應 3）/ inst {len(rows)}（應 6）")
    if len(mrows) != 3 or len(rows) != 6:
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD，預設最近一個交易日")
    ap.add_argument("--backfill", nargs=2, metavar=("START", "END"), help="YYYYMMDD YYYYMMDD")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-check", action="store_true", help="跳過已知答案對照（不建議）")
    ap.add_argument("--sleep", type=float, default=1.2, help="回填時每日間隔秒數（禮貌性節流）")
    a = ap.parse_args()

    if not a.skip_check:
        if not sanity_check():
            print("🔴 已知答案對照未通過 —— 端點格式可能已變，不寫入。")
            return 1
        print()

    if a.backfill:
        s = datetime.datetime.strptime(a.backfill[0], "%Y%m%d").date()
        e = datetime.datetime.strptime(a.backfill[1], "%Y%m%d").date()
        # 只打交易日，非交易日不必浪費請求
        tds = set(DB.trading_dates.distinct("date"))
        days = []
        cur = s
        while cur <= e:
            if cur.weekday() < 5 and (not tds or cur.strftime("%Y-%m-%d") in tds):
                days.append(cur)
            cur += datetime.timedelta(days=1)
        print(f"回填 {s} ~ {e}，交易日 {len(days)} 天")
        tm = ti = 0
        for i, d in enumerate(days, 1):
            m, n = sync_day(d, a.dry_run, quiet=True)
            tm += m; ti += n
            if i % 50 == 0 or i == len(days):
                print(f"  [{i}/{len(days)}] {d} 累計 margin {tm} / inst {ti}")
            time.sleep(a.sleep)
        print(f"完成：margin {tm} 列 / inst {ti} 列")
        return 0

    d = (datetime.datetime.strptime(a.date, "%Y%m%d").date() if a.date
         else datetime.date.today())
    print(f"同步 {d}")
    m, n = sync_day(d, a.dry_run)
    if a.dry_run:
        print("[dry-run] 未寫入")
    elif not (m or n):
        print("  (無資料 —— 可能是非交易日或當日尚未公布)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
