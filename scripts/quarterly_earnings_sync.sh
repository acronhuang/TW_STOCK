#!/bin/bash
# 季報自動更新 - 透過 FinMind API 同步最新季報
# 排程：每季公告截止日後執行（4/1, 5/16, 8/15, 11/15）
# 策略：只更新最近1年，--resume 跳過已有資料

cd /home/mdsadmin/Stock/tw-stock-analysis

# 從 .env 讀取 token
source .env
TOKEN="${FINMIND_API_TOKEN}"

echo "=========================================="
echo "季報自動更新 $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 用 --years 1 只抓最近1年，--resume 跳過已有
# --delay 12 = 每股12秒（2 API calls），600/hr 配額約跑300支
/home/mdsadmin/Stock/.venv/bin/python3 \
    /home/mdsadmin/Stock/tw-stock-analysis/scripts/finmind_quarterly_backfill.py \
    --token "$TOKEN" \
    --years 1 \
    --resume \
    --delay 12

echo ""
echo "── 資產負債表 + ROE（免費官方 OpenAPI，補 quarterly_earnings.balance）──"
/home/mdsadmin/Stock/.venv/bin/python3 \
    /home/mdsadmin/Stock/tw-stock-analysis/scripts/sync_balance_openapi.py

echo ""
echo "季報更新完成 $(date '+%Y-%m-%d %H:%M:%S')"
