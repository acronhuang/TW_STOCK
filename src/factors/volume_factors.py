#!/usr/bin/env python3
"""
Volume Factors 模組 - 量價因子計算

計算基於成交量與價量關係的因子，寫入 stock_factors（data_source=None / factor_calc）：
- volume_ratio  : 量比 = 當日量 / 前 N 日均量（爆量 / 量縮判定基礎）
- vol_pct_60d   : 成交量在近 60 交易日的百分位 (0~100)，量縮(<20) / 爆量(>90) 用
- obv_slope     : OBV(能量潮) 近 N 日斜率，正規化為「日均量倍數」。正=資金持續流入
- vp_divergence : 量價背離旗標 (-1 空頭背離 / 0 無 / +1 多頭背離)

設計與 momentum_factors.py 一致：每檔每日讀 stock_price 視窗即時計算，回傳 dict。
成交量為 bson.Decimal128，統一以 _to_float() 轉換。
"""

import numpy as np
from typing import Dict, Optional
from datetime import datetime, timedelta
from bson.decimal128 import Decimal128


class VolumeFactors:
    """量價因子計算器"""

    # 量比的均量視窗（前 N 個交易日，不含當日）
    VOL_MA_WINDOW = 20
    # 成交量百分位視窗
    VOL_PCT_WINDOW = 60
    # OBV 斜率與量價背離的觀察視窗
    TREND_WINDOW = 20
    # 真背離(擺動低/高點比對)視窗與參數
    DIVERGENCE_WINDOW = 60   # 找擺動低/高點的回看天數
    PIVOT_K = 3              # 擺動點強度：左右各 K 根都不更極端才算 pivot
    FRESH_DAYS = 8           # 第二個 pivot 距今 ≤ 此天數才算「剛浮現」(供每日選股榜)
    # 框架量價狀態參數
    CAP_LOW_WINDOW = 20      # 絕望量：價創此窗新低
    CAP_VOL_PCT = 88         # 絕望量：當日量能百分位 ≥ 此值(區間極限量)
    CHOKE_RATIO = 0.12       # 窒息量：當日量 ≤ 近60日最大量 × 此比率(框架≈1/10)
    LOCK_UP_WINDOW = 5       # 鎖籌：近此窗收盤上漲

    def __init__(self, db):
        self.db = db
        self._shares_map = None      # {stock_id: 流通股數(千股)}，首次用時載入並快取

    def _to_float(self, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        try:
            return float(str(value).replace(',', ''))   # 相容字串(含千分位)：amount/transaction 常為 str
        except (ValueError, TypeError):
            return None

    def _load_series(self, symbol: str, date: datetime, lookback_days: int = 130):
        """
        載入 [date-lookback, date] 的收盤價與成交量序列（依日期升冪）。
        回傳 (closes, volumes) 兩個 np.array(float)，已對齊、剔除無效值；不足則回傳 (None, None)。
        """
        start = date - timedelta(days=lookback_days)
        rows = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': start, '$lte': date}},
            {'close': 1, 'adj_close': 1, 'volume': 1, 'date': 1},
        ).sort('date', 1))

        closes, vols = [], []
        for r in rows:
            c = self._to_float(r.get('adj_close', r.get('close')))
            v = self._to_float(r.get('volume'))
            if c is None or v is None:
                continue
            closes.append(c)
            vols.append(v)

        if len(closes) < 2:
            return None, None
        return np.array(closes, dtype=float), np.array(vols, dtype=float)

    # ── 個別因子 ────────────────────────────────────────────────────────

    def calculate_volume_ratio(self, vols: np.ndarray) -> Optional[float]:
        """量比 = 當日量 / 前 VOL_MA_WINDOW 日均量。>1 放量、<1 量縮。"""
        if len(vols) < 2:
            return None
        window = vols[-(self.VOL_MA_WINDOW + 1):-1]  # 前 N 日，不含當日
        if len(window) == 0:
            return None
        base = float(np.mean(window))
        if base <= 0:
            return None
        return round(float(vols[-1]) / base, 3)

    def calculate_vol_percentile(self, vols: np.ndarray) -> Optional[float]:
        """當日量在近 VOL_PCT_WINDOW 日的百分位 (0~100)。"""
        window = vols[-self.VOL_PCT_WINDOW:]
        if len(window) < 10:
            return None
        today = vols[-1]
        pct = float(np.sum(window <= today)) / len(window) * 100.0
        return round(pct, 1)

    @staticmethod
    def _compute_obv(closes: np.ndarray, vols: np.ndarray) -> np.ndarray:
        """OBV 能量潮：漲日 +量、跌日 -量、平盤不變，累積。"""
        direction = np.sign(np.diff(closes))           # -1/0/1，長度 N-1
        obv = np.concatenate([[0.0], np.cumsum(direction * vols[1:])])
        return obv

    def calculate_obv_slope(self, closes: np.ndarray, vols: np.ndarray) -> Optional[float]:
        """
        OBV 近 TREND_WINDOW 日的線性回歸斜率，除以日均量正規化
        → 單位約為「每日流入幾倍日均量」。正=資金流入，負=流出。
        """
        if len(closes) < self.TREND_WINDOW + 1:
            return None
        obv = self._compute_obv(closes, vols)
        seg = obv[-self.TREND_WINDOW:]
        x = np.arange(len(seg), dtype=float)
        slope = float(np.polyfit(x, seg, 1)[0])
        avg_vol = float(np.mean(vols[-self.TREND_WINDOW:]))
        if avg_vol <= 0:
            return None
        return round(slope / avg_vol, 4)

    @staticmethod
    def _pivot_lows(arr: np.ndarray, k: int) -> list:
        """擺動低點索引：arr[i] ≤ 左右各 k 根。連續平台只取首個。"""
        out = []
        for i in range(k, len(arr) - k):
            if arr[i] <= arr[i - k:i].min() and arr[i] <= arr[i + 1:i + k + 1].min():
                if not out or i - out[-1] > k:      # 去除相鄰群聚
                    out.append(i)
        return out

    @staticmethod
    def _pivot_highs(arr: np.ndarray, k: int) -> list:
        """擺動高點索引：arr[i] ≥ 左右各 k 根。"""
        out = []
        for i in range(k, len(arr) - k):
            if arr[i] >= arr[i - k:i].max() and arr[i] >= arr[i + 1:i + k + 1].max():
                if not out or i - out[-1] > k:
                    out.append(i)
        return out

    def detect_obv_divergence(self, closes: np.ndarray, vols: np.ndarray) -> Dict:
        """
        真量價背離（近 DIVERGENCE_WINDOW 日，以擺動低/高點比對 OBV）：
          底背離(bottom)：價格『更低的低點』但 OBV『抬高的低點』+ 現價在區間下半 → 賣壓衰竭、底部承接
          頂背離(top)   ：價格『更高的高點』但 OBV『走低的高點』+ 現價在區間上半 → 追價無量、頭部警示
        回傳 dict（無訊號則 bottom/top 為 None），供旗標與每日選股榜共用。
        """
        n = len(closes)
        if n < self.PIVOT_K * 2 + 4:
            return {'flag': None, 'bottom': None, 'top': None, 'pos': None}
        win = min(self.DIVERGENCE_WINDOW, n)
        c = closes[-win:]
        obv = self._compute_obv(closes, vols)[-win:]    # 切窗不影響窗內兩點差值
        rng = float(c.max() - c.min())
        pos = float((c[-1] - c.min()) / rng) if rng > 0 else 0.5   # 現價區間位置 0=最低,1=最高
        obv_rng = float(obv.max() - obv.min()) or 1.0              # 以視窗振幅正規化(避免跨零失真)

        bottom = None
        lows = self._pivot_lows(c, self.PIVOT_K)
        if len(lows) >= 2:
            l1, l2 = lows[-2], lows[-1]
            if c[l2] < c[l1] and obv[l2] > obv[l1] and pos <= 0.5:
                bottom = {
                    'price_ll': round((c[l1] - c[l2]) / c[l1], 4),         # 價低點再低 %
                    'obv_hl': round((obv[l2] - obv[l1]) / obv_rng, 4),     # OBV 低點抬高(佔視窗振幅)
                    'pos': round(pos, 3),
                    'recent': int(win - 1 - l2),                           # 第二低點距今幾根
                    'rebound': bool(c[-1] > c[l2]),                        # 是否已自低點反彈
                }

        top = None
        highs = self._pivot_highs(c, self.PIVOT_K)
        if len(highs) >= 2:
            h1, h2 = highs[-2], highs[-1]
            if c[h2] > c[h1] and obv[h2] < obv[h1] and pos >= 0.5:
                top = {
                    'price_hh': round((c[h2] - c[h1]) / c[h1], 4),
                    'obv_lh': round((obv[h1] - obv[h2]) / obv_rng, 4),
                    'pos': round(pos, 3),
                    'recent': int(win - 1 - h2),
                }

        flag = 1 if bottom else (-1 if top else 0)
        return {'flag': flag, 'bottom': bottom, 'top': top, 'pos': round(pos, 3)}

    def calculate_vp_divergence(self, closes: np.ndarray, vols: np.ndarray) -> Optional[int]:
        """量價背離旗標 -1/0/+1（沿用既有欄位，改用真擺動低/高點背離）。"""
        if len(closes) < self.PIVOT_K * 2 + 4:
            return None
        return self.detect_obv_divergence(closes, vols)['flag']

    # ── 框架量價狀態（價跌量增絕望量 / 窒息量 / 鎖籌）────────────────────

    def detect_capitulation(self, closes: np.ndarray, vols: np.ndarray) -> bool:
        """絕望量(框架版底背離)：價創近 CAP_LOW_WINDOW 日新低 + 當日量為區間極限量。
        對應『價跌量增』——恐慌拋售/主力承接的潛在落底。"""
        if len(closes) < self.CAP_LOW_WINDOW + 1:
            return False
        is_new_low = closes[-1] <= closes[-self.CAP_LOW_WINDOW:].min() * 1.003
        vpct = self.calculate_vol_percentile(vols)
        return bool(is_new_low and vpct is not None and vpct >= self.CAP_VOL_PCT)

    def detect_choke(self, vols: np.ndarray) -> bool:
        """窒息量：當日量 ≤ 近60日最大量 × CHOKE_RATIO（賣壓竭盡）。"""
        seg = vols[-self.VOL_PCT_WINDOW:] if len(vols) >= self.VOL_PCT_WINDOW else vols
        vmax = float(seg.max())
        return bool(vmax > 0 and vols[-1] <= vmax * self.CHOKE_RATIO)

    def detect_chip_lock(self, closes: np.ndarray, vols: np.ndarray) -> bool:
        """鎖籌(量縮上漲)：窒息或量縮(量比≤0.7) + 近 LOCK_UP_WINDOW 日上漲 + 非高檔(區間≤0.7)。
        框架特例：價漲量縮並非背離，而是主力高度控盤(如祥碩/豐泰/儒鴻窒息量後噴發)。"""
        n = len(closes)
        if n < max(self.CAP_LOW_WINDOW, self.LOCK_UP_WINDOW) + 1:
            return False
        light = self.detect_choke(vols)          # 須真窒息(非僅量比偏低)，貼近「窒息後鎖籌噴發」
        up = closes[-1] > closes[-1 - self.LOCK_UP_WINDOW]
        seg = closes[-self.DIVERGENCE_WINDOW:] if n >= self.DIVERGENCE_WINDOW else closes
        rng = float(seg.max() - seg.min())
        pos = float((closes[-1] - seg.min()) / rng) if rng > 0 else 0.5
        return bool(light and up and pos <= 0.7)

    def volume_state(self, closes: np.ndarray, vols: np.ndarray) -> Optional[str]:
        """彙整單一主導量價狀態(優先序：絕望量 > 鎖籌 > 窒息量)；皆非則 None。"""
        if self.detect_capitulation(closes, vols):
            return '絕望量'
        if self.detect_chip_lock(closes, vols):
            return '鎖籌'
        if self.detect_choke(vols):
            return '窒息量'
        return None

    # ── 彙整 ────────────────────────────────────────────────────────────

    # ── A 補強因子：均額(大單/散單) / 周轉率 ────────────────────────────

    def _load_value_series(self, symbol: str, date: datetime, lookback_days: int = 40):
        """載入近 N 日的 (成交金額, 成交筆數) 序列（升冪，list，缺值為 None）。與 _load_series
        分開，避免動到既有簽名；均額計算不需與收盤對齊，各自過濾即可。"""
        start = date - timedelta(days=lookback_days)
        rows = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': start, '$lte': date}},
            {'amount': 1, 'transaction': 1, 'date': 1},
        ).sort('date', 1))
        amts = [self._to_float(r.get('amount')) for r in rows]
        txns = [self._to_float(r.get('transaction')) for r in rows]
        return amts, txns

    def calculate_avg_trade_ratio(self, amts: list, txns: list):
        """每筆均額 = 成交金額 / 成交筆數（元/筆）。回 (avg_trade_value, atv_ratio)。
        atv_ratio = 今日均額 / 前 VOL_MA_WINDOW 日均額 → 大單放大倍數：
        >1.5 常代表大單進場（主力足跡，量價側、當日盤後即得，不必等法人 T+1）。"""
        per = [(a / t) if (a is not None and t is not None and t > 0) else None
               for a, t in zip(amts, txns)]
        if not per or per[-1] is None:
            return None, None
        today = per[-1]
        hist = [p for p in per[-(self.VOL_MA_WINDOW + 1):-1] if p is not None]
        if len(hist) < 5:
            return round(today), None
        base = sum(hist) / len(hist)
        return round(today), (round(today / base, 2) if base > 0 else None)

    def _shares(self, symbol: str) -> Optional[float]:
        """流通股數(千股)，來自 taiwan_stock_info；一次載入全市場快取。"""
        if self._shares_map is None:
            self._shares_map = {d['stock_id']: self._to_float(d.get('outstanding_shares'))
                                for d in self.db.taiwan_stock_info.find(
                                    {}, {'stock_id': 1, 'outstanding_shares': 1})}
        return self._shares_map.get(symbol)

    def calculate_turnover(self, vols: np.ndarray, symbol: str) -> Optional[float]:
        """周轉率(%) = 當日成交量(股) / 流通股數(股) × 100。把量能標準化，不同股本可比。"""
        sh = self._shares(symbol)          # 千股
        if not sh or sh <= 0:
            return None
        return round(float(vols[-1]) / (sh * 1000.0) * 100.0, 3)

    def calculate_all_volume_factors(self, symbol: str, date: datetime) -> Dict:
        """計算單檔單日所有量價因子；資料不足的因子回傳 None。"""
        closes, vols = self._load_series(symbol, date)
        if closes is None:
            return {
                'date': date, 'symbol': symbol,
                'volume_ratio': None, 'vol_pct_60d': None,
                'obv_slope': None, 'vp_divergence': None,
                'avg_trade_value': None, 'atv_ratio': None, 'turnover': None,
            }
        amts, txns = self._load_value_series(symbol, date)
        avg_trade_value, atv_ratio = self.calculate_avg_trade_ratio(amts, txns)
        turnover = self.calculate_turnover(vols, symbol)
        # 框架量價狀態碼(0無/1絕望量/2鎖籌/3窒息量)；存碼而非字串，避免被掃描數值快取丟棄
        vs = self.volume_state(closes, vols)
        vs_code = {'絕望量': 1, '鎖籌': 2, '窒息量': 3}.get(vs, 0)
        return {
            'date': date,
            'symbol': symbol,
            'volume_ratio':  self.calculate_volume_ratio(vols),
            'vol_pct_60d':   self.calculate_vol_percentile(vols),
            'obv_slope':     self.calculate_obv_slope(closes, vols),
            'vp_divergence': self.calculate_vp_divergence(closes, vols),
            'vol_state':     vs_code,
            'avg_trade_value': avg_trade_value,   # 每筆均額(元)
            'atv_ratio':       atv_ratio,         # 均額放大倍數(大單偵測)
            'turnover':        turnover,          # 周轉率(%)
        }
