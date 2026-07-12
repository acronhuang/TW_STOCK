#!/usr/bin/env python3
"""
LINE 警報系統（Messaging API + Notify 雙模式）
=============================================
支援 LINE Messaging API（push message）和 LINE Notify 兩種通知方式。

設定方式（二擇一）：

方式一：LINE Messaging API（推薦）
  在 .env 設定：
    LINE_CHANNEL_ID=<your_channel_id>
    LINE_CHANNEL_SECRET=<your_channel_secret>
    LINE_CHANNEL_ACCESS_TOKEN=<auto_generated>
    LINE_USER_ID=<your_user_id>

方式二：LINE Notify
  在 .env 設定：
    LINE_NOTIFY_TOKEN=<your_token>

Usage:
    from src.alerts.line_notifier import AlertManager
    am = AlertManager()
    am.check_and_notify()  # 檢查所有規則並發送通知
"""

import os
import sys
import json
import logging
import requests
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

LINE_NOTIFY_URL = 'https://notify-api.line.me/api/notify'
LINE_MESSAGING_API_URL = 'https://api.line.me/v2/bot/message/push'
LINE_BROADCAST_API_URL = 'https://api.line.me/v2/bot/message/broadcast'
LINE_OAUTH_URL = 'https://api.line.me/v2/oauth/accessToken'


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class LineNotifier:
    """LINE 訊息發送器（支援 Messaging API + Notify）"""

    def __init__(self, token: str = None, user_id: str = None):
        # 優先使用 Messaging API
        self.channel_id = os.getenv('LINE_CHANNEL_ID', '')
        self.channel_secret = os.getenv('LINE_CHANNEL_SECRET', '')
        self.access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '')
        self.user_id = user_id or os.getenv('LINE_USER_ID', '')

        # 備用：LINE Notify
        self.notify_token = token or os.getenv('LINE_NOTIFY_TOKEN', '')

        self._mode = self._detect_mode()
        if not self.enabled:
            logger.warning('LINE 通知未設定（需 Messaging API 或 Notify token）')
        else:
            logger.info(f'LINE 通知模式: {self._mode}')

    def _detect_mode(self) -> str:
        if self.access_token and self.user_id:
            return 'messaging_push'
        if self.channel_id and self.channel_secret:
            self._refresh_token()
            if self.access_token:
                return 'messaging_push' if self.user_id else 'messaging_broadcast'
        if self.notify_token:
            return 'notify'
        return 'disabled'

    def _refresh_token(self):
        """用 Channel ID + Secret 取得 access token"""
        try:
            r = requests.post(LINE_OAUTH_URL, data={
                'grant_type': 'client_credentials',
                'client_id': self.channel_id,
                'client_secret': self.channel_secret,
            }, timeout=10)
            if r.status_code == 200:
                self.access_token = r.json().get('access_token', '')
                logger.info('LINE access token 取得成功')
            else:
                logger.error(f'LINE token 取得失敗: {r.status_code}')
        except Exception as e:
            logger.error(f'LINE token 取得失敗: {e}')

    @property
    def enabled(self) -> bool:
        return self._mode != 'disabled'

    def send(self, message: str) -> bool:
        """發送 LINE 訊息"""
        if self._mode == 'messaging_push':
            return self._send_push(message)
        elif self._mode == 'messaging_broadcast':
            return self._send_broadcast(message)
        elif self._mode == 'notify':
            return self._send_notify(message)
        else:
            logger.warning(f'[LINE 停用] {message}')
            return False

    def _send_push(self, message: str) -> bool:
        """透過 LINE Messaging API push 給指定用戶"""
        return self._send_messaging(LINE_MESSAGING_API_URL, {
            'to': self.user_id,
            'messages': [{'type': 'text', 'text': message.strip()}],
        })

    def _send_broadcast(self, message: str) -> bool:
        """透過 LINE Messaging API 廣播給所有好友"""
        return self._send_messaging(LINE_BROADCAST_API_URL, {
            'messages': [{'type': 'text', 'text': message.strip()}],
        })

    def _send_messaging(self, url: str, body: dict) -> bool:
        """LINE Messaging API 通用發送"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.access_token}',
            }
            r = requests.post(url, headers=headers,
                              data=json.dumps(body), timeout=10)
            if r.status_code == 200:
                logger.info('[LINE ✅] 發送成功')
                return True
            elif r.status_code == 401:
                logger.warning('Token 過期，嘗試刷新...')
                self._refresh_token()
                headers['Authorization'] = f'Bearer {self.access_token}'
                r = requests.post(url, headers=headers,
                                  data=json.dumps(body), timeout=10)
                if r.status_code == 200:
                    logger.info('[LINE ✅] Token 刷新後發送成功')
                    return True
            logger.error(f'[LINE ❌] HTTP {r.status_code}: {r.text}')
            return False
        except Exception as e:
            logger.error(f'[LINE ❌] 發送失敗: {e}')
            return False

    def _send_notify(self, message: str) -> bool:
        """透過 LINE Notify 發送"""
        try:
            headers = {'Authorization': f'Bearer {self.notify_token}'}
            data = {'message': message}
            r = requests.post(LINE_NOTIFY_URL, headers=headers, data=data, timeout=10)
            if r.status_code == 200:
                logger.info('[LINE ✅] Notify 發送成功')
                return True
            else:
                logger.error(f'[LINE ❌] Notify HTTP {r.status_code}: {r.text}')
                return False
        except Exception as e:
            logger.error(f'[LINE ❌] Notify 失敗: {e}')
            return False

    def send_stock_alert(self, symbol: str, name: str, alert_type: str,
                         message: str, price: float = None) -> bool:
        """格式化股票警報"""
        price_str = f' 股價:{price:.2f}' if price else ''
        text = f'📊 {alert_type}\n{symbol} {name}{price_str}\n{message}'
        return self.send(text)


class AlertManager:
    """警報管理器 - 整合各種監控規則"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis",
                 line_token: str = None):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.notifier = LineNotifier(line_token)
        self._ensure_collections()

    def _ensure_collections(self):
        """確保 alert 相關 collection 存在"""
        if 'alert_rules' not in self.db.list_collection_names():
            self.db.create_collection('alert_rules')
        if 'alert_history' not in self.db.list_collection_names():
            self.db.create_collection('alert_history')
            self.db.alert_history.create_index([('timestamp', -1)])
            self.db.alert_history.create_index([('symbol', 1), ('timestamp', -1)])

    # ──────────────────────────────────────────────
    #  監控規則管理
    # ──────────────────────────────────────────────
    def add_price_alert(self, symbol: str, condition: str, target_price: float,
                        note: str = ''):
        """新增價格警報規則
        condition: 'above' | 'below'
        """
        rule = {
            'symbol': symbol,
            'type': 'price',
            'condition': condition,
            'target_price': target_price,
            'note': note,
            'active': True,
            'created_at': datetime.now(timezone.utc),
            'triggered_at': None,
        }
        self.db.alert_rules.update_one(
            {'symbol': symbol, 'type': 'price', 'condition': condition},
            {'$set': rule},
            upsert=True
        )
        logger.info(f'已新增價格警報: {symbol} {condition} {target_price}')

    def add_volume_alert(self, symbol: str, multiplier: float = 2.0):
        """新增爆量警報（成交量 > N 倍均量）"""
        rule = {
            'symbol': symbol,
            'type': 'volume',
            'multiplier': multiplier,
            'active': True,
            'created_at': datetime.now(timezone.utc),
            'triggered_at': None,
        }
        self.db.alert_rules.update_one(
            {'symbol': symbol, 'type': 'volume'},
            {'$set': rule},
            upsert=True
        )

    def add_watchlist(self, symbols: List[str]):
        """批次加入監控清單（啟用所有預設警報）"""
        for sym in symbols:
            self.db.alert_rules.update_one(
                {'symbol': sym, 'type': 'watchlist'},
                {'$set': {
                    'symbol': sym,
                    'type': 'watchlist',
                    'active': True,
                    'created_at': datetime.now(timezone.utc),
                }},
                upsert=True
            )
        logger.info(f'已加入監控清單: {len(symbols)} 支')

    def list_rules(self) -> List[Dict]:
        """列出所有有效規則"""
        return list(self.db.alert_rules.find({'active': True}, {'_id': 0}))

    def remove_rule(self, symbol: str, rule_type: str = None):
        """移除規則"""
        query = {'symbol': symbol}
        if rule_type:
            query['type'] = rule_type
        self.db.alert_rules.update_many(query, {'$set': {'active': False}})

    # ──────────────────────────────────────────────
    #  檢查並觸發警報
    # ──────────────────────────────────────────────
    def check_and_notify(self) -> List[Dict]:
        """檢查所有有效規則，觸發符合條件的警報"""
        triggered = []
        rules = list(self.db.alert_rules.find({'active': True}))

        for rule in rules:
            alerts = self._check_rule(rule)
            for alert in alerts:
                # 防重複：同一警報 24 小時內只發一次
                if self._is_duplicate(alert):
                    continue

                # 發送通知
                name = self._get_stock_name(alert['symbol'])
                self.notifier.send_stock_alert(
                    symbol=alert['symbol'],
                    name=name,
                    alert_type=alert['alert_type'],
                    message=alert['message'],
                    price=alert.get('price'),
                )

                # 記錄歷史
                alert['timestamp'] = datetime.now(timezone.utc)
                alert['name'] = name
                self.db.alert_history.insert_one(alert)
                triggered.append(alert)

        return triggered

    def _check_rule(self, rule: Dict) -> List[Dict]:
        """檢查單一規則"""
        rule_type = rule.get('type')
        if rule_type == 'price':
            return self._check_price_alert(rule)
        elif rule_type == 'volume':
            return self._check_volume_alert(rule)
        elif rule_type == 'watchlist':
            return self._check_watchlist(rule)
        return []

    def _check_price_alert(self, rule: Dict) -> List[Dict]:
        symbol = rule['symbol']
        price = self._get_latest_price(symbol)
        if price is None:
            return []

        target = rule['target_price']
        condition = rule['condition']

        if condition == 'above' and price >= target:
            return [{
                'symbol': symbol,
                'alert_type': '🔺 價格突破',
                'message': f'現價 {price:.2f} 突破 {target:.2f}',
                'price': price,
                'rule_type': 'price',
            }]
        elif condition == 'below' and price <= target:
            return [{
                'symbol': symbol,
                'alert_type': '🔻 價格跌破',
                'message': f'現價 {price:.2f} 跌破 {target:.2f}',
                'price': price,
                'rule_type': 'price',
            }]
        return []

    def _check_volume_alert(self, rule: Dict) -> List[Dict]:
        symbol = rule['symbol']
        multiplier = rule.get('multiplier', 2.0)

        prices = list(self.db.stock_price.find(
            {'symbol': symbol},
            {'date': 1, 'volume': 1, 'close': 1}
        ).sort('date', -1).limit(21))

        if len(prices) < 6:
            return []

        latest_vol = _to_float(prices[0].get('volume'))
        avg_vol = sum(_to_float(p.get('volume', 0)) or 0 for p in prices[1:21]) / min(20, len(prices) - 1)

        if latest_vol and avg_vol and avg_vol > 0 and latest_vol > avg_vol * multiplier:
            ratio = latest_vol / avg_vol
            price = _to_float(prices[0].get('close'))
            return [{
                'symbol': symbol,
                'alert_type': '📈 爆量警報',
                'message': f'成交量 {latest_vol/1000:.0f}千張 = {ratio:.1f}倍均量',
                'price': price,
                'rule_type': 'volume',
            }]
        return []

    def _check_watchlist(self, rule: Dict) -> List[Dict]:
        """監控清單：檢查技術指標異常"""
        symbol = rule['symbol']
        alerts = []

        # RSI 超賣/超買
        factor = self.db.stock_factors.find_one(
            {'symbol': symbol, 'rsi_14': {'$ne': None}},
            {'rsi_14': 1, 'date': 1},
            sort=[('date', -1)]
        )
        if factor:
            rsi = _to_float(factor.get('rsi_14'))
            if rsi is not None:
                if rsi < 30:
                    alerts.append({
                        'symbol': symbol,
                        'alert_type': '🟢 RSI 超賣',
                        'message': f'RSI(14) = {rsi:.1f}，進入超賣區',
                        'price': self._get_latest_price(symbol),
                        'rule_type': 'rsi_oversold',
                    })
                elif rsi > 70:
                    alerts.append({
                        'symbol': symbol,
                        'alert_type': '🔴 RSI 超買',
                        'message': f'RSI(14) = {rsi:.1f}，進入超買區',
                        'price': self._get_latest_price(symbol),
                        'rule_type': 'rsi_overbought',
                    })

        # 大跌警報（單日 -3% 以上）
        prices = list(self.db.stock_price.find(
            {'symbol': symbol},
            {'close': 1, 'date': 1}
        ).sort('date', -1).limit(2))

        if len(prices) >= 2:
            p0 = _to_float(prices[1].get('close'))
            p1 = _to_float(prices[0].get('close'))
            if p0 and p1 and p0 > 0:
                change = (p1 - p0) / p0 * 100
                if change <= -3:
                    alerts.append({
                        'symbol': symbol,
                        'alert_type': '⚠️ 大跌警報',
                        'message': f'日跌幅 {change:.1f}%',
                        'price': p1,
                        'rule_type': 'big_drop',
                    })
                elif change >= 5:
                    alerts.append({
                        'symbol': symbol,
                        'alert_type': '🚀 大漲警報',
                        'message': f'日漲幅 +{change:.1f}%',
                        'price': p1,
                        'rule_type': 'big_rise',
                    })

        return alerts

    # ──────────────────────────────────────────────
    #  掃描結果通知
    # ──────────────────────────────────────────────
    def notify_scan_results(self, scan_results: List[Dict]):
        """將掃描結果透過 LINE 發送摘要"""
        if not scan_results:
            return

        msg = f'\n📊 掃描結果摘要 ({len(scan_results)} 支)'
        for i, r in enumerate(scan_results[:10]):
            sym = r.get('symbol', r.get('stock_id', ''))
            name = r.get('name', '')
            pattern = r.get('pattern_type', r.get('pattern', ''))
            score = r.get('score', r.get('total_score', ''))
            price = r.get('price', r.get('close', ''))
            msg += f'\n{i+1}. {sym} {name}'
            if pattern:
                msg += f' [{pattern}]'
            if score:
                msg += f' 分數:{score}'
            if price:
                msg += f' ${price}'

        if len(scan_results) > 10:
            msg += f'\n... 共 {len(scan_results)} 支'

        self.notifier.send(msg)

    def notify_daily_summary(self):
        """每日摘要通知"""
        today = datetime.now().strftime('%Y-%m-%d')

        # 取今日警報數
        alert_count = self.db.alert_history.count_documents({
            'timestamp': {'$gte': datetime.now(timezone.utc) - timedelta(hours=24)}
        })

        # 取監控股票數
        watch_count = self.db.alert_rules.count_documents({'active': True})

        msg = f'\n📋 每日摘要 {today}'
        msg += f'\n監控規則: {watch_count} 條'
        msg += f'\n今日警報: {alert_count} 則'

        # 附帶大盤資訊
        taiex = self.db.stock_price.find_one(
            {'symbol': '0050'},
            {'close': 1, 'date': 1},
            sort=[('date', -1)]
        )
        if taiex:
            msg += f'\n0050: {_to_float(taiex["close"]):.2f}'

        self.notifier.send(msg)

    # ──────────────────────────────────────────────
    #  輔助方法
    # ──────────────────────────────────────────────
    def _get_latest_price(self, symbol: str) -> Optional[float]:
        rec = self.db.stock_price.find_one(
            {'symbol': symbol}, {'close': 1}, sort=[('date', -1)]
        )
        return _to_float(rec['close']) if rec else None

    def _get_stock_name(self, symbol: str) -> str:
        for col in ['taiwan_stock_info', 'stock_list']:
            try:
                rec = self.db[col].find_one({'stock_id': symbol}, {'name': 1})
                if rec and rec.get('name'):
                    return rec['name']
            except Exception:
                pass
        # 從 stock_price 取 name
        rec = self.db.stock_price.find_one({'symbol': symbol}, {'name': 1})
        if rec and rec.get('name'):
            return rec['name']
        return ''

    def _is_duplicate(self, alert: Dict) -> bool:
        """24 小時內同一股票同類警報不重複發送"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        exists = self.db.alert_history.find_one({
            'symbol': alert['symbol'],
            'rule_type': alert['rule_type'],
            'timestamp': {'$gte': cutoff},
        })
        return exists is not None


# ──────────────────────────────────────────────
#  CLI 測試
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    am = AlertManager()
    print(f'LINE Notify: {"✅ 已設定" if am.notifier.enabled else "❌ 未設定 (需要 LINE_NOTIFY_TOKEN)"}')

    # 示範：加入監控清單
    am.add_watchlist(['2330', '2317', '2454', '0056'])
    am.add_price_alert('2330', 'below', 1700, '台積電跌破支撐')
    am.add_price_alert('2330', 'above', 2000, '台積電突破前高')
    am.add_volume_alert('2330', multiplier=2.0)

    print(f'\n現有規則: {len(am.list_rules())} 條')
    for r in am.list_rules():
        print(f"  {r['symbol']} | {r['type']} | {r.get('condition','')}{r.get('target_price','')}")

    # 檢查警報
    print('\n檢查警報...')
    triggered = am.check_and_notify()
    print(f'觸發 {len(triggered)} 則警報:')
    for t in triggered:
        print(f"  {t['symbol']} {t['alert_type']}: {t['message']}")
