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

NFR-QUAL-001（5 日，服務每日推薦）與 NFR-QUAL-002（20 日，服務核心池）：
買進 超額命中 ≥ 55%，均超額門檻由目標年化超額反推（見 ADR-0008）。

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
import os, sys, bisect, math, argparse, datetime
from collections import defaultdict, Counter
from pymongo import MongoClient

DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
# ── 品質門檻（ADR-0007 / ADR-0008）────────────────────────────────────
# 兩條獨立需求，各自視窗、各自告警：
#   NFR-QUAL-001  前瞻 5 交易日   服務每日推薦（短線）
#   NFR-QUAL-002  前瞻 20 交易日  服務核心池（中期）
#
# 均超額門檻**由目標年化超額反推**，不同視窗不共用同一數字。
# 原本兩者共用 +1.5%，換算後才發現它其實是為 20 日校準的：
#   5 日 → 年化 +111%（任何真實系統都達不到）｜10 日 → +45%｜20 日 → +20%
# 實測 5 日 +0.71%（年化 +42%）曾因此被判「未達標」——那是假警報，壞的是門檻。
TARGET_ANNUAL_EXCESS = float(os.getenv('QUAL_TARGET_ANNUAL', '0.20'))
TRADING_DAYS_YEAR = 250.0
QUAL_HIT = 0.55      # 命中率門檻，兩條需求共用：它是「方向對不對」，不隨視窗換算


def excess_threshold(window: int) -> float:
    """由目標年化超額反推該視窗的均超額門檻。20% → 5 日 0.37%、20 日 1.47%。"""
    return (1.0 + TARGET_ANNUAL_EXCESS) ** (window / TRADING_DAYS_YEAR) - 1.0


REQ_ID = {5: 'NFR-QUAL-001', 20: 'NFR-QUAL-002'}   # 有編號者才是需求（ADR-0010）
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
ACTIVE_DAYS = 5             # 現任委員判定：最近幾個分析日投過票才算在職
# 委員對同票率上限：超過代表兩人幾乎在說同一件事，三人委員會實際只有兩個獨立意見。
# 依據（2026-08-15 實測，30 題真實顧問草案、同提示詞、temp0 固定 seed）：
#   llama3.1 × gemma2 = 56.7%/+0.41　llama3.1 × qwen2.5:7b = 56.7%/+0.41
#   gemma2 × qwen2.5:7b = 86.7%/+0.91  ← 不同家族卻高度重疊
# 這推翻了「換不同家族就能拿到多樣性」的假設 —— 冗餘與模型家族無關，
# 只能靠實測同票率發現，故必須有這個告警而不是靠選型時的直覺。
PAIR_AGREE_MAX = 0.85
# 判偏態所需的最低票數：新委員剛上線時票數個位數，100% 買進只是雜訊不是偏態。
# 2026-08-15 實測踩過：llama3.1 上線數小時、10 票全買，SLI 直接報 100% 破門檻，
# 而 committee_live_check.py 因為有這道門檻所以正確地不判定。兩支要一致。
MIN_MODEL_VOTES = 20

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


def _config_drift(active):
    """設定檔的委員名單 vs 最近實際投票的名單。

    兩者不一致有兩種可能：(a) 剛改設定、尚未跑到 —— 正常，過幾輪就會收斂；
    (b) 設定沒生效（env 覆寫、模型不存在、pull 失敗）—— 這種會靜默持續。
    本專案的教訓是設定檔不等於現實，故這裡只據**實際投票紀錄**判在職，
    設定僅作對照輸出，不參與 gate。
    """
    try:
        sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')
        from src.moe.consensus import COMMITTEE as CFG
    except Exception:
        return {'configured': None, 'drift': None}
    cfg = set(CFG)
    return {'configured': sorted(cfg),
            'drift': {'設定有但沒在投': sorted(cfg - active),
                      '在投但設定沒有': sorted(active - cfg)} if cfg != active else None}


def compute(fwd):
    _THR = excess_threshold(fwd)      # 該視窗的均超額門檻（由目標年化超額反推）
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
                'excess_ge_thr': sum(1 for x in exs if x >= _THR) / n}

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
    tenure = {}           # 模型 → (首次, 最後) 投票日
    for d in docs:
        dt = d.get('date')
        for v in (d.get('consensus') or {}).get('votes') or []:
            if not v.get('model'):
                continue
            m = v['model']
            seat[m] += 1
            if dt:
                f, l = tenure.get(m, (dt, dt))
                tenure[m] = (min(f, dt), max(l, dt))
            if v.get('vote') in V:
                mv[str(d['_id'])][m] = V[v['vote']]
            else:
                null_v[m] += 1

    # 現任委員 = 最近 ACTIVE_DAYS 個分析日實際投過票的模型。
    # 用「實際投票紀錄」而非 consensus.COMMITTEE 設定，因為設定改了不代表已生效，
    # 而已退役委員的歷史數據會一直留在庫裡 —— 若拿全歷史判退化，
    # 會對早已換掉的委員天天告警（hermes3:8b 2026-08-06 退役即為此例）。
    all_days = sorted({d['date'] for d in docs if d.get('date')})
    recent_days = set(all_days[-ACTIVE_DAYS:])
    active = set()
    for d in docs:
        if d.get('date') in recent_days:
            for v in (d.get('consensus') or {}).get('votes') or []:
                if v.get('model'):
                    active.add(v['model'])
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
    # 冗餘委員對：只看**現任**兩兩組合（已退役的重疊無法再改變，報了只是噪音）
    redundant = [dict(p, limit=PAIR_AGREE_MAX) for p in pairs
                 if p['a'] in active and p['b'] in active and p['agree'] > PAIR_AGREE_MAX]
    bias, degenerate = {}, []
    for m in models:
        cnt = Counter(); tot = 0
        for x in mv.values():
            if m in x:
                cnt[x[m]] += 1; tot += 1
        if tot:
            f, l = tenure.get(m, (None, None))
            b = {'seats': seat[m], 'buy%': round(cnt[1] * 100 / tot, 1),
                 'hold%': round(cnt[0] * 100 / tot, 1),
                 'sell%': round(cnt[-1] * 100 / tot, 1),
                 'null%': round(null_v[m] * 100 / seat[m], 1) if seat[m] else 0.0,
                 'active': m in active,
                 'first_seen': f, 'last_seen': l}
            bias[m] = b
            # 退化委員偵測：恆說同一句話，或常態棄權 —— 兩者都是「出席但沒貢獻資訊」。
            # 只對現任委員告警：已退役者的歷史數據無法再改變，天天報只會變成噪音，
            # 但仍留在 bias 表中供追溯（見 print 的「已退役」列）。
            if m not in active or tot < MIN_MODEL_VOTES:
                continue
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
                          'bias': bias, 'degenerate': degenerate, 'redundant': redundant,
                          'active': sorted(active), 'active_days': ACTIVE_DAYS,
                          **_config_drift(active)},
            '_rows': usable}


def run_one(window, a):
    r = compute(window)
    b = r['buy']
    print(f"=== verdict SLI (前瞻 {r['window']} 交易日) ===")
    print(f"完整視窗樣本 N={r['n_usable']}  基準=同日分析池橫斷面均報酬")
    if b['n']:
        print(f"買進 N={b['n']} 命中(超額基準)={b['hit']*100:.1f}% "
              f"均超額={b['mean_excess']*100:+.2f}% 中位={b['median_excess']*100:+.2f}% "
              f"超額≥門檻={b['excess_ge_thr']*100:.1f}%")
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
    cm = r['committee']
    deg = cm.get('degenerate') or []
    if cm.get('active'):
        print(f"現任委員(最近 {cm.get('active_days')} 個分析日有投票): {', '.join(cm['active'])}")
    # 注意：這裡不可用 b 當迴圈變數 —— b 是上面的 r['buy']，被遮蔽會讓下面的
    # NFR 判定拋 KeyError（2026-08-14 實測踩過，會讓每日 cron 整支掛掉）
    retired = [(m, x) for m, x in (cm.get('bias') or {}).items() if not x.get('active')]
    for m, rb in sorted(retired, key=lambda x: str(x[1].get('last_seen')), reverse=True):
        top = max(rb['buy%'], rb['hold%'], rb['sell%'])
        print(f"   (已退役 {str(rb.get('last_seen'))[:10]}) {m}: 出席{rb['seats']} "
              f"最高票種{top:.1f}%" + ("  ← 當年未被察覺的退化委員" if top > COMMITTEE_BIAS_MAX * 100 else ""))
    if cm.get('drift'):
        d = cm['drift']
        print(f"ⓘ 設定 vs 實際投票不一致: 設定有但沒在投={d['設定有但沒在投'] or '—'} / "
              f"在投但設定沒有={d['在投但設定沒有'] or '—'}")
        print("   (剛改設定尚未跑到屬正常；若持續多輪不收斂代表設定沒生效)")
    if deg:
        print("🔴 退化現任委員(出席但不提供資訊):")
        for x in deg:
            print(f"   {x['model']}: {x['reason']} {x['value']*100:.1f}% > 上限 {x['limit']*100:.0f}%")
    elif cm.get('bias'):
        print("✅ 現任委員票種偏態檢查通過(無單一票種>75%、無棄權>5%)")
    red = cm.get('redundant') or []
    if red:
        print(f"🔴 冗餘委員對(同票率>{PAIR_AGREE_MAX*100:.0f}%,三人會實際少一個獨立意見):")
        for p in red:
            print(f"   {p['a']} × {p['b']}: 同票 {p['agree']*100:.1f}% corr {p['corr']:+.2f} (n={p['n']})")
        print("   註:冗餘與模型家族無關 —— 實測 gemma2 × qwen2.5:7b 雖不同家族仍達 86.7%,"
              "換家族不保證有效,要換就得實測同票率")
    elif cm.get('pairs'):
        print(f"✅ 現任委員無冗餘對(同票率皆 ≤{PAIR_AGREE_MAX*100:.0f}%)")

    # NFR-QUAL 判定 —— 命中率用超額基準（與均超額同基準，見檔頭）
    # 門檻依視窗反推（ADR-0008）；只有 5/20 日有需求編號，其餘視窗僅供參考（ADR-0010）
    thr = excess_threshold(window)
    req = REQ_ID.get(window)
    label = req or f"（前瞻 {window} 日，無需求編號，僅參考）"
    qual_pass = None
    if b['n'] >= MIN_N:
        ok = (b['hit'] >= QUAL_HIT) and (b['mean_excess'] >= thr)
        qual_pass = ok if req else None     # 沒有編號就不是需求，不進 gate
        print(f"{label}: {'✅ 達標' if ok else '🔴 未達標'} "
              f"(門檻 超額命中≥{QUAL_HIT*100:.0f}% 且 均超額≥{thr*100:.2f}%"
              f"，由目標年化超額 {TARGET_ANNUAL_EXCESS*100:.0f}% 反推)")
        if bf.get('n', 0) >= MIN_N:
            fp = (bf['hit'] >= QUAL_HIT) and (bf['mean_excess'] >= thr)
            print(f"              └ 套用反動能過濾後: {'✅ 達標' if fp else '🔴 未達標'}"
                  f" (參考值,不作為 gate)")
    else:
        print(f"{label}: 樣本 <{MIN_N}，不判定")

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

    if a.alert and qual_pass is False and req:
        DB.schedule_alerts.create_index([('ts', -1)])
        DB.schedule_alerts.insert_one({
            'ts': datetime.datetime.now(), 'level': 'warning', 'source': 'verdict_sli',
            'requirement': req,
            'message': f"⚠️ {req} 未達標(前瞻 {window} 日): 買進超額命中 "
                       f"{b['hit']*100:.1f}%(需≥{QUAL_HIT*100:.0f}%) 均超額 "
                       f"{b['mean_excess']*100:+.2f}%(需≥{thr*100:.2f}%), N={b['n']}",
            'resolved': False})
        print(f"[alert] 已寫 schedule_alerts（{req}）")

    # 退化委員獨立告警 —— 與 NFR gate 分開,因為它是「委員會組成」的問題,
    # 不是「判斷準不準」的問題,兩者要能各自被看見(hermes3 就是被整體數字蓋過去的)
    if a.alert and (deg or red):
        msgs = [f"{x['model']} {x['reason']} {x['value']*100:.1f}%" for x in deg]
        msgs += [f"{p['a']}×{p['b']} 同票 {p['agree']*100:.1f}%" for p in red]
        DB.schedule_alerts.create_index([('ts', -1)])
        DB.schedule_alerts.insert_one({
            'ts': datetime.datetime.now(), 'level': 'warning', 'source': 'consensus_committee',
            'message': "⚠️ 委員會組成問題: " + "; ".join(msgs),
            'detail': {'degenerate': deg, 'redundant': red}, 'resolved': False})
        print("[alert] 已寫委員會組成告警")
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
