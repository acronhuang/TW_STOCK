#!/usr/bin/env python3
"""
情緒/替代資料分析模組
====================
新聞情緒分析、社群輿情追蹤、內部人交易追蹤。

資料來源：
- 新聞情緒：Google News RSS + 簡易中文情緒詞典
- 內部人交易：MOPS 董監事持股變動 / FinMind API
- 社群輿情：PTT Stock 板 RSS

Usage:
    from src.sentiment.analyzer import SentimentAnalyzer
    sa = SentimentAnalyzer()
    result = sa.analyze('2330')
    print(result['news_sentiment'])
    print(result['insider_trading'])
"""

import os
import sys
import re
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib.parse import quote
import requests
import urllib3
from pymongo import MongoClient
from bson.decimal128 import Decimal128

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# 簡易中文情緒詞典（股市相關）
POSITIVE_WORDS = {
    '漲', '漲停', '大漲', '噴出', '突破', '創新高', '利多', '看好', '看漲',
    '買進', '買超', '加碼', '營收成長', '獲利', '成長', '強勢', '多頭',
    '反彈', '起漲', '轉強', '回升', '穩健', '優於預期', '上修', '亮眼',
    '增持', '樂觀', '佈局', '受惠', '題材', '熱門', '飆漲', '站穩',
    '紅盤', '量增', '攻高', '走揚', '翻紅', '超預期', '爆量上攻',
}

NEGATIVE_WORDS = {
    '跌', '跌停', '大跌', '崩跌', '暴跌', '破底', '創新低', '利空', '看壞',
    '賣出', '賣超', '減碼', '營收衰退', '虧損', '衰退', '弱勢', '空頭',
    '下跌', '破線', '轉弱', '回檔', '疲弱', '低於預期', '下修', '慘淡',
    '減持', '悲觀', '出脫', '套牢', '風險', '警示', '重挫', '失守',
    '綠盤', '量縮', '殺低', '走低', '翻黑', '不如預期', '爆量下殺',
    '戰爭', '制裁', '關稅', '通膨',
}


class SentimentAnalyzer:
    """情緒與替代資料分析"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.finmind_token = os.getenv('FINMIND_API_TOKEN', '')

    def analyze(self, symbol: str) -> Dict:
        """完整情緒分析"""
        name = self._get_stock_name(symbol)

        news = self.news_sentiment(symbol, name)
        insider = self.insider_trading(symbol)
        ptt = self.ptt_sentiment(symbol, name)

        # 綜合情緒分數（-100 到 +100）
        scores = []
        if news and news.get('score') is not None:
            scores.append(('news', news['score'], 0.4))
        if insider and insider.get('score') is not None:
            scores.append(('insider', insider['score'], 0.3))
        if ptt and ptt.get('score') is not None:
            scores.append(('ptt', ptt['score'], 0.3))

        if scores:
            total_w = sum(w for _, _, w in scores)
            composite = sum(s * w for _, s, w in scores) / total_w
        else:
            composite = None

        sentiment = self._score_to_label(composite)

        return {
            'symbol': symbol,
            'name': name,
            'news_sentiment': news,
            'insider_trading': insider,
            'ptt_sentiment': ptt,
            'composite': {
                'score': round(composite, 1) if composite is not None else None,
                'label': sentiment,
                'sources_used': len(scores),
            },
            'updated_at': datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────
    #  新聞情緒分析
    # ──────────────────────────────────────────────
    def news_sentiment(self, symbol: str, name: str = None) -> Dict:
        """從 Google News 抓取新聞並分析情緒"""
        if not name:
            name = self._get_stock_name(symbol)

        search_term = f'{symbol} {name} 股票' if name else f'{symbol} 股票'
        articles = self._fetch_google_news(search_term)

        if not articles:
            return {'score': None, 'articles': [], 'reason': '無法取得新聞'}

        scored_articles = []
        total_score = 0

        for article in articles[:15]:
            title = article.get('title', '')
            score = self._score_text(title)
            scored_articles.append({
                'title': title,
                'source': article.get('source', ''),
                'date': article.get('date', ''),
                'score': score,
                'sentiment': self._score_to_label(score),
            })
            total_score += score

        avg_score = total_score / len(scored_articles) if scored_articles else 0

        positive = sum(1 for a in scored_articles if a['score'] > 0)
        negative = sum(1 for a in scored_articles if a['score'] < 0)
        neutral = sum(1 for a in scored_articles if a['score'] == 0)

        return {
            'score': round(avg_score, 1),
            'label': self._score_to_label(avg_score),
            'articles_count': len(scored_articles),
            'positive': positive,
            'negative': negative,
            'neutral': neutral,
            'articles': scored_articles[:5],  # 只回傳前 5 則
        }

    # ──────────────────────────────────────────────
    #  內部人交易追蹤
    # ──────────────────────────────────────────────
    def insider_trading(self, symbol: str) -> Dict:
        """追蹤董監事持股異動"""
        # 從 FinMind 取得董監事持股變動
        if self.finmind_token:
            data = self._fetch_insider_from_finmind(symbol)
        else:
            data = []

        # 也從本地 DB 查詢（如果有的話）
        local = list(self.db.get_collection('insider_trading', {}).find(
            {'stock_id': symbol},
            {'_id': 0}
        ).sort('date', -1).limit(20)) if 'insider_trading' in self.db.list_collection_names() else []

        records = data or local

        if not records:
            return {'score': None, 'records': [], 'reason': '無內部人交易資料'}

        # 分析：近 3 個月買賣統計
        buy_count = 0
        sell_count = 0
        net_shares = 0

        for r in records:
            change = r.get('change_shares', r.get('shares_change', 0)) or 0
            if isinstance(change, str):
                change = int(change.replace(',', '')) if change else 0
            if change > 0:
                buy_count += 1
                net_shares += change
            elif change < 0:
                sell_count += 1
                net_shares += change

        # 評分：內部人買入 = 正面，賣出 = 負面
        if buy_count + sell_count == 0:
            score = 0
        else:
            buy_ratio = buy_count / (buy_count + sell_count)
            score = (buy_ratio - 0.5) * 200  # -100 to +100

        return {
            'score': round(score, 1),
            'label': self._score_to_label(score),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'net_shares': net_shares,
            'records': records[:5],
        }

    # ──────────────────────────────────────────────
    #  PTT 股票板輿情
    # ──────────────────────────────────────────────
    def ptt_sentiment(self, symbol: str, name: str = None) -> Dict:
        """PTT Stock 板輿情分析"""
        if not name:
            name = self._get_stock_name(symbol)

        # 搜尋 PTT Stock 板
        posts = self._fetch_ptt_stock(symbol, name)

        if not posts:
            return {'score': None, 'posts': [], 'reason': '無 PTT 資料'}

        scored_posts = []
        total_score = 0

        for post in posts[:20]:
            title = post.get('title', '')
            score = self._score_text(title)

            # PTT 特殊標記加權
            if title.startswith('[多]') or '多' in title[:5]:
                score += 20
            elif title.startswith('[空]') or '空' in title[:5]:
                score -= 20

            scored_posts.append({
                'title': title,
                'date': post.get('date', ''),
                'score': score,
            })
            total_score += score

        avg_score = total_score / len(scored_posts) if scored_posts else 0

        bullish = sum(1 for p in scored_posts if p['score'] > 0)
        bearish = sum(1 for p in scored_posts if p['score'] < 0)

        return {
            'score': round(avg_score, 1),
            'label': self._score_to_label(avg_score),
            'posts_count': len(scored_posts),
            'bullish': bullish,
            'bearish': bearish,
            'posts': scored_posts[:5],
        }

    # ──────────────────────────────────────────────
    #  市場整體情緒指標
    # ──────────────────────────────────────────────
    def market_sentiment(self) -> Dict:
        """市場整體情緒（融資融券、外資動向、漲跌比）"""
        # 漲跌家數比
        latest_date = self.db.stock_price.find_one(
            {}, {'date': 1}, sort=[('date', -1)])
        if not latest_date:
            return {'error': '無資料'}

        date = latest_date['date']

        # 統計當日漲跌
        prices = list(self.db.stock_price.find(
            {'date': date},
            {'symbol': 1, 'close': 1}
        ))

        up = down = flat = 0
        for p in prices:
            # 取前一日收盤價比較
            prev = self.db.stock_price.find_one(
                {'symbol': p['symbol'], 'date': {'$lt': date}},
                {'close': 1},
                sort=[('date', -1)]
            )
            if prev:
                c0 = _to_float(prev['close'])
                c1 = _to_float(p['close'])
                if c0 and c1:
                    if c1 > c0:
                        up += 1
                    elif c1 < c0:
                        down += 1
                    else:
                        flat += 1

        # 外資買賣超
        flows = list(self.db.institutional_flow.find(
            {'date': date},
            {'foreign_net': 1}
        ))
        foreign_net = sum(_to_float(f.get('foreign_net', 0)) or 0 for f in flows)

        # 情緒分數
        total = up + down + flat
        if total > 0:
            ad_ratio = up / total
            score = (ad_ratio - 0.5) * 200
        else:
            score = 0

        if foreign_net > 0:
            score += 10
        elif foreign_net < 0:
            score -= 10

        return {
            'date': str(date)[:10],
            'advance': up,
            'decline': down,
            'flat': flat,
            'ad_ratio': round(up / total * 100, 1) if total > 0 else 0,
            'foreign_net': round(foreign_net),
            'score': round(score, 1),
            'label': self._score_to_label(score),
        }

    # ──────────────────────────────────────────────
    #  資料抓取
    # ──────────────────────────────────────────────
    def _fetch_google_news(self, query: str) -> List[Dict]:
        """從 Google News RSS 取新聞"""
        try:
            url = f'https://news.google.com/rss/search?q={quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
            r = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            })
            if r.status_code != 200:
                return []

            root = ET.fromstring(r.content)
            articles = []
            for item in root.findall('.//item'):
                title = item.findtext('title', '')
                source = item.findtext('source', '')
                pub_date = item.findtext('pubDate', '')
                articles.append({
                    'title': title,
                    'source': source,
                    'date': pub_date,
                })
            return articles
        except Exception as e:
            logger.warning(f'Google News 抓取失敗: {e}')
            return []

    def _fetch_insider_from_finmind(self, symbol: str) -> List[Dict]:
        """從 FinMind 取內部人持股異動"""
        try:
            start = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            r = requests.get('https://api.finmindtrade.com/api/v4/data', params={
                'dataset': 'TaiwanStockShareholding',
                'data_id': symbol,
                'start_date': start,
                'token': self.finmind_token,
            }, timeout=15)

            if r.status_code != 200:
                return []

            data = r.json().get('data', [])
            records = []
            for d in data:
                records.append({
                    'date': d.get('date', ''),
                    'name': d.get('name', ''),
                    'title': d.get('title', ''),
                    'shares_hold': d.get('HoldingShares', 0),
                    'change_shares': d.get('HoldingSharesChange', 0),
                })
            return records
        except Exception as e:
            logger.warning(f'FinMind insider 取得失敗: {e}')
            return []

    def _fetch_ptt_stock(self, symbol: str, name: str) -> List[Dict]:
        """從 PTT Stock 板 RSS 搜尋"""
        try:
            # PTT web RSS
            url = f'https://www.ptt.cc/bbs/Stock/search?q={quote(symbol)}'
            r = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0',
                'Cookie': 'over18=1',
            }, verify=False)

            if r.status_code != 200:
                return []

            # 簡易 HTML 解析取標題
            posts = []
            # 找所有 <div class="title">...<a href="...">標題</a>...</div>
            pattern = r'<div class="title">\s*<a[^>]*>([^<]+)</a>'
            matches = re.findall(pattern, r.text)

            for title in matches:
                title = title.strip()
                if symbol in title or (name and name in title):
                    posts.append({'title': title, 'date': ''})

            return posts
        except Exception as e:
            logger.warning(f'PTT 抓取失敗: {e}')
            return []

    # ──────────────────────────────────────────────
    #  情緒計算
    # ──────────────────────────────────────────────
    def _score_text(self, text: str) -> float:
        """用詞典計算文本情緒分數（-100 到 +100）"""
        pos_count = sum(1 for w in POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text)

        total = pos_count + neg_count
        if total == 0:
            return 0

        return ((pos_count - neg_count) / total) * 100

    def _score_to_label(self, score: Optional[float]) -> str:
        if score is None:
            return '無資料'
        if score > 30:
            return '強烈看多'
        if score > 10:
            return '偏多'
        if score > -10:
            return '中性'
        if score > -30:
            return '偏空'
        return '強烈看空'

    def _get_stock_name(self, symbol: str) -> str:
        for col in ['taiwan_stock_info', 'stock_list']:
            try:
                rec = self.db[col].find_one({'stock_id': symbol}, {'stock_name': 1, 'name': 1})
                if rec:
                    return rec.get('stock_name', rec.get('name', ''))
            except Exception:
                pass
        rec = self.db.stock_price.find_one({'symbol': symbol}, {'name': 1})
        return rec.get('name', '') if rec else ''


# ──────────────────────────────────────────────
#  CLI 測試
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    sa = SentimentAnalyzer()

    for sym in ['2330', '2603']:
        print(f"\n{'='*60}")
        r = sa.analyze(sym)
        print(f"  {sym} {r['name']} — 情緒分析")
        print(f"{'='*60}")

        # 新聞
        ns = r['news_sentiment']
        if ns.get('score') is not None:
            print(f"\n  📰 新聞情緒: {ns['label']} ({ns['score']:+.1f})")
            print(f"     正面:{ns['positive']} 負面:{ns['negative']} 中性:{ns['neutral']}")
            for a in ns.get('articles', [])[:3]:
                s = '🟢' if a['score'] > 0 else ('🔴' if a['score'] < 0 else '⚪')
                print(f"     {s} {a['title'][:50]}")
        else:
            print(f"\n  📰 新聞: {ns.get('reason', 'N/A')}")

        # 內部人
        ins = r['insider_trading']
        if ins.get('score') is not None:
            print(f"\n  👔 內部人: {ins['label']} ({ins['score']:+.1f})")
            print(f"     買入:{ins['buy_count']} 賣出:{ins['sell_count']} 淨變動:{ins['net_shares']:,}股")
        else:
            print(f"\n  👔 內部人: {ins.get('reason', 'N/A')}")

        # PTT
        ptt = r['ptt_sentiment']
        if ptt.get('score') is not None:
            print(f"\n  💬 PTT: {ptt['label']} ({ptt['score']:+.1f})")
            print(f"     看多:{ptt['bullish']} 看空:{ptt['bearish']}")
        else:
            print(f"\n  💬 PTT: {ptt.get('reason', 'N/A')}")

        # 綜合
        comp = r['composite']
        print(f"\n  🎯 綜合情緒: {comp['label']}"
              + (f" ({comp['score']:+.1f})" if comp['score'] is not None else ''))
