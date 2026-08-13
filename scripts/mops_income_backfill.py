#!/usr/bin/env python3
"""從 MOPS 公開資訊觀測站補 financial_statement_detail 缺的季度損益資料。

為什麼需要(2026-08-13):
    FinMind 配額長期用盡(見 finmind-quota-chronically-exhausted),缺季資料
    永遠補不進來 → fundamental_factors.net_income_ttm 缺 4360 列 → roe 覆蓋率
    卡在 83%,quality_roe_pit 過不了 IC 的 85% 閘門。

    但其中 **58% 的 TTM 窗落在上市前**,MOPS 這個權威來源同樣沒有 ——
    那是資料不存在,不是漏抓。本腳本只補剩下 42%「上市後仍缺」的部分。

    MOPS 免費、無配額,是 FinMind 之外的合理替代。

🔴 兩個必須明確處理的陷阱(都已實測確認,見 sanity_check):

  1. **單位是仟元**。MOPS 的數字要 ×1000 才對得上 FinMind 的元。
  2. **每一季都是「年初至今累計」,不是單季**。這與完整版 t164sb04 口徑不同,
     踩過一次:實測台積電 112Q3,t163sb04 給 599,461,316 仟元,但真實單季是
     210,795,274 仟元 —— 599.46 億正好是 Q1+Q2+Q3 的和。直接寫入會讓 Q2 灌水
     約 2 倍、Q3 約 3 倍、Q4 約 3.5 倍,而且不會有任何錯誤訊息。
     本腳本一律以「本季累計 − 上季累計」差分回推單季(Q1 累計即單季)。
     這個特性由 sanity_check 每次啟動時實測驗證,口徑一變就中止。

⚠ 對政府站要客氣:預設每次請求間隔 3 秒、帶正常 User-Agent。台銀的免費 CSV
   就是被 bot 挑戰擋死的(見 bot-fx-source-dead-finmind),別重蹈覆轍。

用法:
    python3 scripts/mops_income_backfill.py                 # dry-run
    python3 scripts/mops_income_backfill.py --apply
    python3 scripts/mops_income_backfill.py --apply --limit 50
"""
import argparse
import io
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import urllib3
from pymongo import MongoClient, UpdateOne

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_URI = "mongodb://localhost:27017/"
DB_NAME = "tw_stock_analysis"
# 用 t163sb04(簡明綜合損益表)而非 t164sb04(完整版),原因:
#   ① t164sb04 是「單一公司單季」,且對不少公司只有 Q2/Q4 —— 實測 1294/1563/1587
#      需要的 Q1/Q3 全部查無,但 t163sb04 有。
#   ② t163sb04 一次回傳**該季全市場**(實測上櫃 110Q1 共 750 家)的完整欄位,
#      請求數從「檔數×季數」降到「季數×市場數」,約 1268 → 100,對政府站也友善得多。
URL = "https://mopsov.twse.com.tw/mops/web/ajax_t163sb04"   # 簡明綜合損益表(全市場)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DELAY = 3.0
COL = "financial_statement_detail"

# MOPS 中文列名 → FinMind 的 type 名(下游 build_fundamental_factors 認這個)
LABELS = {
    "IncomeAfterTaxes": ("本期淨利（淨損）", "本期淨利(淨損)"),
    "Revenue": ("營業收入合計", "收入合計"),
}

QEND = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def qdate(year, q):
    m, d = QEND[q]
    return datetime(year, m, d)


COL_ID = "公司 代號"

# 同一個 TYPEK 的回應裡有多張子表,各業別用不同範本、欄名不同。
# 實測 sii 114Q1 共 7 張:一般業 1024 家用「本期淨利（淨損）」,但銀行(表1,10家)
# 與金控/保險(表4,13家)用「本期**稅後**淨利（淨損）」—— 只認前者會整張跳過,
# 149 檔金融保險證券全部漏掉(中信金 2891 就在表4)。
NI_COLS = ("本期淨利（淨損）", "本期稅後淨利（淨損）")
# 收入側各業別差異更大:一般業「營業收入」、銀行/金控「淨收益」、
# 其他「收益」或「收入」。順序即優先序。
REV_COLS = ("營業收入", "淨收益", "收益", "收入")


def fetch_market(roc_year, season, typek, session):
    """抓該季該市場的全部公司,回傳 {stock_id: {type: 仟元值}}。查無回 {}。"""
    r = session.post(URL, data={
        "encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1",
        "queryName": "co_id", "inpuType": "co_id", "TYPEK": typek,
        "isnew": "false", "co_id": "2330", "year": str(roc_year),
        "season": "%02d" % season}, headers=UA, timeout=90, verify=False)
    r.encoding = "utf-8"
    if "查無所需資料" in r.text or len(r.text) < 20000:
        return {}
    out = {}
    for t in pd.read_html(io.StringIO(r.text)):
        cols = [str(c) for c in t.columns]
        if COL_ID not in cols:
            continue
        ni_col = next((c for c in NI_COLS if c in cols), None)
        if ni_col is None:
            continue                      # 這張表沒有可用的淨利欄(例如目錄小表)
        rev_col = next((c for c in REV_COLS if c in cols), None)
        t.columns = cols
        for _, row in t.iterrows():
            sid = str(row[COL_ID]).strip()
            if len(sid) != 4 or not sid.isdigit():
                continue
            rec = {}
            for key, col in (("IncomeAfterTaxes", ni_col), ("Revenue", rev_col)):
                if col is None:
                    continue
                v = str(row.get(col, "")).replace(",", "").strip()
                if v and v not in ("--", "nan", ""):
                    try:
                        rec[key] = float(v)
                    except ValueError:
                        pass
            if rec:
                out[sid] = rec
    return out


def sanity_check(session):
    """驗證單位(仟元)與「累計制」是否成立 —— 任一改變都會靜默寫壞資料。"""
    q2 = fetch_market(112, 2, "sii", session)
    time.sleep(DELAY)
    q3 = fetch_market(112, 3, "sii", session)
    if not q2.get("2330") or not q3.get("2330"):
        return None, "自檢無法進行:台積電 112Q2/Q3 取不到"
    c2 = q2["2330"]["IncomeAfterTaxes"]
    c3 = q3["2330"]["IncomeAfterTaxes"]
    single_q3 = (c3 - c2) * 1000
    expect = 210_795_274_000
    ok = abs(single_q3 - expect) / expect < 0.02
    msg = (f"自檢:全市場表載入 {len(q3)} 家;台積電 112 年累計 Q2={c2:,.0f} "
           f"Q3={c3:,.0f} 仟元 → 差分單季 Q3 = {single_q3:,.0f}"
           f"(期望 {expect:,})→ {'✅ 累計制與單位皆正確' if ok else '🔴 不符'}")
    return ok, msg


def local_quarter(db, sid, dt, typ):
    d = db[COL].find_one({"stock_id": sid, "date": dt, "type": typ})
    return d["value"] if d else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="最多處理幾個 (季,市場)")
    ap.add_argument("--delay", type=float, default=DELAY)
    ap.add_argument("--sector", default=None,
                    help="改為依產業補洞(正規表示式比對 industry_category),"
                         "例如 --sector '金融|保險|證券'。這批公司多半連一筆損益都沒有,"
                         "無法從 fundamental_factors 的 null 反推,故需另一種取樣方式")
    ap.add_argument("--from-year", type=int, default=2013,
                    help="--sector/--symbols 模式的起始年(預設 2013,配合 IFRS 後的資料深度)")
    ap.add_argument("--symbols", default=None,
                    help="直接指定代號(逗號分隔),逐季掃該檔缺哪些。"
                         "用於零星補洞,例如 FinMind 排除下市股後仍落後的個位數檔")
    args = ap.parse_args()

    db = MongoClient(DB_URI)[DB_NAME]
    session = requests.Session()

    ok_unit, msg = sanity_check(session)
    print(msg)
    if not ok_unit:
        print("MOPS 單位與預期不符,中止 —— 硬寫會產生看似合理的錯誤資料。")
        return
    time.sleep(args.delay)

    def typek_of(t):
        return {"tpex": "otc", "emerging": "rotc"}.get(t, "sii")

    market = {d["stock_id"]: typek_of(d.get("type"))
              for d in db.taiwan_stock_info.find({}, {"stock_id": 1, "type": 1})}

    if args.sector or args.symbols:
        # 依產業或指定代號補洞。這批(典型是金融保險證券)多半在 financial_statement_detail
        # 連一筆都沒有,所以 fundamental_factors 也生不出列 —— 無法用「net_income_ttm
        # 為 null」反推,必須直接以「該檔該季有沒有資料」為準逐季掃。
        if args.symbols:
            syms = [x.strip() for x in args.symbols.split(",") if x.strip()]
        else:
            syms = [d["stock_id"] for d in db.taiwan_stock_info.find(
                {"industry_category": {"$regex": args.sector}, "security_type": "Stock"},
                {"stock_id": 1})]
        latest_year = db.stock_price.find_one(sort=[("date", -1)])["date"].year
        need = {}
        for sid in syms:
            p = db.stock_price.find_one({"symbol": sid}, sort=[("date", 1)])
            if not p:
                continue
            for y in range(max(args.from_year, p["date"].year), latest_year + 1):
                for q in (1, 2, 3, 4):
                    dt = qdate(y, q)
                    if dt < p["date"] or dt > datetime.now():
                        continue          # 上市前 / 未來季,來源不會有
                    if local_quarter(db, sid, dt, "IncomeAfterTaxes") is None:
                        need.setdefault((y, q, market.get(sid, "sii")), set()).add(sid)
        print(f"{'--symbols' if args.symbols else '--sector'} :{len(syms)} 檔,"
              f"需補 {sum(len(v) for v in need.values())} 個(股票,季)")
        return run(db, session, need, args)

    # 找「上市後仍缺」的 (股票, 季);上市前的任何來源都沒有,不必浪費請求
    need = {}
    for r in db.fundamental_factors.find({"net_income_ttm": None},
                                         {"stock_id": 1, "period_end": 1}):
        sid, pe = str(r["stock_id"]), r["period_end"]
        p = db.stock_price.find_one({"symbol": sid}, sort=[("date", 1)])
        if not p or p["date"] > pe - timedelta(days=400):
            continue
        y, q = pe.year, (pe.month - 1) // 3 + 1
        for k in range(4):
            qq, yy = q - k, y
            while qq <= 0:
                qq += 4
                yy -= 1
            if not local_quarter(db, sid, qdate(yy, qq), "IncomeAfterTaxes"):
                need.setdefault((yy, qq, market.get(sid, "sii")), set()).add(sid)
    return run(db, session, need, args)


def run(db, session, need, args):
    """共用的抓取/差分/寫入流程。兩種取樣模式(缺 TTM 反推 vs 依產業掃)共用。"""
    keys = sorted(need)
    if args.limit:
        keys = keys[:args.limit]
    n_pairs = sum(len(need[k]) for k in keys)
    print(f"需補 {n_pairs} 個(股票,季),歸併為 {len(keys)} 次請求"
          f"(季×市場),預估 {len(keys) * args.delay / 60:.0f} 分鐘")
    if not args.apply:
        for k in keys[:8]:
            print(f"    {k[0]}Q{k[1]} {k[2]}: {len(need[k])} 檔")
        print("(dry-run,未寫入。加 --apply 才會實際抓取與更新)")
        return

    ops, stats = [], {"ok": 0, "miss": 0, "nodata": 0}
    cache = {}

    def cum(y, q, tk):
        """該季的年初至今累計值(帶快取,同一季不重複請求)。"""
        k = (y, q, tk)
        if k not in cache:
            cache[k] = fetch_market(y - 1911, q, tk, session)
            time.sleep(args.delay)
        return cache[k]

    for i, (y, q, tk) in enumerate(keys, 1):
        want = need[(y, q, tk)]
        data = cum(y, q, tk)
        if not data:
            stats["nodata"] += len(want)
            print(f"  [{i}/{len(keys)}] {y}Q{q} {tk}: 整季查無")
            continue
        prev = cum(y, q - 1, tk) if q > 1 else {}    # Q1 的累計即單季

        got = 0
        for sid in want:
            rec = data.get(sid)
            if not rec:
                stats["miss"] += 1
                continue
            dt = qdate(y, q)
            for typ, key in (("IncomeAfterTaxes", "IncomeAfterTaxes"), ("Revenue", "Revenue")):
                cur = rec.get(key)
                if cur is None:
                    continue
                if q > 1:
                    pv = prev.get(sid, {}).get(key)
                    if pv is None:
                        continue          # 湊不齊上一季就無法差分,寧可不寫
                    val = cur - pv
                else:
                    val = cur
                # 只補「這個 type 本身也缺」的:need 是以 IncomeAfterTaxes 有無決定的,
                # 但同一季的 Revenue 可能已存在(來自 FinMind)。不加這道檢查會連帶
                # 覆寫它 —— 2026-08-13 首次跑 --sector 時就這樣「更新 585 筆」。
                # 兩邊都源自官方申報,值本身不算錯,但金融業的 MOPS 欄位是「淨收益」
                # 而 FinMind 是「Revenue」,語意未必等價,不該無聲替換。
                if local_quarter(db, sid, dt, typ) is not None:
                    continue
                ops.append(UpdateOne(
                    {"stock_id": sid, "date": dt, "type": typ},
                    {"$set": {"value": val * 1000, "origin_name": f"{typ}(MOPS差分)",
                              "source": "MOPS", "updated_at": datetime.now()}},
                    upsert=True))
                if typ == "IncomeAfterTaxes":
                    got += 1
                    stats["ok"] += 1
        print(f"  [{i}/{len(keys)}] {y}Q{q} {tk}: 需 {len(want)} 檔 → 取得 {got} "
              f"(該季表含 {len(data)} 家)")

    if ops:
        res = db[COL].bulk_write(ops, ordered=False)
        print(f"寫入:upsert {res.upserted_count} / 更新 {res.modified_count}")
    print(f"完成:成功 {stats['ok']}、該季表無該檔 {stats['miss']}、整季查無 {stats['nodata']}")
    print("接著跑:python3 scripts/backfill_fundamental_income.py --apply")


if __name__ == "__main__":
    main()
