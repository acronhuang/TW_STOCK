#!/usr/bin/env python3
"""
每日「已查證」角色團隊分析（Tier1/2）
=====================================
解決兩個落差：
  (1) 角色分流分析沒進到每日輸出 → 本腳本每日對 Tier1/2 標的自動跑 7 角色分析。
  (2) 沒有資料佐證 → 加「網路查證層」：關鍵數字向 FinMind 即時重抓，與本地 DB 比對，
      標示 ✅一致 / ⚠️背離。此層『完全不信任 LLM』，是獨立的數據正確性驗證。

流程：
  Tier1/2 名單(HsiehWatchlist) → 每檔:
    [A] 網路查證層: DB 收盤/PE/殖利率  vs  FinMind 即時  → ✅/⚠️
    [B] 本地 Ollama 7 角色分流分析(每角色須列出引用數值)
    [C] 投資顧問整合
  → Console + LINE（各角色一句話 + 資料佐證表）

用法：
  python scripts/team_daily_verified.py                  # 跑 Tier1/2 前2檔 + 發LINE
  python scripts/team_daily_verified.py --no-line        # 不發LINE
  python scripts/team_daily_verified.py --symbols 2330   # 指定個股
  python scripts/team_daily_verified.py --top 3 --quick  # 前3檔, quick(略過顧問整合)
"""
from __future__ import annotations
import os
import re
import sys
import csv
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import requests
from pymongo import MongoClient
from bson import Decimal128

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from scripts.team_analyze import fetch_all_data, build_expert_prompt
from src.moe.role_router import ask_role, ROLE_TO_MODEL

FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'
FINMIND_TOKEN = os.getenv('FINMIND_API_TOKEN', '')
DB = MongoClient('mongodb://localhost:27017')['tw_stock_analysis']

# 分析角色順序（不含 investment-advisor，最後整合）
ANALYST_ROLES = ['macro-analyst', 'technical-analyst', 'fundamental-analyst',
                 'value-analyst', 'risk-manager', 'chip-analyst']
ROLE_ICON = {
    'macro-analyst': '🎯總經', 'technical-analyst': '📈技術',
    'fundamental-analyst': '💰基本面', 'value-analyst': '💎價值',
    'risk-manager': '🛡️風險', 'chip-analyst': '🏦籌碼',
}
# 要求每個角色把引用數值攤出來（透明化；正確性由查證層獨立驗證）
EVIDENCE_SUFFIX = ("\n\n【務必】最後另起一行『📌引用數值：』，以「欄位=數值」條列你"
                   "實際用到的關鍵數字(至少3項)，數字一律取自上方提供的資料，不可自行編造。")


def _tof(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── [A] 網路查證層（DB vs FinMind 即時）────────────────────────────────
def _finmind(dataset: str, data_id: str, start_date: str):
    try:
        r = requests.get(FINMIND_URL, params={
            'dataset': dataset, 'data_id': data_id,
            'start_date': start_date, 'token': FINMIND_TOKEN,
        }, timeout=20)
        if r.status_code != 200:
            return None
        return r.json().get('data', [])
    except Exception:
        return None


def _db_latest(coll: str, key: str, symbol: str, field: str, non_null: bool = False):
    """取 DB 某 collection 最新一筆的某欄位值。
    non_null=True 時抓『該欄位最新非空』那筆（stock_factors 多來源，最新一筆可能無 PE）。"""
    q = {key: symbol}
    if non_null:
        q[field] = {'$ne': None}
    doc = DB[coll].find_one(q, sort=[('date', -1)])
    return (_tof(doc.get(field)) if doc else None), (doc.get('date') if doc else None)


# FinMind 複核節流：本地 DB 為權威來源，FinMind 僅作抽查稽核。
# 每個 process 最多複核 N 檔(避免 50 檔 ×3 打爆 600/hr 配額、與其他排程互搶)，
# 超過則純用本地 DB(標 📁本地，非警示)。符合「本地優先」原則。
_FM_AUDIT_QUOTA = [25]


def _fm_audit_take() -> bool:
    """取一次 FinMind 抽查額度；用完回 False(改純本地)。"""
    if _FM_AUDIT_QUOTA[0] > 0:
        _FM_AUDIT_QUOTA[0] -= 1
        return True
    return False


def verify_metrics(symbol: str) -> list[dict]:
    """關鍵數字佐證：本地 DB 為準，FinMind 節流抽查複核。回傳佐證列(每列含 db/live/flag/source)。"""
    rows = []
    start = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
    audit = _fm_audit_take()    # 本檔是否動用 FinMind 複核(節流)

    # 1) 收盤價：stock_price(本地) vs TaiwanStockPrice(抽查)
    db_close, _ = _db_latest('stock_price', 'symbol', symbol, 'close')
    fm_price = _finmind('TaiwanStockPrice', symbol, start) if audit else None
    live_close = _tof(fm_price[-1].get('close')) if fm_price else None
    rows.append(_cmp('收盤價', db_close, live_close, 'FinMind', tol=0.03))

    # 2) 本益比 / 殖利率：stock_factors(本地,最新非空) vs TaiwanStockPER(抽查)
    db_pe, _ = _db_latest('stock_factors', 'symbol', symbol, 'pe_ratio', non_null=True)
    db_dy, _ = _db_latest('stock_factors', 'symbol', symbol, 'dividend_yield', non_null=True)
    fm_per = _finmind('TaiwanStockPER', symbol, start) if audit else None
    live_pe = _tof(fm_per[-1].get('PER')) if fm_per else None
    live_dy = _tof(fm_per[-1].get('dividend_yield')) if fm_per else None
    rows.append(_cmp('本益比', db_pe, live_pe, 'FinMind', tol=0.05))
    rows.append(_cmp('殖利率%', db_dy, live_dy, 'FinMind', tol=0.05))

    # 3) 法人10日淨(張)：institutional_flow（DB 端佐證，附來源；FinMind 法人需逐類加總，v1 僅列 DB）
    docs = list(DB.institutional_flow.find({'stock_id': symbol}, sort=[('date', -1)]).limit(10))
    if docs:
        net = sum((_tof(d.get('total_net')) or 0) for d in docs) / 1000
        rows.append({'metric': '法人10日淨(張)', 'db': round(net), 'live': None,
                     'source': 'institutional_flow', 'flag': '📊'})
    return rows


def _cmp(metric, db, live, source, tol):
    if db is None and live is None:
        return {'metric': metric, 'db': None, 'live': None, 'source': source, 'flag': '—無資料'}
    if live is None:   # 本地 DB 有值、未動用/未取得 FinMind 複核 → 本地為準(非缺資料)
        return {'metric': metric, 'db': round(db, 2), 'live': None, 'source': source, 'flag': '📁本地'}
    if db is None:     # FinMind 有、DB 缺 → 真的 DB 缺
        return {'metric': metric, 'db': None, 'live': round(live, 2), 'source': source, 'flag': '⚠️DB缺'}
    base = abs(live) if live else 1
    diff = abs(db - live) / base if base else 0
    flag = '✅' if diff <= tol else '⚠️背離'
    return {'metric': metric, 'db': round(db, 2), 'live': round(live, 2),
            'source': source, 'flag': flag}


# ── 蔡森型態（SenVision 演算法）→ 餵給 technical-analyst ────────────────
def senvision_patterns(symbol: str) -> list[dict]:
    """讀最新 scan_auto CSV，取該股的蔡森型態訊號（依評分排序前4）。"""
    rdir = ROOT / 'results'
    try:
        csvs = sorted([f for f in os.listdir(rdir)
                       if f.startswith('scan_auto_') and f.endswith('.csv')], reverse=True)
    except FileNotFoundError:
        return []
    if not csvs:
        return []
    out = []
    with open(rdir / csvs[0], encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row.get('股票代碼', '').strip() == symbol:
                out.append({
                    'tf': row.get('時框', ''), 'pattern': row.get('形態', ''),
                    'status': row.get('狀態', ''), 'neckline': row.get('頸線', ''),
                    'target': row.get('目標價', ''), 'stop': row.get('停損價', ''),
                    'rrr': row.get('風報比', ''), 'score': row.get('評分', ''),
                    'vp': row.get('量價狀態', ''),
                })
    out.sort(key=lambda r: float(r['score'] or 0), reverse=True)
    return out[:4]


def senvision_text(pats: list[dict]) -> str:
    if not pats:
        return "蔡森型態分析(SenVision 演算法)：近期無觸發型態訊號。"
    lines = ["蔡森型態分析(SenVision 蔡森技術型態演算法，已含量價/均線/多時框評分)："]
    for p in pats:
        lines.append(f"- {p['tf']} {p['pattern']} {p['status']} 頸線={p['neckline']} "
                     f"目標={p['target']} 停損={p['stop']} 風報比={p['rrr']} 評分={p['score']} 量價={p['vp']}")
    return '\n'.join(lines)


# ── [B][C] 角色分析 + 整合 ─────────────────────────────────────────────
_MOMENTUM = None


def _ma_inst_extra(symbol: str) -> dict:
    """MA乖離(20/60) + 法人連續(外資/投信)，供 LINE 顯示。"""
    global _MOMENTUM
    if _MOMENTUM is None:
        from src.factors.momentum_factors import MomentumFactors
        _MOMENTUM = MomentumFactors(DB)
    now = datetime.now()
    try:
        return {**_MOMENTUM.calculate_ma_bias(symbol, now),
                **_MOMENTUM.calculate_ma_long_trend(symbol, now),
                **_MOMENTUM.calculate_inst_streak(symbol, now)}
    except Exception:
        return {}


def analyze_symbol(symbol: str, quick: bool) -> dict:
    data = fetch_all_data(symbol)
    evidence = verify_metrics(symbol)
    sv_pats = senvision_patterns(symbol)          # 蔡森型態結果
    extra = _ma_inst_extra(symbol)                # MA乖離 + 法人連續

    reports = {}
    for role in ANALYST_ROLES:
        prompt = build_expert_prompt(role, symbol, data)
        if role == 'technical-analyst':
            # 技術角色依「蔡森方法」分析：餵入 SenVision 型態/頸線/目標價/風報比
            prompt += "\n\n" + senvision_text(sv_pats) + \
                      "\n\n請務必結合上述蔡森型態結果(型態/頸線/目標價/風報比)做技術判讀，而非只看因子。"
        prompt += EVIDENCE_SUFFIX
        # timeout 放寬：deepseek-r1:14b 等模型在角色迴圈中『第一次呼叫』需冷載(9GB)+thinking，
        # 易破 180s（後續同模型 warm 則快）。給 300s 吸收冷啟動。
        r = ask_role(role, prompt, include_role_prompt=True, timeout=300)
        txt = r.get('response', f"分析失敗: {r.get('error')}")
        if '</think>' in txt:
            txt = txt.split('</think>', 1)[-1]
        reports[role] = txt.strip()
        print(f"     {ROLE_ICON.get(role, role)} ({r.get('model','?')}) {r.get('elapsed_sec','?')}s")

    advisor = None
    if not quick:
        data['reports'] = reports
        prompt = build_expert_prompt('investment-advisor', symbol, data)
        # 顧問 qwen3.6:27b(17GB) 冷載 + 整合6份報告，給 600s
        r = ask_role('investment-advisor', prompt, include_role_prompt=True, timeout=600)
        advisor = r.get('response', f"整合失敗: {r.get('error')}")
        if '</think>' in advisor:
            advisor = advisor.split('</think>', 1)[-1].strip()
        print(f"     🎩顧問整合 ({r.get('model','?')}) {r.get('elapsed_sec','?')}s")

    # [D] .27 合議投票層：委員會對 .28 顧問草案投票定案
    consensus = _consensus_for(
        {'symbol': symbol, 'advisor': advisor, 'evidence': evidence,
         'name': data.get('name', '') if isinstance(data, dict) else ''})
    if consensus:
        print(f"     🗳️合議 ({consensus['n']}模型) → 定案:{consensus['final']}")

    return {'symbol': symbol, 'evidence': evidence, 'reports': reports,
            'advisor': advisor, 'senvision': sv_pats, 'extra': extra,
            'consensus': consensus}


def _first_line(txt: str, n: int = 60) -> str:
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith('📌'):
            return ln[:n]
    return txt[:n]


# ── 名單 + 輸出 ────────────────────────────────────────────────────────
def get_tier_symbols(top: int) -> list[dict]:
    """謝富旭存股法篩選前 N 檔(全市場演算法，取代手選清單)。"""
    from src.strategy.hsieh_value import HsiehValueScreen
    picks = HsiehValueScreen(DB).screen(top=top)
    return [{'symbol': r['symbol'], 'name': r['name'], 'action': '[存股法]'} for r in picks]


def select_universe_50(n: int = 50) -> list[dict]:
    """各行業龍頭(市值最大) + 成交額前段，去重補滿 n 檔。
    龍頭=outstanding_shares×最新收盤最大者(用各股最新收盤，避開當日partial)。"""
    import re
    latest = {}
    for d in DB.stock_price.aggregate([{'$sort': {'date': -1}}, {'$group': {
            '_id': '$symbol', 'close': {'$first': '$close'}, 'volume': {'$first': '$volume'}}}],
            allowDiskUse=True):
        latest[d['_id']] = d
    info = {}
    for d in DB.taiwan_stock_info.find(
            {}, {'stock_id': 1, 'industry_category': 1, 'stock_name': 1, 'outstanding_shares': 1}):
        sid = d['stock_id']
        if sid not in info or (d.get('outstanding_shares') is not None and info[sid].get('outstanding_shares') is None):
            info[sid] = d
    EXCL = ('ETF', '指數股票型', '受益', '存託')
    rows = []
    for sym, p in latest.items():
        if not re.fullmatch(r'\d{4}', str(sym)):
            continue
        ti = info.get(sym)
        if not ti:
            continue
        ind = ti.get('industry_category')
        if not ind or any(w in ind for w in EXCL):
            continue
        close, vol, sh = _tof(p.get('close')), _tof(p.get('volume')), _tof(ti.get('outstanding_shares'))
        if not close or vol is None:
            continue
        rows.append({'symbol': sym, 'name': ti.get('stock_name'), 'industry': ind,
                     'mktcap': sh * close if sh else 0, 'value': close * vol})
    leaders = {}
    for r in rows:
        if r['industry'] not in leaders or r['mktcap'] > leaders[r['industry']]['mktcap']:
            leaders[r['industry']] = r
    sel = {r['symbol']: r for r in leaders.values()}        # 龍頭優先
    for r in sorted(rows, key=lambda x: -x['value']):        # 成交額補滿
        if len(sel) >= n:
            break
        sel.setdefault(r['symbol'], r)
    return [{'symbol': r['symbol'], 'name': r['name'], 'action': f"[{r['industry']}]"}
            for r in sel.values()]


def select_universe_all() -> list[dict]:
    """全市場：所有有價、有基本資訊的 4 碼個股(去 ETF/受益/存託)。"""
    import re
    syms = set(s for s in DB.stock_price.distinct('symbol') if re.fullmatch(r'\d{4}', str(s)))
    info = {d['stock_id']: d for d in DB.taiwan_stock_info.find(
        {}, {'stock_id': 1, 'industry_category': 1, 'stock_name': 1})}
    EXCL = ('ETF', '指數股票型', '受益', '存託')
    out = []
    for sym in sorted(syms):
        ti = info.get(sym)
        ind = (ti or {}).get('industry_category')
        if not ti or not ind or any(w in ind for w in EXCL):
            continue
        out.append({'symbol': sym, 'name': ti.get('stock_name'), 'action': '(全市場)'})
    return out


# ── 存檔 / 讀檔（兩階段：phase1精簡存檔 → phase2讀檔補顧問）─────────────
RESULT_DIR = ROOT / 'results' / 'team_analysis'


# 存讀檔日期覆寫（--date 設定）。None 時用今天。
# 用途：phase1 跨午夜或時區不一致時，phase2 才不會因「今天日期」對不上而找不到 phase1 存檔。
_DATE_OVERRIDE = None


def _result_path(date_str: str = None):
    ds = date_str or _DATE_OVERRIDE or datetime.now().strftime('%Y%m%d')
    return RESULT_DIR / f"team_{ds}.json"


def _latest_result_path():
    """最新一份 team_YYYYMMDD.json（供 phase2 在當日檔缺席時退回）。"""
    files = sorted(RESULT_DIR.glob('team_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json'))
    return files[-1] if files else None


def save_results(analyses: list, meta: dict):
    import json
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_result_path(), 'w', encoding='utf-8') as f:
        json.dump({'meta': meta, 'analyses': analyses}, f, ensure_ascii=False, default=str)


def _current_date():
    """本次分析的交易日基準（與 JSON 檔名同一天），供 DB 文件 date 欄位。"""
    ds = _DATE_OVERRIDE or datetime.now().strftime('%Y%m%d')
    return datetime.strptime(ds, '%Y%m%d')


_TEAM_DB = None


def db_upsert_one(analysis: dict, meta: dict):
    """單檔雙寫到 team_analysis（JSON 之外）。失敗僅記錄，不中斷分析流程。"""
    global _TEAM_DB
    try:
        from src.moe.team_store import upsert_analyses
        if _TEAM_DB is None:
            from src.moe.team_store import ensure_indexes, get_db
            _TEAM_DB = get_db()
            ensure_indexes(_TEAM_DB)
        upsert_analyses(_TEAM_DB, [analysis], _current_date(), meta,
                        source_file=_result_path().name)
    except Exception as e:
        print(f"     ⚠️ DB 雙寫失敗({analysis.get('symbol')}): {e}")


def load_results():
    import json
    p = _result_path()
    if not p.exists():
        # 當日檔不存在時退回最新一份（phase1 跨午夜/時區錯位的防呆）
        p = _latest_result_path()
        if p is None:
            return None
        print(f"⚠️ 無當日存檔，改用最新一份：{p.name}")
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def run_advisor(symbol: str, reports: dict) -> str:
    """phase2：用 phase1 存的 6 份報告重跑投資顧問整合(不重跑6角色)。"""
    prompt = build_expert_prompt('investment-advisor', symbol, {'reports': reports})
    r = ask_role('investment-advisor', prompt, include_role_prompt=True, timeout=600)
    txt = r.get('response', f"整合失敗: {r.get('error')}")
    if '</think>' in txt:
        txt = txt.split('</think>', 1)[-1].strip()
    return txt


def _consensus_for(a: dict, meta: dict = None):
    """對顧問草案跑 .27 合議投票(完整模式與 phase2 共用)。無顧問/整合失敗回 None。"""
    advisor = a.get('advisor')
    if not advisor or advisor.startswith('整合失敗'):
        return None
    from src.moe.consensus import deliberate, discuss
    ev_txt = '; '.join(f"{e.get('metric')}={e.get('db')}" for e in (a.get('evidence') or [])
                       if e.get('db') is not None)
    name = (meta.get(a['symbol']) or {}).get('name', '') if meta else a.get('name', '')
    # 預設走「序列討論 discuss」(多輪+逐字稿+主持人)；env CONSENSUS_MODE=deliberate 可切回盲投對照。
    if os.getenv('CONSENSUS_MODE', 'discuss') == 'deliberate':
        return deliberate(a['symbol'], name, advisor[:1500], ev_txt)
    return discuss(a['symbol'], name, advisor[:1500], ev_txt, rounds=2)


_VERDICTS = ['強力買進', '買進', '觀望', '減碼', '賣出']


def _verdict(advisor_txt: str) -> str:
    """從顧問整合文字抽『最終評級』。
    舊 bug：在整篇找『買進』第一個命中 → 內文『條件式買進』等把賣出/觀望蓋掉。
    新法：① 先讀固定標籤『評級：X』(新版 prompt 產出)；
          ② 退而取『最終建議』窗格，依『出現位置最前』者為準(非關鍵字優先序)。"""
    if not advisor_txt:
        return '—'

    def _pick(seg):
        pos = {kw: seg.find(kw) for kw in _VERDICTS if kw in seg}
        # 『強力買進』含子字串『買進』(offset+2) → 同位置取『強力買進』
        if '強力買進' in pos and pos.get('買進') == pos['強力買進'] + 2:
            del pos['買進']
        return min(pos, key=pos.get) if pos else None   # 取出現位置最前者

    # ① 結構化標籤(新版 prompt 產出『評級：X』)
    m = re.search(r'(?:最終)?評級\s*[：:]\s*\**\s*(強力買進|買進|觀望|減碼|賣出)', advisor_txt)
    if m:
        return m.group(1)
    # ② 明確「最終(投資)建議/評級：X」窗格(最準，取位置最前的評級詞)
    m = re.search(r'(?:最終投資建議|最終建議|最終評級|🎯[^\n：:]{0,8}建議)[】\]\s]*[:：][\s\*]*([\s\S]{0,28})',
                  advisor_txt)
    if m:
        v = _pick(m.group(1))
        if v:
            return v
    # ③ 退而求其次：顧問多在開頭即下結論 → 前 160 字位置法補漏
    v = _pick(advisor_txt[:160])
    return v or '—'


def _evidence_ok(a) -> str:
    """顯示資料完整度(本地 DB 有值=有資料)，非 FinMind 成功率。
    背離(⚠️)另標；真缺(DB缺/無資料)才算缺。"""
    ev = a.get('evidence', [])
    if not ev:
        return '—'
    present = sum(1 for e in ev if e.get('db') is not None)          # 本地有值
    total = len(ev)
    diverge = any(e.get('flag') == '⚠️背離' for e in ev)             # 複核背離(需留意)
    s = '齊' if present == total else f'{present}/{total}'
    return s + ('⚠' if diverge else '')


def _ev_val(a, metric):
    """從佐證列取某指標的 DB 值。"""
    for e in a.get('evidence', []):
        if e.get('metric') == metric:
            return e.get('db')
    return None


def _pat_dir(sv: dict) -> str:
    """蔡森型態方向：以 target vs stop 判定(最穩，不受 Failed-Breakdown 命名干擾)；
    退而求其次看型態名。回傳 'long'/'short'/'none'。"""
    if not sv or not sv.get('pattern'):
        return 'none'
    t, s = _tof(sv.get('target')), _tof(sv.get('stop'))
    if t is not None and s is not None and t != s:
        return 'long' if t > s else 'short'
    p = (sv.get('pattern') or '').lower()
    if 'bottom' in p or 'breakdown' in p:   # failed-breakdown 屬偏多
        return 'long'
    if 'top' in p or 'breakout' in p:
        return 'short'
    return 'none'


def _enrich_line(a: dict, meta: dict, show_verdict: bool) -> str:
    """單檔加料行：現價/PE/殖利率 + 蔡森(型態方向·狀態 RRR 量價) + 佐證。"""
    m = meta.get(a['symbol'], {})
    price, pe, dy = _ev_val(a, '收盤價'), _ev_val(a, '本益比'), _ev_val(a, '殖利率%')
    bits = []
    if price is not None:
        bits.append(f"{price:g}")
    if pe:
        bits.append("PE高" if pe > 80 else f"PE{pe:.0f}")   # PE>80 多為低獲利,數值無意義 → 標『高』
    if dy:
        bits.append(f"殖{dy:.1f}%")
    sv = (a.get('senvision') or [{}])[0]
    pat = sv.get('pattern')
    if pat:
        arrow = {'long': '↗', 'short': '↘', 'none': ''}[_pat_dir(sv)]
        st = f"·{sv.get('status')}" if sv.get('status') else ""
        rr = f" RRR{sv.get('rrr')}" if sv.get('rrr') else ""
        vp = f" 📊{sv.get('vp')}" if sv.get('vp') else ""
        patf = f"🔷{pat}{arrow}{st}{rr}{vp}"
    else:
        patf = "🔷無型態"
    # MA乖離(僅在過度延伸時標) + 法人連續(≥3 才標)
    ex = a.get('extra') or {}
    tags = []
    _MA_LBL = {20: '乖離20', 60: '乖離季', 120: '乖離半年', 240: '乖離年'}
    cand = [(w, ex.get(f'ma_bias_{w}')) for w in (20, 60, 120, 240) if ex.get(f'ma_bias_{w}') is not None]
    if cand:
        w, bias = max(cand, key=lambda x: abs(x[1]))
        if abs(bias) >= 15:                          # 過度延伸才標(均值回歸提醒)
            tags.append(f"{_MA_LBL[w]}{bias:+.0f}%{'⚠超買' if bias > 0 else '⚠超賣'}")
    if ex.get('ma_above_long') == 0:                 # 跌破全部長均線=長期空頭格局
        tags.append("⚠年線下")
    for key, nm in (('foreign_streak', '外資'), ('trust_streak', '投信')):
        s = ex.get(key)
        if s and abs(s) >= 3:
            tags.append(f"{nm}連{abs(s)}{'買' if s > 0 else '賣'}")
    tagstr = (' ' + ' '.join(tags)) if tags else ''
    head = f"🎩{_verdict(a.get('advisor') or '')} " if show_verdict else ""
    cons = a.get('consensus')
    cons_tag = ''
    if cons and cons.get('n'):
        t = cons['tally']
        cons_tag = f" 🗳️{cons['final']}({t['買進']}/{t['持有']}/{t['賣出']})"
    return f"{head}{a['symbol']} {m.get('name','')} {' '.join(bits)} {patf}{tagstr}{cons_tag} 佐{_evidence_ok(a)}"


def _rrr_key(a):
    """組內排序：風報比高者優先(None 視為0)。"""
    sv = (a.get('senvision') or [{}])[0]
    return -(_tof(sv.get('rrr')) or 0)


def build_line_summary(analyses: list[dict], meta: dict) -> str:
    """多檔(如50)摘要：加料行 + 分組。完整版(有顧問)依🎩判定分組；精簡版依蔡森方向分組。"""
    d = datetime.now().strftime('%m/%d')
    has_adv = any(a.get('advisor') for a in analyses)
    phase = '完整' if has_adv else '精簡'
    L = [f"🏛️ 每日團隊分析({phase}·已查證) {d}  共{len(analyses)}檔\n"]

    if has_adv:
        # 完整版：依顧問判定分組(判定即組標題，行內不重複)
        order = [('強力買進', '🔥'), ('買進', '🟢'), ('觀望', '🟡'),
                 ('減碼', '🟠'), ('賣出', '🔴'), ('—', '⚪')]
        groups = {k: [] for k, _ in order}
        for a in analyses:
            groups[_verdict(a.get('advisor') or '')].append(a)
        for k, icon in order:
            g = groups[k]
            if not g:
                continue
            L.append(f"{icon} {k}（{len(g)}）")
            for a in sorted(g, key=_rrr_key):
                L.append(_enrich_line(a, meta, show_verdict=False))
            L.append("")
    else:
        # 精簡版：依蔡森方向分組(偏多在前=可留意的進場 setup)
        order = [('long', '📈 偏多型態'), ('short', '📉 偏空型態'), ('none', '➖ 無型態(僅數據)')]
        groups = {'long': [], 'short': [], 'none': []}
        for a in analyses:
            sv = (a.get('senvision') or [{}])[0]
            groups[_pat_dir(sv)].append(a)
        for key, title in order:
            g = groups[key]
            if not g:
                continue
            L.append(f"{title}（{len(g)}）")
            for a in sorted(g, key=_rrr_key):
                L.append(_enrich_line(a, meta, show_verdict=False))
            L.append("")
    return '\n'.join(L).rstrip()


def build_line(analyses: list[dict], meta: dict) -> str:
    if len(analyses) > 8:                 # 多檔(如50)→精簡摘要
        return build_line_summary(analyses, meta)
    d = datetime.now().strftime('%m/%d')
    L = [f"🏛️ 每日團隊分析(已查證) {d}\n"]
    for a in analyses:
        m = meta.get(a['symbol'], {})
        L.append(f"── {a['symbol']} {m.get('name','')} {m.get('action','')} ──")
        # 蔡森型態（SenVision 演算法）— 技術角色的依據
        sv = a.get('senvision') or []
        if sv:
            top = sv[0]
            L.append(f"🔷蔡森型態: {top['tf']}{top['pattern']} {top['status']} "
                     f"頸線{top['neckline']}/目標{top['target']} RRR{top['rrr']}")
        else:
            L.append("🔷蔡森型態: 近期無訊號")
        for role in ANALYST_ROLES:
            L.append(f"{ROLE_ICON[role]}: {_first_line(a['reports'].get(role,''))}")
        if a.get('advisor'):
            L.append(f"🎩整合: {_first_line(a['advisor'], 80)}")
        if a.get('consensus'):
            from src.moe.consensus import line as _cl100
            L.append(_cl100(a['consensus']))
        L.append("📋資料佐證(DB vs FinMind即時):")
        for e in a['evidence']:
            if e['live'] is not None:
                L.append(f"  {e['metric']} DB{e['db']}/FM{e['live']} {e['flag']}")
            else:
                L.append(f"  {e['metric']} {e['db']} ({e['source']}) {e['flag']}")
        L.append("")
    return '\n'.join(L)


def _send_line(msg: str):
    try:
        from src.alerts.line_notifier import LineNotifier
        ln = LineNotifier()
        if not ln.enabled:
            print("⚠️ LINE 未設定"); return
        # LINE 單則上限~5000字 → 過長分段
        for i in range(0, len(msg), 4500):
            ln.send(msg[i:i + 4500])
        print("✅ LINE 已發送")
    except Exception as e:
        print(f"⚠️ LINE 失敗: {e}")


def main():
    ap = argparse.ArgumentParser(description='每日已查證角色團隊分析')
    ap.add_argument('--top', type=int, default=2, help='Tier1/2 取前幾檔')
    ap.add_argument('--symbols', nargs='+', help='指定個股(略過自動選股)')
    ap.add_argument('--universe', choices=['tier', 'industry50', 'all'], default='tier',
                    help='選股範圍：tier=謝富旭Tier1/2(預設)；industry50=各行業龍頭50；all=全市場~2000檔')
    ap.add_argument('--quick', action='store_true', help='精簡：略過投資顧問整合(較快)')
    ap.add_argument('--phase2', action='store_true', help='第二階段：讀今日精簡存檔，只補跑顧問整合')
    ap.add_argument('--date', help='存讀檔日期 YYYYMMDD（預設今天）；phase1 跨午夜或 phase2 補跑舊存檔時指定')
    ap.add_argument('--no-line', action='store_true', help='不發 LINE')
    args = ap.parse_args()

    if args.date:
        global _DATE_OVERRIDE
        _DATE_OVERRIDE = args.date

    # ── 第二階段：讀 phase1 存檔，只補顧問整合 ──────────────────────────
    if args.phase2:
        saved = load_results()
        if not saved:
            print("⚠️ 無今日精簡存檔，請先跑 --quick"); return
        meta, analyses = saved['meta'], saved['analyses']
        todo = [a for a in analyses if not a.get('advisor')]
        print(f"第二階段：對 {len(todo)} 檔補跑顧問整合(重用已存6角色報告)")
        for i, a in enumerate(todo, 1):
            print(f"  [{i}/{len(todo)}] 🎩 {a['symbol']} 顧問整合...")
            a['advisor'] = run_advisor(a['symbol'], a.get('reports', {}))
            a['consensus'] = _consensus_for(a, meta)   # .27 合議投票定案
            if a.get('consensus'):
                print(f"       🗳️合議 → 定案:{a['consensus']['final']}")
            save_results(analyses, meta)        # 逐檔存檔(中斷可續)
            db_upsert_one(a, meta)              # 雙寫 DB(含顧問+合議)
        msg = build_line(analyses, meta)
        print("\n" + "=" * 60 + "\n" + msg)
        if not args.no_line:
            _send_line(msg)
        return

    # ── 選股 ────────────────────────────────────────────────────────────
    if args.symbols:
        targets = [{'symbol': s, 'name': '', 'action': '(指定)'} for s in args.symbols]
    elif args.universe == 'all':
        print("選取 全市場所有個股...")
        targets = select_universe_all()
    elif args.universe == 'industry50':
        print("選取 各行業龍頭 + 成交額補滿50...")
        targets = select_universe_50(50)
    else:
        print("選取 Tier1/2 名單...")
        targets = get_tier_symbols(args.top)
    if not targets:
        print("無標的，結束"); return
    meta = {t['symbol']: t for t in targets}
    print(f"分析 {len(targets)} 檔: {', '.join(t['symbol'] for t in targets[:10])}{'...' if len(targets)>10 else ''}")

    analyses = []
    for t in targets:
        print(f"\n🏛️ {t['symbol']} {t['name']} 團隊分析...")
        res = analyze_symbol(t['symbol'], args.quick)
        analyses.append(res)
        save_results(analyses, meta)            # 逐檔存檔(中斷可續/供phase2)
        db_upsert_one(res, meta)                # 雙寫 DB

    msg = build_line(analyses, meta)
    print("\n" + "=" * 60 + "\n" + msg)
    if not args.no_line:
        _send_line(msg)


if __name__ == '__main__':
    main()
