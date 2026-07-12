#!/usr/bin/env python3
"""
7 人團隊一鍵完整分析

流程：
  1. 對每支股票預抓所有 API 數據（總經/財報/估值/風險/同業/籌碼/異常）
  2. 7 個專家依序分析（每個專家拿到對應數據 + 角色提示詞）
  3. investment-advisor 整合 6 份報告 → 最終建議
  4. 輸出彙總報告（Console + JSON 存檔，可選發 LINE）

使用：
    python scripts/team_analyze.py 1108
    python scripts/team_analyze.py 1108 2107 2706
    python scripts/team_analyze.py 1108 --line     # 完成後發 LINE
    python scripts/team_analyze.py 1108 --quick    # 跳過 advisor（省時間）
"""

from __future__ import annotations
import sys
import os
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from src.moe.role_router import ask_role, ROLE_TO_MODEL

API = 'http://localhost:8888'


def fetch_all_data(symbol: str) -> dict:
    """一次抓齊所有需要的 API 資料"""
    print(f"  📥 抓取 {symbol} 完整資料...")
    data = {}
    endpoints = {
        'factors':       f'/api/factors/{symbol}',
        'financial':     f'/api/financial/{symbol}',
        'valuation':     f'/api/valuation/{symbol}',
        'risk':          f'/api/risk/{symbol}',
        'peer':          f'/api/peer/{symbol}',
        'institutional': f'/api/institutional/{symbol}?days=10',
        'anomaly':       f'/api/anomaly/{symbol}',
        'revenue':       f'/api/revenue/{symbol}?months=6',
        'macro':         f'/api/macro',
    }
    for key, ep in endpoints.items():
        try:
            r = requests.get(API + ep, timeout=30)
            data[key] = r.json() if r.status_code == 200 else {'error': r.status_code}
        except Exception as e:
            data[key] = {'error': str(e)}
    return data


def build_expert_prompt(role: str, symbol: str, data: dict) -> str:
    """為每個專家準備專屬提示詞 + 數據"""
    if role == 'macro-analyst':
        return f"用台股總經背景判斷對 {symbol} 的影響：\n{json.dumps(data['macro'], ensure_ascii=False)}\n\n用 5 行內回答：大盤是否適合佈局？對 {symbol} 利或不利？"

    if role == 'fundamental-analyst':
        f = data['financial']
        return f"分析 {symbol} 財報健康狀況：\n{json.dumps({k:v for k,v in f.items() if k!='ttm' or True}, ensure_ascii=False)}\n\n用 5 行內回答：財報健康嗎？關鍵警示？"

    if role == 'value-analyst':
        v = data['valuation']
        return f"判斷 {symbol} 估值：\n{json.dumps(v, ensure_ascii=False)}\n\n用 3 行回答：低估還是高估？合理價多少？"

    if role == 'technical-analyst':
        return f"分析 {symbol} 技術面：\n因子: {json.dumps(data['factors'], ensure_ascii=False)}\n異常: {json.dumps(data['anomaly'], ensure_ascii=False)}\n\n用 5 行內回答：趨勢方向？進出場訊號？"

    if role == 'chip-analyst':
        return f"分析 {symbol} 籌碼：\n近10日法人: {json.dumps(data['institutional'], ensure_ascii=False)}\n\n用 3 行內回答：法人在買還是賣？主力意圖？"

    if role == 'risk-manager':
        return f"評估 {symbol} 風險：\n{json.dumps(data['risk'], ensure_ascii=False)}\n\n用 5 行內回答：風險等級？10萬資金建議部位/張數/停損？"

    if role == 'investment-advisor':
        # 把前 6 個專家的報告當輸入
        return f"""你是投資顧問，整合以下 6 份報告，給 {symbol} 最終建議：

【總經】{data.get('reports', {}).get('macro-analyst', '無')}

【基本面】{data.get('reports', {}).get('fundamental-analyst', '無')}

【估值】{data.get('reports', {}).get('value-analyst', '無')}

【技術】{data.get('reports', {}).get('technical-analyst', '無')}

【籌碼】{data.get('reports', {}).get('chip-analyst', '無')}

【風險】{data.get('reports', {}).get('risk-manager', '無')}

⚠️ 輸出規則（務必遵守）：
第一行只輸出評級標籤，固定格式：`評級：<X>`，X 五選一【強力買進 / 買進 / 觀望 / 減碼 / 賣出】，不得加註其他字。
第二行起才寫理由與具體操作（張數/進場價/停損價/目標價/持有期）。
評級需呼應蔡森技術型態方向（一致性要求）：
  • 偏空型態(M-Top/HS-Top/Triple-Top/Failed-Breakout)且無強力利多催化 → 不給買進/強力買進。
  • 偏多型態(W-Bottom/HS-Bottom/Triple-Bottom/Failed-Breakdown)且無強烈利空 → 不給賣出/減碼。
  • 若你的評級與型態方向相反(例如型態偏多卻給賣出)，**必須在理由首句明確說明壓過技術面的關鍵因素**
    (如基本面急轉直下、估值極端、籌碼大量出貨)；否則請改回與型態方向一致的評級。"""

    return f"分析 {symbol}"


def analyze_one(symbol: str, quick: bool = False) -> dict:
    """完整分析單一股票"""
    print(f"\n{'═'*70}")
    print(f"  🏛️  7 人團隊分析：{symbol}")
    print(f"{'═'*70}")
    t_start = time.time()

    # Step 1: 抓資料
    data = fetch_all_data(symbol)
    name = data['factors'].get('symbol', symbol)
    price = data['factors'].get('close') or data['valuation'].get('current_price')

    # Step 2: 6 個專家依序分析
    expert_order = [
        'macro-analyst',
        'fundamental-analyst',
        'value-analyst',
        'technical-analyst',
        'chip-analyst',
        'risk-manager',
    ]
    reports = {}
    for role in expert_order:
        print(f"\n  🤖 {role} ({ROLE_TO_MODEL[role]})")
        prompt = build_expert_prompt(role, symbol, data)
        r = ask_role(role, prompt, include_role_prompt=True, timeout=180)
        if 'error' in r:
            print(f"     ❌ {r['error']}")
            reports[role] = f"分析失敗: {r['error']}"
        else:
            text = r['response'].strip()
            # 去掉 <think>...</think>
            if '<think>' in text:
                text = text.split('</think>', 1)[-1].strip()
            reports[role] = text
            preview = text[:120].replace('\n', ' ')
            print(f"     ⏱  {r['elapsed_sec']}s  💬 {preview}...")

    # Step 3: investment-advisor 整合
    if not quick:
        print(f"\n  🎩 investment-advisor ({ROLE_TO_MODEL['investment-advisor']})  整合中...")
        data['reports'] = reports
        prompt = build_expert_prompt('investment-advisor', symbol, data)
        r = ask_role('investment-advisor', prompt, include_role_prompt=True, timeout=300)
        if 'error' in r:
            final = f"整合失敗: {r['error']}"
        else:
            final = r['response'].strip()
            if '<think>' in final:
                final = final.split('</think>', 1)[-1].strip()
            print(f"     ⏱  {r['elapsed_sec']}s")
    else:
        final = '(--quick 模式跳過 advisor)'

    elapsed_total = time.time() - t_start

    return {
        'symbol': symbol,
        'price': price,
        'reports': reports,
        'final_advice': final,
        'total_seconds': round(elapsed_total, 1),
        'analyzed_at': datetime.now().isoformat(),
    }


def print_report(result: dict):
    """漂亮印出分析結果"""
    print(f"\n{'═'*70}")
    print(f"  📊 {result['symbol']}  最終分析報告  (總耗時 {result['total_seconds']}s)")
    print(f"{'═'*70}")

    titles = {
        'macro-analyst':       '🎯 總經分析',
        'fundamental-analyst': '💰 基本面',
        'value-analyst':       '💎 估值',
        'technical-analyst':   '📈 技術面',
        'chip-analyst':        '🏦 籌碼',
        'risk-manager':        '🛡️ 風險',
    }
    for role, title in titles.items():
        report = result['reports'].get(role, '')
        print(f"\n  ── {title} ──")
        print(f"  {report[:500]}")

    print(f"\n{'═'*70}")
    print(f"  🎩 投資顧問最終建議")
    print(f"{'═'*70}")
    print(f"  {result['final_advice']}")
    print(f"{'═'*70}\n")


def save_report(results: list, output_dir: str = None):
    output_dir = output_dir or str(ROOT / 'results' / 'team_analysis')
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = f"{output_dir}/team_{ts}.json"
    with open(path, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  💾 報告已存至: {path}")
    return path


def send_line(results: list):
    from src.alerts.line_notifier import LineNotifier
    ln = LineNotifier()
    msg = "🏛️ 7人團隊分析報告\n\n"
    for r in results:
        advice = r['final_advice'][:300] if r['final_advice'] else '(無)'
        msg += f"📊 {r['symbol']} ({r['price']})\n{advice}\n\n"
    ln.send(msg[:4500])
    print(f"  ✅ LINE 已發送")


def main():
    parser = argparse.ArgumentParser(description='7 人團隊股票一鍵分析')
    parser.add_argument('symbols', nargs='+', help='股票代號（可多個）')
    parser.add_argument('--quick', action='store_true', help='跳過 advisor 整合（省時間）')
    parser.add_argument('--line', action='store_true', help='完成後發 LINE')
    parser.add_argument('--no-save', action='store_true', help='不存檔')
    args = parser.parse_args()

    results = []
    for sym in args.symbols:
        r = analyze_one(sym, quick=args.quick)
        print_report(r)
        results.append(r)

    if not args.no_save:
        save_report(results)

    if args.line:
        send_line(results)


if __name__ == '__main__':
    main()
