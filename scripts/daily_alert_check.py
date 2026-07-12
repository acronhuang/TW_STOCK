#!/usr/bin/env python3
"""
每日警報檢查腳本（由 launchd 排程執行）
======================================
1. 檢查所有監控規則（價格/爆量/RSI/大跌）
2. 北大四大法則全檢（5%止損 / MA60 / 均線排列 / 主力階段 / 市場週期）
3. 觸發的警報透過 LINE 發送
4. 收盤後發送每日摘要

Usage:
    python3 scripts/daily_alert_check.py          # 正常檢查
    python3 scripts/daily_alert_check.py --summary # 只發每日摘要
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# 真實持股（券商成交均價，不扣股利）。股數/NAV 讀 portfolio_positions(供 VaR)。
HOLDINGS = {
    '00679B': 29.97, '00687B': 30.59, '00710B': 18.65, '00919':  22.49,
    '1229':   46.74, '1402':   27.80, '1722':   51.90, '1723':   99.00,
    '2603':  213.00, '2706':   12.70, '2812':   19.45, '2845':   12.50,
    '2892':   28.70, '2903':   22.90, '5871':  127.96, '7705':   53.75,
    '8422':   30.38,
    # 6884 海柏特 零成本(抽籤/贈與)→ 不設止損(house money)，僅計入 NAV
}

# 債券 ETF 不適用 5% 止損
BOND_ETFS = {'00679B', '00687B', '00710B'}

# 帳戶分流(心理帳戶)：存股/長期領息標的不適用波段硬性止損。
HOLD_LONG = set()  # 例：{'00919', '2892'} ← 視為長期存股，不硬性止損


def run_pku_rules_check(notifier) -> str:
    """北大四大法則全檢"""
    from src.strategy.trading_rules import TradingRules
    tr = TradingRules()

    lines = [f"📕 北大四大法則日檢 ({datetime.now().strftime('%m/%d %H:%M')})\n"]

    # ① 市場週期
    mc = tr.market_cycle()
    lines.append(f"🌡️ 市場: {mc['description']}")
    lines.append(f"   倉位建議: {mc['suggested_position']}\n")

    # ② 逐一檢查持股
    alerts = []      # 需要注意的
    safe = []        # 安全的
    triggered = []   # 觸發止損→附觸發後檢查清單 [(sym, cost)]

    for sym, cost in HOLDINGS.items():
        if sym in BOND_ETFS:
            continue  # 債券 ETF 跳過止損檢查
        if sym in HOLD_LONG:
            continue  # 存股/長期領息：不適用波段硬性止損(心理帳戶分流)
        if sym == '1722':
            continue  # 零股跳過

        stop = tr.check_stop_loss(sym, cost)
        if stop.get('error'):
            continue

        phase = tr.detect_institution_phase(sym)

        # 分類
        if stop['action'] == '止損出場':
            triggered.append((sym, cost))   # 不論主力階段都納入客觀檢查(壓縮凹單空間)
            # 主力在拉升先標暫抱，但仍會在下方清單用四維數據覆核
            if phase.get('phase') == '拉升':
                alerts.append(
                    f"🟡 {sym} 損{stop['pnl_pct']:+.1f}% 觸5%線"
                    f"（主力拉升→見下方檢查清單覆核）"
                )
            else:
                alerts.append(
                    f"🔴 {sym} 損{stop['pnl_pct']:+.1f}% {stop['ma_trend']}"
                    f" 主力:{phase.get('phase','?')} → {stop['action']}"
                )
        elif stop['action'] == '減碼觀察':
            alerts.append(
                f"⚠️ {sym} 損{stop['pnl_pct']:+.1f}% {stop['ma_trend']}"
                f" → 減碼觀察"
            )
        else:
            # 安全的也檢查主力階段
            p = phase.get('phase', '')
            if p in ('拉升', '建倉'):
                safe.append(f"✅ {sym} {stop['pnl_pct']:+.1f}% 主力{p}")
            else:
                safe.append(f"✅ {sym} {stop['pnl_pct']:+.1f}%")

    if alerts:
        lines.append("━━━ 需注意 ━━━")
        lines.extend(alerts)
    if safe:
        lines.append("\n━━━ 安全持有 ━━━")
        lines.extend(safe)

    # 觸發後檢查清單(四維客觀填答+VaR)——把「主力建倉→暫抱」的凹單藉口攤開覆核
    if triggered:
        from src.strategy.post_trigger import portfolio_snapshot, checklist
        from pymongo import MongoClient
        db = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))['tw_stock_analysis']
        snap = portfolio_snapshot(db)
        lines.append("\n━━━ 📋 止損觸發後檢查清單 ━━━")
        for sym, cost in triggered:
            p = db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
            cl = checklist(db, sym, cost, name=(p or {}).get('name', ''), snapshot=snap)
            if cl:
                lines.append(cl + "\n")

    # 債券 ETF 簡報
    if BOND_ETFS:
        lines.append("\n━━━ 美債 ETF（不適用止損）━━━")
    for sym in BOND_ETFS:
        cost = HOLDINGS[sym]
        from pymongo import MongoClient
        db = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))['tw_stock_analysis']
        p = db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
        if p:
            from bson import Decimal128
            price = float(p['close'].to_decimal()) if isinstance(p['close'], Decimal128) else float(p['close'])
            pnl = (price - cost) / cost * 100
            lines.append(f"⏳ {sym} {pnl:+.1f}%（等降息）")

    msg = '\n'.join(lines)
    return msg


def main():
    parser = argparse.ArgumentParser(description='每日警報檢查')
    parser.add_argument('--summary', action='store_true', help='只發每日摘要')
    args = parser.parse_args()

    from src.alerts.line_notifier import AlertManager
    am = AlertManager()

    if not am.notifier.enabled:
        logger.error('LINE 通知未設定，請檢查 .env')
        sys.exit(1)

    logger.info(f'LINE 模式: {am.notifier._mode}')

    if args.summary:
        logger.info('發送每日摘要...')
        am.notify_daily_summary()
        return

    # ━━━ Part 1: 原有警報規則 ━━━
    logger.info('檢查警報規則...')
    triggered = am.check_and_notify()
    logger.info(f'觸發 {len(triggered)} 則警報')

    for t in triggered:
        logger.info(f"  {t['symbol']} {t['alert_type']}: {t['message']}")

    if len(triggered) > 3:
        summary_msg = f"📋 今日警報摘要: {len(triggered)} 則\n"
        for t in triggered[:8]:
            summary_msg += f"• {t['symbol']} {t['alert_type']}\n"
        if len(triggered) > 8:
            summary_msg += f"... 共 {len(triggered)} 則"
        am.notifier.send(summary_msg)

    # ━━━ Part 2: 北大四大法則全檢 ━━━
    logger.info('執行北大四大法則檢查...')
    try:
        pku_msg = run_pku_rules_check(am.notifier)
        am.notifier.send(pku_msg)
        logger.info('北大法則報告已發 LINE')
    except Exception as e:
        logger.error(f'北大法則檢查失敗: {e}')


if __name__ == '__main__':
    main()
