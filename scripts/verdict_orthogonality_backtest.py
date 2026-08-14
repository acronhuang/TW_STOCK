#!/usr/bin/env python3
"""
verdict 命中率 × 委員正交性回測 —— NFR-QUAL-001 常態 SLI（月度）

用法:
  verdict_orthogonality_backtest.py                 算 + 印 + 寫 verdict_performance 快照
  verdict_orthogonality_backtest.py --dry-run       只算 + 印，不寫 DB
  verdict_orthogonality_backtest.py --alert         破 NFR-QUAL 門檻才寫 schedule_alerts
  verdict_orthogonality_backtest.py --window 20     前瞻交易日數（預設 20）
  verdict_orthogonality_backtest.py --windows 5,10,20   一次跑多視窗（累積用）

純讀 team_analysis / stock_price；寫入 verdict_performance（快照）、verdict_detail（逐筆）
與可選 schedule_alerts。

NFR-QUAL-001 門檻：買進 命中 ≥ 55% 且 均超額 ≥ +1.5%。

⚠️ 命中率基準（2026-08-14 修正，見下）
--------------------------------------
基準 = 同一 P0 日、**分析池的橫斷面平均報酬**（非 0050）。這種基準把市場 beta
構造性移除，是衡量「選股力」而非「擇時力」的正確量尺。

原本 gate 的兩個條件用了不同基準：`均超額` 相對基準算，`方向命中` 卻用絕對漲跌算。
下跌行情中，一檔跌得比池子平均少的股票是正確的相對判斷，卻被記成「沒命中」——
於是 gate 在空頭永遠過不了，與判斷力無關。實測（全樣本，2026-08-14）：

    買進 20 日   絕對命中 45.0%  超額命中 68.6%   期間池均 -4.05%
    買進 10 日   絕對命中 44.7%  超額命中 66.6%   期間池均 -2.08%

改用超額基準**不是放寬**——對賣出側反而更嚴（20 日 66.7% → 52.7%），
兩側同時被重新校準才是基準修正、不是移動球門。
故 gate 改用 `hit`（超額基準），`hit_abs`（絕對）保留為次要指標一併輸出。
"""
import sys, bisect, math, argparse, datetime
from collections import defaultdict, Counter
from pymongo import MongoClient

DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
QUAL_HIT = 0.55      # NFR-QUAL-001 命中率門檻（超額基準）
QUAL_EXCESS = 0.015  # NFR-QUAL-001 超額門檻
MIN_N = 30           # 樣本過小不告警（避免雜訊誤報）
# 買進反動能過濾：排除事前 20 日漲幅最高的這一比例。
# 依據（全樣本 2026-08-14）：買進判斷力隨事前動能單調遞減——
#   事前弱 命中 51.8%/超額 +1.04% ｜ 事前中 48.3%/+0.55% ｜ 事前強 40.6%/+0.75%
#   動能前 10% 更是實質虧損：命中 33.0%、均超額 -1.54%
# 排除前 30% 後 20 日：超額命中 68.6%→77.2%、均超額 +2.18%→+4.10%。
# ⚠️ 此門檻為事後切片（in-sample），僅 34 個獨立分析日、單一空頭區間，
#    尚未經樣本外驗證。故 SLI 同時輸出過濾前後兩組，gate 仍以未過濾為準。
MOM_FILTER_PCT = 0.30
# 委員票種偏態上限：任一委員單一票種佔比超過此值，視為「恆說同一句話」的委員，
# 它不提供資訊只提供噪音。依據：本專案曾有 hermes3:8b 出席 8913 次、84.7% 都投買進，
# 長期無人察覺。此監控就是為了讓同類問題不再靜默。
COMMITTEE_BIAS_MAX = 0.75
COMMITTEE_NULL_MAX = 0.05   # 抽不到票（棄權）比例上限：超過代表回覆格式常態不合規

SYN = [('賣出', ('賣出', '賣', '減碼', '出場', '看空')),
       ('買進', ('買進', '買', '加碼', '進場', '看多')),
       ('持有', ('持有', '觀望', '中立', '不動', '續抱'))]


def to_f(x):
    try:
        return float(str(x))   # 處理 Decimal128（float(Decimal128) 會拋例外）
    except Exception:
        return None


def load_verdicts():
    docs = []
    for d in DB.team_analysis.find({}, {'symbol': 1, 'date': 1, 'final_verdict': 1,
                                        'consensus': 1}):
        if d.get('final_verdict') and d.get('symbol') and isinstance(d.get('date'), datetime.datetime):
            docs.append(d)
    return docs


def price_series(symbols):
    ser = {}
    for s in symbols:
        rows = [(r['date'], to_f(r.get('adj_close'))) for r in
                DB.stock_price.find({'symbol': s, 'adj_close': {'$ne': None}},
                                    {'date': 1, 'adj_close': 1}).sort('date', 1)]
        ser[s] = [(dt, px) for dt, px in rows if px]
    return ser


def fwd_return(ser, sym, vdate, fwd):
    s = ser.get(sym)
    if not s or len(s) < 2:
        return None, None
    ds = [x[0] for x in s]
    i = bisect.bisect_right(ds, vdate) - 1
    if i < 0 or i + fwd >= len(s):
        return None, None
    p0, pN = s[i][1], s[i + fwd][1]
    return (pN / p0 - 1.0, s[i][0]) if p0 else (None, None)


def prior_return(ser, sym, p0d, back):
    """P0 日往前 back 個交易日的報酬(事前動能)。取不到回 None。"""
    s = ser.get(sym)
    if not s or p0d is None:
        return None
    ds = [x[0] for x in s]
    i = bisect.bisect_left(ds, p0d)
    if i >= len(ds) or ds[i] != p0d or i - back < 0:
        return None
    p_prev, p0 = s[i - back][1], s[i][1]
    return (p0 / p_prev - 1.0) if p_prev else None


def compute(fwd):
    docs = load_verdicts()
    ser = price_series(sorted({d['symbol'] for d in docs}))
    for d in docs:
        r, p0d = fwd_return(ser, d['symbol'], d['date'], fwd)
        d['_fwd'], d['_p0'] = r, p0d
    usable = [d for d in docs if d['_fwd'] is not None]

    # 橫斷面基準（同 P0 日、分析池平均）
    by_date = defaultdict(list)
    for d in usable:
        by_date[d['_p0']].append(d['_fwd'])
    bench = {dt: sum(v) / len(v) for dt, v in by_date.items()}
    for d in usable:
        d['_ex'] = d['_fwd'] - bench[d['_p0']]

    # 事前動能(前 20 交易日報酬)。2026-08-13 加,用於控制混淆:
    # 實測 8 月「買進」組事前 20 日 +2.24%、「賣出」組 -4.86%,相差 7.1pp。
    # 若不控制,跌深反彈就足以讓「賣出」組的後續報酬贏過「買進」組,
    # 看起來像「判斷方向相反」,實際是均值回歸而非判斷力問題。
    for d in usable:
        d['_prior'] = prior_return(ser, d['symbol'], d['_p0'], 20)

    def cls(v, rows_in=None):
        """v='買進' 看漲、'賣出' 看跌。hit 用超額基準（與 mean_excess 同基準，
        NFR gate 用它）；hit_abs 用絕對漲跌，僅供對照——兩者的差距方向必然
        與 bench_mean 的正負一致，可當成內建對照組。"""
        rows = rows_in if rows_in is not None else [d for d in usable if d['final_verdict'] == v]
        n = len(rows)
        if not n:
            return {'n': 0}
        fwds = [d['_fwd'] for d in rows]
        exs = [d['_ex'] for d in rows]
        up = (lambda x: x > 0) if v == '買進' else (lambda x: x < 0)
        return {'n': n,
                'mean_ret': sum(fwds) / n, 'median_ret': sorted(fwds)[n // 2],
                'hit': sum(1 for x in exs if up(x)) / n,        # 超額基準（gate）
                'hit_abs': sum(1 for x in fwds if up(x)) / n,   # 絕對基準（對照）
                'mean_excess': sum(exs) / n,
                'median_excess': sorted(exs)[n // 2],
                'bench_mean': (sum(fwds) - sum(exs)) / n,       # 期間池均，解釋兩基準差距
                'excess_pos': sum(1 for x in exs if x > 0) / n,
                'excess_ge_1p5': sum(1 for x in exs if x >= QUAL_EXCESS) / n}

    buy = cls('買進')
    sell = cls('賣出')
    spread = (buy.get('mean_ret', 0) - sell.get('mean_ret', 0)) if buy['n'] and sell['n'] else None

    # 買進反動能過濾（見檔頭 MOM_FILTER_PCT 註解）。標記在 row 上，逐筆明細一併存，
    # 讓網頁能回推「若當初套用過濾會如何」而不必重算。
    buy_rows = [d for d in usable if d['final_verdict'] == '買進' and d.get('_prior') is not None]
    buy_rows.sort(key=lambda d: -d['_prior'])
    n_drop = int(len(buy_rows) * MOM_FILTER_PCT)
    for i, d in enumerate(buy_rows):
        d['_mom_excluded'] = i < n_drop
    kept = buy_rows[n_drop:]
    buy_filtered = cls('買進', kept) if len(kept) >= MIN_N else {'n': len(kept)}

    # 委員正交性
    V = {'買進': 1, '持有': 0, '賣出': -1}
    mv = defaultdict(dict)
    seat = Counter()      # 出席次（含抽不到票）
    null_v = Counter()    # 抽不到票次數 —— mv 只收得到有效票，棄權會靜默消失
    for d in docs:
        for v in (d.get('consensus') or {}).get('votes') or []:
            if not v.get('model'):
                continue
            seat[v['model']] += 1
            if v.get('vote') in V:
                mv[str(d['_id'])][v['model']] = V[v['vote']]
            else:
                null_v[v['model']] += 1
    models = sorted({m for x in mv.values() for m in x})
    pairs = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            xs, ys = [], []
            for x in mv.values():
                if models[i] in x and models[j] in x:
                    xs.append(x[models[i]]); ys.append(x[models[j]])
            if len(xs) >= 5:
                n = len(xs)
                agree = sum(1 for k in range(n) if xs[k] == ys[k]) / n
                mx, my = sum(xs) / n, sum(ys) / n
                cov = sum((xs[k] - mx) * (ys[k] - my) for k in range(n))
                sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
                corr = cov / (sx * sy) if sx and sy else None
                pairs.append({'a': models[i], 'b': models[j], 'n': n,
                              'agree': round(agree, 3), 'corr': round(corr, 3) if corr is not None else None})
    max_pair = max((p for p in pairs if p['corr'] is not None), key=lambda p: p['corr'], default=None)
    bias, degenerate = {}, []
    for m in models:
        cnt = Counter(); tot = 0
        for x in mv.values():
            if m in x:
                cnt[x[m]] += 1; tot += 1
        if tot:
            b = {'seats': seat[m], 'buy%': round(cnt[1] * 100 / tot, 1),
                 'hold%': round(cnt[0] * 100 / tot, 1),
                 'sell%': round(cnt[-1] * 100 / tot, 1),
                 'null%': round(null_v[m] * 100 / seat[m], 1) if seat[m] else 0.0}
            bias[m] = b
            # 退化委員偵測：恆說同一句話，或常態棄權 —— 兩者都是「出席但沒貢獻資訊」
            top = max(b['buy%'], b['hold%'], b['sell%']) / 100
            if top > COMMITTEE_BIAS_MAX:
                degenerate.append({'model': m, 'reason': '單一票種佔比過高',
                                   'value': round(top, 3), 'limit': COMMITTEE_BIAS_MAX})
            if b['null%'] / 100 > COMMITTEE_NULL_MAX:
                degenerate.append({'model': m, 'reason': '抽不到票比例過高',
                                   'value': round(b['null%'] / 100, 3), 'limit': COMMITTEE_NULL_MAX})

    # ── 事前動能分層:把「判斷力」與「均值回歸」分開 ──────────────────
    # 在**同一動能區間內**比較買進 vs 賣出。若判斷真有辨識力,每一層內
    # 買進都該優於賣出;若只是跌深反彈,分層後價差會消失或反向。
    strat = []
    withp = [d for d in usable if d.get('_prior') is not None]
    if withp:
        ps = sorted(d['_prior'] for d in withp)
        cuts = [ps[len(ps) * k // 3] for k in (1, 2)]          # 三等分
        def band(p):
            return 0 if p < cuts[0] else (1 if p < cuts[1] else 2)
        names = ['事前弱(跌最多)', '事前中', '事前強(漲最多)']
        for bi in range(3):
            grp = [d for d in withp if band(d['_prior']) == bi]
            bb = [d['_ex'] for d in grp if d['final_verdict'] == '買進']
            ss = [d['_ex'] for d in grp if d['final_verdict'] == '賣出']
            strat.append({
                'band': names[bi], 'n_buy': len(bb), 'n_sell': len(ss),
                'buy_excess': round(sum(bb) / len(bb), 4) if bb else None,
                'sell_excess': round(sum(ss) / len(ss), 4) if ss else None,
                'spread_pp': round((sum(bb) / len(bb) - sum(ss) / len(ss)) * 100, 2)
                             if bb and ss else None,
            })
    prior_gap = None
    pb = [d['_prior'] for d in withp if d['final_verdict'] == '買進']
    psl = [d['_prior'] for d in withp if d['final_verdict'] == '賣出']
    if pb and psl:
        prior_gap = round((sum(pb) / len(pb) - sum(psl) / len(psl)) * 100, 2)

    # ── 獨立分析日數:重疊窗口讓 t 檢定嚴重高估顯著性 ─────────────────
    days_buy = len({d['_p0'] for d in usable if d['final_verdict'] == '買進'})
    days_sell = len({d['_p0'] for d in usable if d['final_verdict'] == '賣出'})

    return {'window': fwd, 'n_usable': len(usable), 'buy': buy, 'sell': sell,
            'buy_mom_filtered': buy_filtered, 'mom_filter_pct': MOM_FILTER_PCT,
            'buy_sell_spread_pp': round(spread * 100, 2) if spread is not None else None,
            'prior_momentum_gap_pp': prior_gap,
            'prior_strata': strat,
            'independent_days': {'buy': days_buy, 'sell': days_sell},
            'committee': {'models': models, 'pairs': pairs, 'max_corr_pair': max_pair,
                          'bias': bias, 'degenerate': degenerate},
            '_rows': usable}


def run_one(window, a):
    r = compute(window)
    b = r['buy']
    print(f"=== verdict SLI (前瞻 {r['window']} 交易日) ===")
    print(f"完整視窗樣本 N={r['n_usable']}  基準=同日分析池橫斷面均報酬")
    if b['n']:
        print(f"買進 N={b['n']} 命中(超額基準)={b['hit']*100:.1f}% "
              f"均超額={b['mean_excess']*100:+.2f}% 中位={b['median_excess']*100:+.2f}% "
              f"超額≥1.5%={b['excess_ge_1p5']*100:.1f}%")
        print(f"     └ 對照 絕對漲跌命中={b['hit_abs']*100:.1f}% "
              f"(期間池均 {b['bench_mean']*100:+.2f}% —— 池均為負時絕對命中必然偏低)")
    if r['sell']['n']:
        s = r['sell']
        print(f"賣出 N={s['n']} 命中(超額基準)={s['hit']*100:.1f}% "
              f"均超額={s['mean_excess']*100:+.2f}% ｜對照 絕對下跌命中={s['hit_abs']*100:.1f}%")
    bf = r['buy_mom_filtered']
    if bf.get('n', 0) >= MIN_N:
        print(f"買進(排除事前動能前{r['mom_filter_pct']*100:.0f}%) N={bf['n']} "
              f"命中={bf['hit']*100:.1f}% 均超額={bf['mean_excess']*100:+.2f}%"
              f"  ⓘ in-sample 切片,尚未樣本外驗證")
    print(f"買-賣 spread = {r['buy_sell_spread_pp']} pp")

    # 混淆控制:先看兩組的事前動能差多少,再看同動能區間內是否仍有價差
    if r.get('prior_momentum_gap_pp') is not None:
        print(f"\n事前動能差(買進−賣出前20日) = {r['prior_momentum_gap_pp']:+.2f} pp"
              f"{'  ⚠️ 兩組體質差異大,整體 spread 混入均值回歸' if abs(r['prior_momentum_gap_pp']) > 3 else ''}")
    if r.get('prior_strata'):
        print("同動能區間內的買-賣超額價差(這才是判斷力):")
        for s in r['prior_strata']:
            sp = s['spread_pp']
            print(f"  {s['band']:<14} 買{s['n_buy']:>4}/賣{s['n_sell']:>4}  "
                  + (f"價差 {sp:+.2f} pp {'✅' if sp > 0 else '🔴'}" if sp is not None else "樣本不足"))
    d_ = r.get('independent_days', {})
    if d_:
        print(f"\n⚠️ 獨立分析日數:買進 {d_.get('buy')} 天 / 賣出 {d_.get('sell')} 天 "
              f"—— 同日多檔在重疊窗口內高度相關,樣本數 N 遠高估有效自由度,"
              f"別直接用 N 算 t 值")
    mp = r['committee']['max_corr_pair']
    if mp:
        print(f"委員最高相關: {mp['a']} × {mp['b']} 同票{mp['agree']*100:.1f}% corr={mp['corr']:+.2f}")
    deg = r['committee'].get('degenerate') or []
    if deg:
        print("🔴 退化委員(出席但不提供資訊):")
        for x in deg:
            print(f"   {x['model']}: {x['reason']} {x['value']*100:.1f}% > 上限 {x['limit']*100:.0f}%")
    elif r['committee'].get('bias'):
        print("✅ 委員票種偏態檢查通過(無單一票種>75%、無棄權>5%)")

    # NFR-QUAL 判定 —— 命中率用超額基準（與均超額同基準，見檔頭）
    qual_pass = None
    if b['n'] >= MIN_N:
        qual_pass = (b['hit'] >= QUAL_HIT) and (b['mean_excess'] >= QUAL_EXCESS)
        print(f"NFR-QUAL-001: {'✅ 達標' if qual_pass else '🔴 未達標'} "
              f"(門檻 超額命中≥{QUAL_HIT*100:.0f}% 且 均超額≥{QUAL_EXCESS*100:.1f}%)")
        if bf.get('n', 0) >= MIN_N:
            fp = (bf['hit'] >= QUAL_HIT) and (bf['mean_excess'] >= QUAL_EXCESS)
            print(f"              └ 套用反動能過濾後: {'✅ 達標' if fp else '🔴 未達標'}"
                  f" (參考值,不作為 gate)")
    else:
        print(f"NFR-QUAL-001: 樣本 <{MIN_N}，不判定")

    rows = r.pop('_rows', [])          # 逐筆明細另存,不塞進快照文件
    snapshot = {'ts': datetime.datetime.now(), 'source': 'verdict_sli', **r, 'nfr_qual_pass': qual_pass}

    # ── 逐筆明細:累積用,供網頁查詢與事後回推 ──────────────────────
    # 為什麼要留逐筆而非只留快照:快照只能回答「整體命中率多少」,
    # 回答不了「哪些判斷錯、錯在哪種情境」。而要把判斷力從均值回歸中分離,
    # 一定要有每筆的事前動能與超額報酬。2026-08-13 加。
    if rows and not a.dry_run:
        det = DB.verdict_detail
        det.create_index([('date', -1), ('symbol', 1), ('window', 1)])
        det.create_index([('window', 1), ('verdict', 1)])
        ops = []
        from pymongo import UpdateOne
        for d in rows:
            ops.append(UpdateOne(
                {'symbol': d['symbol'], 'date': d['date'], 'window': window},
                {'$set': {
                    'symbol': d['symbol'], 'date': d['date'], 'window': window,
                    'verdict': d['final_verdict'],
                    'p0_date': d['_p0'],
                    'fwd_ret': round(d['_fwd'], 6),
                    'excess': round(d['_ex'], 6),
                    'hit': (d['_ex'] > 0) if d['final_verdict'] == '買進'
                           else ((d['_ex'] < 0) if d['final_verdict'] == '賣出' else None),
                    'hit_abs': (d['_fwd'] > 0) if d['final_verdict'] == '買進'
                               else ((d['_fwd'] < 0) if d['final_verdict'] == '賣出' else None),
                    'prior_20d': round(d['_prior'], 6) if d.get('_prior') is not None else None,
                    # 反動能過濾是否會排除這筆買進 —— 供網頁回推「套用過濾會如何」
                    'mom_excluded': d.get('_mom_excluded'),
                    'updated_at': datetime.datetime.now(),
                }}, upsert=True))
        res = det.bulk_write(ops, ordered=False)
        print(f"  逐筆明細:upsert {res.upserted_count} / 更新 {res.modified_count}"
              f"(verdict_detail,window={window})")

    if a.dry_run:
        print("[dry-run] 未寫 DB")
    else:
        DB.verdict_performance.create_index([('ts', -1)])
        DB.verdict_performance.insert_one(dict(snapshot))
        print("[ok] 已寫 verdict_performance 快照")

    if a.alert and qual_pass is False:
        DB.schedule_alerts.create_index([('ts', -1)])
        DB.schedule_alerts.insert_one({
            'ts': datetime.datetime.now(), 'level': 'warning', 'source': 'verdict_sli',
            'message': f"⚠️ NFR-QUAL-001 未達標(window={window}): 買進超額命中 "
                       f"{b['hit']*100:.1f}%(需≥55%) 均超額 {b['mean_excess']*100:+.2f}%"
                       f"(需≥1.5%), N={b['n']}",
            'resolved': False})
        print("[alert] 已寫 schedule_alerts")

    # 退化委員獨立告警 —— 與 NFR gate 分開,因為它是「委員會組成」的問題,
    # 不是「判斷準不準」的問題,兩者要能各自被看見(hermes3 就是被整體數字蓋過去的)
    if a.alert and deg:
        DB.schedule_alerts.create_index([('ts', -1)])
        DB.schedule_alerts.insert_one({
            'ts': datetime.datetime.now(), 'level': 'warning', 'source': 'consensus_committee',
            'message': "⚠️ 退化委員: " + "; ".join(
                f"{x['model']} {x['reason']} {x['value']*100:.1f}%" for x in deg),
            'detail': deg, 'resolved': False})
        print("[alert] 已寫退化委員告警")
    return qual_pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window', type=int, default=20)
    ap.add_argument('--windows', type=str, default=None,
                    help='一次跑多視窗，逗號分隔（如 5,10,20）。累積 verdict_detail 用')
    ap.add_argument('--dry-run', action='store_true', help='只算不寫 DB')
    ap.add_argument('--alert', action='store_true', help='破 NFR-QUAL 門檻才寫 schedule_alerts')
    a = ap.parse_args()

    wins = ([int(x) for x in a.windows.split(',') if x.strip()]
            if a.windows else [a.window])
    for i, w in enumerate(wins):
        if i:
            print()
        run_one(w, a)
    return 0


if __name__ == '__main__':
    sys.exit(main())
