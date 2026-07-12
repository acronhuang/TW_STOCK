"""
⚠️ 已棄用（2026-06-20）：本檔的手選 13 檔硬編碼清單(HSIEH_PICKS)已由
   全市場演算法篩選 `src/strategy/hsieh_value.py`(HsiehValueScreen) 取代。
   daily_recommendations / team 皆已改用 HsiehValueScreen，本檔無外部引用，可安全刪除。

謝富旭老師實際選股清單（2026/4/13 更新）— 舊版手選
========================================
直接匯入老師的研究成果，用系統即時數據追蹤。

使用：
    from src.strategy.hsieh_watchlist import HsiehWatchlist
    hw = HsiehWatchlist()
    hw.report()           # 完整報告
    hw.line_summary()     # 發 LINE
"""

from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime
from pymongo import MongoClient
from bson import Decimal128
import os

def _tof(v) -> Optional[float]:
    if isinstance(v, Decimal128): return float(v.to_decimal())
    try: return float(v)
    except: return None


def _volume_tag(volume_ratio, vol_pct_60d, obv_slope, vp_divergence) -> str:
    """量價狀態標籤（來自 stock_factors volume factors），如『爆量·資金流入』『量縮·空背』。
    資料不足回空字串。"""
    if volume_ratio is None and obv_slope is None and vp_divergence is None:
        return ''
    parts = []
    if volume_ratio is not None:
        if volume_ratio >= 2.0 or (vol_pct_60d is not None and vol_pct_60d >= 90):
            parts.append('爆量')
        elif volume_ratio <= 0.7 or (vol_pct_60d is not None and vol_pct_60d <= 20):
            parts.append('量縮')
    if obv_slope is not None:
        parts.append('資金流入' if obv_slope > 0 else ('資金流出' if obv_slope < 0 else ''))
    if vp_divergence == -1:
        parts.append('空背')
    elif vp_divergence == 1:
        parts.append('多背')
    return '·'.join(p for p in parts if p)


# 謝富旭老師 2026/4/13 實際選股清單
HSIEH_PICKS = [
    # (代號, 名稱, 產業, 屬性, 2027預估配息, 老師估價位階, 除息日)
    ('6525', '捷敏-KY',    'IC封測',    '小型成長', 6.0,  '便宜',   '2025-05-27'),
    ('4506', '崇友',       '電梯',      '小型領息', 5.1,  '殷實',   '2025-07-22'),
    ('6914', '阜爾運通',    '停車場',    '小型成長', 8.0,  '合理',   '2025-07-17'),
    ('2385', '群光',       '電腦周邊',   '中型成長', 8.7,  '便宜',   '2026-06-15'),
    ('6412', '群電',       '電源供應',   '中型成長', 4.0,  '殷實',   '2026-06-09'),
    ('3010', '華立',       '電子通路',   '中型成長', 5.1,  '昂貴',   '2025-06-23'),
    ('4958', '臻鼎-KY',    'PCB',      '大型成長', 5.5,  '昂貴',   '2026-06-08'),
    ('3044', '健鼎',       'PCB',      '中型領息', None, '昂貴',   '2025-07-10'),
    ('2393', '億光',       'LED',      '中型成長', 3.9,  '合理',   '2025-07-31'),
    ('2228', '劍麟',       '汽車零件',   '小型成長', None, '合理',   '2025-07-08'),
    ('3005', '神基',       '工業電腦',   '中型成長', 6.6,  '便宜',   '2026-03-25'),
    ('6192', '巨路',       '儀控設備',   '小型成長', 6.3,  '合理',   '2026-04-23'),
    ('2480', '敦陽科',      '資訊軟體',   '小型成長', 7.6,  '殷實',   '2025-06-18'),
    ('6214', '精誠',       '資訊軟體',   '中型領息', 5.2,  '昂貴',   '2025-06-24'),
    ('1722', '台肥',       '資產股',    '深度價值', None, '實惠',   '2025-09-02'),
    ('9911', '櫻花',       '廚具',      '小型成長', 5.5,  '實惠',   '2026-04-01'),
    ('2347', '聯強',       '電子通路',   '大型成長', 4.2,  '合理',   '2025-06-23'),
    ('2891', '中信金',      '金控',      '大型領息', 2.6,  '合理',   '2025-07-14'),
    ('2850', '新產',       '產險',      '小型成長', 8.0,  '實惠',   '2025-06-27'),
    ('2330', '台積電',      '半導體',    '大型成長', 30.0, '合理',   '2026-06-11'),
    ('6605', '帝寶',       '汽車零件',   '中型成長', 9.5,  '便宜',   '2025-07-10'),
    ('2603', '長榮',       '貨櫃海運',   '大型成長', 10.5, '合理',   '2025-06-19'),
    ('8016', '矽創',       '驅動IC',    '中型成長', 13.0, '實惠',   '2025-06-16'),
    ('4105', '東洋',       '醫藥',      '小型成長', 4.8,  '實惠',   '2026-03-26'),
    ('6005', '群益證',      '證券',      '中型成長', 0.4,  '合理',   '2026-07-01'),  # 含股票股利1.31元，老師第一大持股137張
]

# 謝富旭老師持股與研究筆記
HSIEH_NOTES = {
    '6605': {
        'holding': '13.5張（從50張停損至13.5張，佔7.7%）',
        'thesis': '汽車零件成長股，但受關稅+台幣升值衝擊',
        'stop_loss': '2025年在160-150元間大幅停損，停損金額達160萬。從55%降至7.7%',
        'lesson': '第787期教訓：單一持股比重不超過20%',
        'updated': '2026-04-24（第787期）',
    },
    '6005': {
        'holding': '137張（第一大持股，佔17.1%）+ 最近從榮運等價轉移加碼',
        'thesis': '結構性成長股：利息收入CAGR 23.4%、借券CAGR 25.4%、財管CAGR 17.9%',
        'dividend': '2026年配0.4元現金+1.31元股票（睽違7年首度配股）',
        'key_metric': '2026年需賺65億才能EPS不墜（Q1已達30.86億=47.5%）。4月單月淨利若達12億，前4月EPS達1.85元',
        'catalyst': '5/7收盤後公布4月獲利。4月台股漲19.4%+櫃買28.4%，單月挑戰1月18.12億',
        'target': 'EPS達4元→對應股價36-38元',
        'risk': '自營部3月台股跌10%仍獲利4.12億（同業虧損）',
        'updated': '2026-04-22（第786期）',
    },
    '2850': {
        'holding': '存股池',
        'thesis': '產險第三，50%營收來自車險。2025淨利年增17.22%',
        'catalyst': '4/29公布Q1財報。預估Q1 EPS 3.5元→全年上修至14元→2027配息8.4元→合理價140-168元',
        'key_metric': '2026年1月交通事故減少0.9%（對新產有利）。富邦產Q1淨利成長59.9%',
        'updated': '2026-04-22（第786期）',
    },
    '9911': {
        'holding': '存股池',
        'thesis': '廚具龍頭，營收獲利連續10年歷史新高。Q1營收29.1億年增5.45%創歷史單季最高',
        'catalyst': '預估Q1 EPS挑戰2元→全年EPS期望8元→PE14倍→目標112元（+20%套利空間）',
        'key_metric': '參考2025年5/8公布Q1財報',
        'updated': '2026-04-22（第786期）',
    },
    '2385': {'holding': '存股池', 'thesis': '電腦周邊成長股'},
    '2330': {'holding': '存股池', 'thesis': '半導體龍頭，21-23倍PE合理'},
    '2603': {'holding': '存股池', 'thesis': '貨櫃海運，0.65-0.85倍PB合理'},
    '6192': {'holding': '存股池', 'thesis': '儀控設備小型成長股'},
    '2607': {
        'holding': '已減碼（等價轉移至新產+群益證）',
        'thesis': '獲利符合預期但股價不給力，殖利率5.9%不如新產6.45%',
        'updated': '2026-04-24（第787期）',
    },
}

# ━━━ 謝富旭停損三原則（第787期 2026/4/24）━━━
HSIEH_STOP_LOSS_RULES = {
    'rule_1': {
        'name': '扛不住了',
        'desc': '持股比重太高，超出風險承受度',
        'example': '帝寶50張佔55%，跌20%損失200萬佔總部位10% → 扛不住',
        'threshold': '單一持股若跌20%，損失佔總部位>5% → 該減碼',
    },
    'rule_2': {
        'name': '判斷錯誤',
        'desc': 'EPS期望值達不到，營收/獲利不如預期',
        'example': '崧騰、黑松、廣隆、群光',
        'threshold': '實際EPS < 期望值的80% → 認錯停損',
    },
    'rule_3': {
        'name': '等價轉移',
        'desc': '獲利符合預期但股價不給力，發現更好標的',
        'example': '減碼榮運(殖5.9%)→轉移新產(殖6.45%)，業績+動能更優',
        'threshold': '找到殖利率更高+成長更強的替代標的',
    },
}

# ━━━ 蝌蚪投資法修正版（第787期）━━━
HSIEH_POSITION_RULES = {
    'max_single': 20,        # 單一持股不超過20%
    'tadpole_head_count': '3-5檔',  # 蝌蚪頭持股3-5檔（不只1-2檔）
    'fatal_loss': 40,        # 整體部位虧損40%以上 = 致命錯誤
    'total_portfolio': 2250,  # 老師台股部位2250萬元（2026/4）
}

# 第786期 短線套利標的（Event-driven，持有最多3週）
HSIEH_SHORT_TERM = {
    '2850': {
        'type': 'Q1財報驚喜',
        'trigger_date': '2026-04-29',
        'thesis': 'Q1 EPS預估3.5元→上修全年至14元→配息8.4元→合理價140-168元',
        'entry': '現價125.5',
        'exit': '財報公布後1-2週',
    },
    '6005': {
        'type': '4月獲利驚喜',
        'trigger_date': '2026-05-07',
        'thesis': '4月單月淨利挑戰12-18億→前4月EPS 1.85元→全年EPS挑戰4元→目標36-38元',
        'entry': '現價28',
        'exit': '4月獲利公布後1-2週',
    },
    '9911': {
        'type': 'Q1財報驚喜',
        'trigger_date': '2026-05-08（預估）',
        'thesis': 'Q1 EPS挑戰2元→全年EPS 8元期望→PE14倍→目標112元',
        'entry': '現價84',
        'exit': '財報公布後1-2週',
    },
}

# ETF 估價（第786期 2026/4/22更新）
HSIEH_ETF = [
    # (代號, 名稱, 2027預估配息, 股價, 便宜價, 合理價區間, 昂貴價, 位階)
    ('00713', '元大台灣高息低波', 3.4, 54.1, 52.3, '52.3~61.8', 61.8, '合理'),
    ('0056',  '元大高股息',       3.6, 42.61, 48.0, '48~55.4', 55.4, '便宜'),
    ('00891', '中信關鍵半導體',   1.8, 30.0, 32.7, '32.7~40', 40.0, '便宜'),
    ('00927', '群益半導體收益',   1.7, 29.14, 34.0, '34~42.5', 42.5, '便宜'),
    ('00878', '國泰永續高股息',   1.8, 25.1, 24.0, '24~27.7', 27.7, '合理'),
    ('00919', '群益台灣精選高息', 2.5, 23.94, 31.3, '31.3~35.7', 35.7, '便宜'),
    ('00918', '大華優利高填息',   2.5, 23.83, 31.3, '31.3~35.7', 35.7, '便宜'),
    ('00751B','元大AAA至A公司債', 1.36, 31.93, 24.7, '24.7~27.2', 27.2, '昂貴'),
    ('00720B','元大投資級公司債', 1.54, 33.51, 25.7, '25.7~28', 28.0, '昂貴'),
    ('00945B','凱基美國非投等債', 1.1, 14.43, 14.7, '14.7~16.9', 16.9, '便宜'),
]


class HsiehWatchlist:
    """追蹤謝富旭老師選股清單的即時狀態"""

    ZONE_MAP = {'便宜': '🔴', '合理': '🟢', '殷實': '🔵', '實惠': '🔵', '昂貴': '🟣'}

    def __init__(self, mongo_uri: str = None, db_name: str = "tw_stock_analysis"):
        uri = mongo_uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self.db = MongoClient(uri)[db_name]

    def report(self) -> List[Dict]:
        """產出完整追蹤報告"""
        results = []
        for sym, name, industry, attr, est_div, zone, ex_date in HSIEH_PICKS:
            # 即時資料
            p = self.db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
            f = self.db.stock_factors.find_one({'symbol': sym}, sort=[('date', -1)])

            price = _tof(p['close']) if p else None
            pe = _tof(f.get('pe_ratio')) if f else None
            pb = _tof(f.get('pb_ratio')) if f else None
            dy_sys = _tof(f.get('dividend_yield')) if f else None

            # 量價因子（stock_factors volume factors）
            vol_ratio = _tof(f.get('volume_ratio')) if f else None
            vol_pct   = _tof(f.get('vol_pct_60d')) if f else None
            obv_slope = _tof(f.get('obv_slope')) if f else None
            vp_div    = f.get('vp_divergence') if f else None
            volume_tag = _volume_tag(vol_ratio, vol_pct, obv_slope, vp_div)

            # 用老師的預估配息算即時殖利率
            est_yield = (est_div / price * 100) if est_div and price else None

            # 價格變化（vs 4/13 基準）
            base_prices = {
                '6525': 85.2, '4506': 121.5, '6914': 151, '2385': 125,
                '6412': 81.6, '3010': 136, '4958': 257.5, '3044': 373.5,
                '2393': 71.4, '2228': 91.3, '3005': 98.5, '6192': 118.5,
                '2480': 138.5, '6214': 116, '1722': 46.95, '9911': 85,
                '2347': 82, '2891': 53.3, '2850': 124.5, '2330': 1990,
                '6605': 134.5, '2603': 200, '8016': 201.5, '4105': 74.7,
                '6005': 28.0,
            }
            base = base_prices.get(sym, price or 0)
            change_pct = ((price - base) / base * 100) if price and base else 0

            # 除息日是否即將到來
            today = datetime.now()
            try:
                ex_dt = datetime.strptime(ex_date, '%Y-%m-%d')
                days_to_ex = (ex_dt - today).days
                ex_status = '🟡即將' if 0 < days_to_ex <= 30 else ('✅已過' if days_to_ex < 0 else f'{days_to_ex}天')
            except:
                days_to_ex = None
                ex_status = '—'

            # 老師筆記
            note = HSIEH_NOTES.get(sym, {})

            results.append({
                'symbol': sym, 'name': name, 'industry': industry, 'attr': attr,
                'price': price, 'base_price': base, 'change_pct': round(change_pct, 1),
                'est_div': est_div, 'est_yield': round(est_yield, 2) if est_yield else None,
                'zone': zone, 'zone_icon': self.ZONE_MAP.get(zone, '⚪'),
                'pe': pe, 'pb': pb,
                'volume_ratio': vol_ratio, 'vol_pct_60d': vol_pct,
                'obv_slope': obv_slope, 'vp_divergence': vp_div,
                'volume_tag': volume_tag,
                'ex_date': ex_date, 'ex_status': ex_status, 'days_to_ex': days_to_ex,
                'note': note.get('thesis', ''),
                'holding': note.get('holding', ''),
            })

        return results

    def full_analysis(self) -> List[Dict]:
        """對老師清單每支做主動深度分析（不只追蹤，要給建議）"""
        from src.analysis.financial_health import FinancialHealthAnalyzer
        from src.analysis.valuation_models import ValuationAnalyzer
        from src.analysis.risk_manager import RiskAnalyzer
        from src.strategy.trading_rules import TradingRules
        from src.strategy.hsieh_analysis import HsiehAnalysis
        import csv

        fh, va, ra, tr, ha = FinancialHealthAnalyzer(), ValuationAnalyzer(), RiskAnalyzer(), TradingRules(), HsiehAnalysis()

        # 讀 SenVision 突破
        senvision_hits = set()
        results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results')
        csvs = sorted([f for f in os.listdir(results_dir) if f.startswith('scan_auto_')], reverse=True)
        if csvs:
            bullish = {'W-Bottom', 'HS-Bottom', 'Triple-Bottom', 'Triangle-Up', 'Flag-Rising'}
            with open(os.path.join(results_dir, csvs[0]), encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('狀態') == '剛突破' and row.get('形態') in bullish:
                        senvision_hits.add(row.get('股票代碼', '').strip())

        base_report = self.report()
        results = []

        for r in base_report:
            sym = r['symbol']

            # 財報健康
            health = fh.analyze_stock(sym)
            fs_score = health.get('total_score', 0) if 'error' not in health else None
            fs_grade = health.get('grade', '') if 'error' not in health else '—'
            ttm_eps = health.get('ttm', {}).get('eps') if 'error' not in health else None
            warnings = health.get('warnings', []) if 'error' not in health else []

            # 系統估值
            val = va.analyze(sym)
            sys_upside = val['composite'].get('upside_pct') if not val.get('error') else None

            # 風險
            risk = ra.analyze(sym)
            sharpe = risk['ratios']['sharpe'] if not risk.get('error') else None
            mdd = risk['drawdown']['max_drawdown'] if not risk.get('error') else None
            risk_level = risk['risk_level']['level'] if not risk.get('error') else '—'

            # 北大法則（用老師基準價當成本）
            base = r.get('base_price', r['price'])
            pku = tr.check_stop_loss(sym, base) if base else {}
            pku_action = pku.get('action', '—')
            ma_trend = pku.get('ma_trend', '—')

            # 主力階段
            phase = tr.detect_institution_phase(sym)
            inst_phase = phase.get('phase', '—')

            # 買入三問
            three_q = tr.buy_three_questions(sym)
            q_pass = three_q.get('pass_count', 0)

            # 蔡森型態
            has_breakout = sym in senvision_hits

            # 謝富旭研究分析
            hsieh_r = ha.full_research(sym)
            earnings_surprise = hsieh_r.get('earnings_surprise', {}).get('score', 0)
            is_growth = hsieh_r.get('structural_growth', {}).get('is_growth', False)
            fill_prob = hsieh_r.get('fill_dividend', {}).get('fill_probability', '')

            # 綜合行動建議（加入研究分析）
            action = self._recommend_action(r, fs_score, sharpe, pku_action, inst_phase, q_pass, has_breakout,
                                           earnings_surprise, is_growth, fill_prob)

            results.append({
                **r,
                'fs_score': fs_score, 'fs_grade': fs_grade,
                'ttm_eps': ttm_eps,
                'sys_upside': round(sys_upside, 1) if sys_upside is not None else None,
                'sharpe': round(sharpe, 3) if sharpe is not None else None,
                'mdd': round(mdd, 1) if mdd is not None else None,
                'risk_level': risk_level,
                'pku_action': pku_action,
                'ma_trend': ma_trend,
                'inst_phase': inst_phase,
                'three_q': q_pass,
                'has_breakout': has_breakout,
                'warnings': warnings[:2],
                'action': action,
            })

        return results

    def _recommend_action(self, r, fs_score, sharpe, pku_action, inst_phase, q_pass, has_breakout,
                          earnings_surprise=0, is_growth=False, fill_prob=''):
        """綜合多維度給出行動建議"""
        zone = r.get('zone', '')
        signals = []

        # 老師估價
        if zone == '便宜':
            signals.append(('buy', '老師評便宜'))
        elif zone == '昂貴':
            signals.append(('sell', '老師評昂貴'))

        # 北大法則
        if pku_action == '止損出場':
            signals.append(('sell', '北大止損'))
        elif pku_action == '減碼觀察':
            signals.append(('caution', '北大減碼'))

        # 主力
        if inst_phase == '拉升':
            signals.append(('buy', '主力拉升'))
        elif inst_phase == '出貨':
            signals.append(('sell', '主力出貨'))

        # 蔡森
        if has_breakout:
            signals.append(('buy', '型態突破'))

        # 三問
        if q_pass >= 3:
            signals.append(('buy', '三問通過'))

        # Sharpe
        if sharpe and sharpe > 0.5:
            signals.append(('buy', f'Sharpe{sharpe:+.2f}'))

        # 財報
        if fs_score and fs_score < 50:
            signals.append(('caution', '財報偏弱'))

        # 即將除息
        days = r.get('days_to_ex')
        if days and 0 < days <= 30:
            signals.append(('buy', f'除息倒數{days}天'))

        # 謝富旭研究分析
        if earnings_surprise > 3:
            signals.append(('buy', '財報驚喜'))
        elif earnings_surprise < -1:
            signals.append(('caution', '股價超前'))
        if is_growth:
            signals.append(('buy', '成長股'))
        if fill_prob == '高':
            signals.append(('buy', '填息佳'))

        # 第787期停損三原則檢查
        note = HSIEH_NOTES.get(r.get('symbol', ''), {})
        if note.get('stop_loss'):
            signals.append(('caution', '老師已停損'))

        # ── 基礎判定（不含量價）─────────────────────────────────
        buy_count = sum(1 for s, _ in signals if s == 'buy')
        sell_count = sum(1 for s, _ in signals if s == 'sell')

        BUY_LADDER = ['⚪ 持有', '🟢 可佈局', '🟢 買進', '⭐ 強力買進']
        if sell_count >= 2:
            action, tier = '🔴 減碼', None
        elif sell_count >= 1 and buy_count == 0:
            action, tier = '🟡 觀望', None
        elif buy_count >= 3:
            tier = 3
        elif buy_count >= 2:
            tier = 2
        elif buy_count >= 1:
            tier = 1
        else:
            tier = 0

        # ── 量價否決/升級（強模式：量價可推翻其他訊號）──────────────
        # 來源：stock_factors volume factors。空背或資金流出對「買進方向」評級具否決力，
        # 雙重負面直接否決為觀望；爆量/多背 + 資金流入可單獨升級一級。
        vol_reason = ''
        if tier is not None:  # 僅對買進方向評級套用否決/升級
            vp = r.get('vp_divergence')
            obv = r.get('obv_slope')
            vr = r.get('volume_ratio')
            vpct = r.get('vol_pct_60d')
            bear_div = (vp == -1)                                    # 量價空背
            bear_flow = (obv is not None and obv < 0)                # 資金流出
            strong_bull = (vp == 1 and obv is not None and obv > 0) or \
                          (((vr is not None and vr >= 2.0) or (vpct is not None and vpct >= 90))
                           and obv is not None and obv > 0)
            if bear_div and bear_flow:
                action, tier, vol_reason = '🟡 觀望', None, '量價背離'   # 雙重負面 → 否決為觀望
            elif bear_div or bear_flow:
                tier = max(0, tier - 1)                               # 單一負面 → 降一級
                vol_reason = '量價空背' if bear_div else '資金流出'
            elif strong_bull:
                tier = min(3, tier + 1)                               # 強多頭量價 → 升一級
                vol_reason = '量價多背' if vp == 1 else '爆量進場'
            if tier is not None:
                action = BUY_LADDER[tier]

        # 理由：有量價否決/升級時保留前 2 個主訊號 + 量價理由，否則前 3 個
        if vol_reason:
            head = '、'.join(reason for _, reason in signals[:2])
            reasons = (head + '、' + vol_reason) if head else vol_reason
        else:
            reasons = '、'.join(reason for _, reason in signals[:3])
        return f"{action}（{reasons}）" if reasons else action

    def line_analysis(self) -> str:
        """產出含主動分析的 LINE 訊息"""
        results = self.full_analysis()
        d = datetime.now().strftime('%m/%d')
        lines = [f"📕 謝富旭清單主動分析 ({d})\n"]

        # 按行動分組
        strong_buy = [r for r in results if '強力買進' in r['action']]
        buy = [r for r in results if '買進' in r['action'] or '可佈局' in r['action']]
        hold = [r for r in results if '持有' in r['action']]
        caution = [r for r in results if '觀望' in r['action'] or '減碼' in r['action']]

        if strong_buy:
            lines.append("⭐ 強力買進")
            for r in strong_buy:
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} {r['action']}"
                             f"{(' 📊' + r['volume_tag']) if r.get('volume_tag') else ''}")

        if buy:
            lines.append("\n🟢 買進/佈局")
            for r in buy:
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} {r['action']}"
                             f"{(' 📊' + r['volume_tag']) if r.get('volume_tag') else ''}")

        if caution:
            lines.append("\n🟡 觀望/減碼")
            for r in caution:
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} {r['action']}"
                             f"{(' 📊' + r['volume_tag']) if r.get('volume_tag') else ''}")

        if hold:
            lines.append(f"\n⚪ 持有（{len(hold)}支）")
            for r in hold[:5]:
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f}")
            if len(hold) > 5:
                lines.append(f"  ...等 {len(hold)} 支")

        # 短線套利機會
        if HSIEH_SHORT_TERM:
            lines.append(f"\n📌 短線套利（第786期）")
            today = datetime.now()
            for sym, info in HSIEH_SHORT_TERM.items():
                name_r = next((r for r in results if r['symbol'] == sym), None)
                name = name_r['name'] if name_r else sym
                price = name_r['price'] if name_r else 0
                try:
                    trigger = datetime.strptime(info['trigger_date'][:10], '%Y-%m-%d')
                    days = (trigger - today).days
                    countdown = f"倒數{days}天" if days > 0 else "已到期"
                except:
                    countdown = info['trigger_date']
                lines.append(f"  ⏰ {sym} {name} {price:.0f} {info['type']} {countdown}")

        return '\n'.join(lines)

    def line_summary(self) -> str:
        """產出 LINE 訊息"""
        results = self.report()
        d = datetime.now().strftime('%m/%d')
        lines = [f"📕 謝富旭清單追蹤 ({d})\n"]

        # 按估價位階分組
        cheap = [r for r in results if r['zone'] == '便宜']
        fair = [r for r in results if r['zone'] == '合理']
        solid = [r for r in results if r['zone'] in ('殷實', '實惠')]
        expensive = [r for r in results if r['zone'] == '昂貴']

        if cheap:
            lines.append("🔴 便宜（積極買）")
            for r in cheap:
                ex = f" 🟡{r['ex_date'][5:]}" if r.get('days_to_ex') and 0 < r['days_to_ex'] <= 60 else ''
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} "
                             f"殖{r['est_yield']:.1f}% {r['change_pct']:+.1f}%{ex}")

        if fair:
            lines.append("\n🟢 合理（分批佈局）")
            for r in fair:
                ex = f" 🟡{r['ex_date'][5:]}" if r.get('days_to_ex') and 0 < r['days_to_ex'] <= 60 else ''
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} "
                             f"殖{r['est_yield'] or 0:.1f}% {r['change_pct']:+.1f}%{ex}")

        if solid:
            lines.append("\n🔵 殷實/實惠（持有）")
            for r in solid:
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} {r['change_pct']:+.1f}%")

        if expensive:
            lines.append("\n🟣 昂貴（觀望/減碼）")
            for r in expensive:
                lines.append(f"  {r['symbol']} {r['name']} {r['price']:.0f} {r['change_pct']:+.1f}%")

        # 即將除息
        upcoming = [r for r in results if r.get('days_to_ex') and 0 < r['days_to_ex'] <= 60]
        if upcoming:
            lines.append(f"\n🟡 即將除息（60天內）")
            for r in upcoming:
                lines.append(f"  {r['symbol']} {r['name']} {r['ex_date']} 配{r['est_div'] or '?'}元")

        return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    from dotenv import load_dotenv
    load_dotenv()

    hw = HsiehWatchlist()
    results = hw.report()

    print(f"\n{'═'*90}")
    print(f"  📕 謝富旭老師選股清單即時追蹤（{len(results)} 支）")
    print(f"{'═'*90}\n")
    print(f"  {'代號':<7} {'名稱':<8} {'產業':<8} {'屬性':<6} {'現價':>7} {'vs4/13':>7} "
          f"{'預估息':>5} {'殖利':>5} {'位階':<6} {'除息':<12}")
    print(f"  {'─'*90}")

    for r in results:
        div_s = f"{r['est_div']:.1f}" if r['est_div'] else '  ?'
        dy_s = f"{r['est_yield']:.1f}%" if r['est_yield'] else '  ?'
        print(f"  {r['symbol']:<7} {r['name']:<8} {r['industry']:<8} {r['attr']:<6} "
              f"{r['price'] or 0:>7.1f} {r['change_pct']:>+6.1f}% "
              f"{div_s:>5} {dy_s:>5} {r['zone_icon']}{r['zone']:<4} {r['ex_status']:<4} {r['ex_date']}")

    print(f"\n{'─'*90}")
    print(hw.line_summary())
