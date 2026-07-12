#!/usr/bin/env python3
"""
每週 OpenClaw 7 人團隊深度驗證（重要決策）
=============================================
每週六早上 08:00 執行：
 1. 讀取最近一次 daily_recommendations 的 Tier 1/2 推薦
 2. 用 OpenClaw 7 人團隊逐一深度分析
 3. 產出最終投資決策報告
 4. 發 LINE

適合用於：
 - 週末整理下週投資決策
 - 多視角交叉驗證 Claude 的建議
"""
from __future__ import annotations
import sys
import json
import warnings
import subprocess
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')


def latest_picks() -> dict | None:
    picks_dir = ROOT / 'results' / 'daily_picks'
    if not picks_dir.exists():
        return None
    files = sorted(picks_dir.glob('picks_*.json'), reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        return json.load(f)


def main():
    picks = latest_picks()
    if not picks:
        print("⚠️ 無可用推薦，先跑 daily_recommendations.py")
        return

    # 只對 Tier 1 + Tier 2 做團隊驗證（重要決策）
    high_priority = picks.get('tier1', []) + picks.get('tier2', [])
    if not high_priority:
        print("ℹ️ 無強烈推薦/推薦標的，跳過團隊驗證")
        try:
            from src.alerts.line_notifier import LineNotifier
            LineNotifier().send(f"📋 每週深度驗證 ({datetime.now().strftime('%Y-%m-%d')})\n\n本週無高優先標的需驗證")
        except Exception:
            pass
        return

    print(f"📊 團隊深度驗證 {len(high_priority)} 支")
    for c in high_priority:
        print(f"  - {c['sym']} {c['name']}")

    symbols = [c['sym'] for c in high_priority]
    # 呼叫 team_analyze.py（順序執行）
    cmd = [sys.executable, str(ROOT / 'scripts' / 'team_analyze.py')] + symbols + ['--line']
    print(f"\n執行：{' '.join(cmd)}")
    subprocess.run(cmd)


if __name__ == '__main__':
    main()
