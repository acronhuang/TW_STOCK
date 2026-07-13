#!/bin/bash
# 每週五晚上：全市場團隊分析 phase1(6角色) + phase2(顧問整合 + .27 合議) 串接。
# 兩階段用 --date 釘在同一天（phase1 啟動日），避免跨午夜/時區的存讀檔錯位。
# 排程：crontab  0 21 * * 5
set -u
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
PY=/home/mdsadmin/Stock/.venv/bin/python3
DATE=$(date +%Y%m%d)
JSON="results/team_analysis/team_${DATE}.json"

echo "════════ 週末全市場團隊分析 開始 $(date '+%F %T %Z') · date=${DATE} ════════"

echo "──── [1/4] phase1：6 角色分析（quick，全市場 ~2000 檔）────"
$PY -u scripts/team_daily_verified.py --universe all --quick --no-line --date "$DATE"
echo "phase1 結束 $(date '+%F %T')"

if [ ! -s "$JSON" ]; then
  echo "✗ 找不到 phase1 存檔 ${JSON}，中止（不跑 phase2）"
  exit 1
fi

echo "──── [2/4] phase2：投資顧問整合 + .27 合議【序列討論】────"
# 強制全市場也走序列討論(覆寫 main() 對 --universe all 的自動盲投 gate)。
# ⚠️ 全市場 ~2000 檔 × ~31s ≈ 14 小時，且期間長時間佔用 .27/.28 共用 Ollama。
CONSENSUS_MODE=discuss $PY -u scripts/team_daily_verified.py --universe all --phase2 --no-line --date "$DATE"
echo "phase2 結束 $(date '+%F %T')"

echo "──── [3/4] 同步 JSON → DB（team_analysis）────"
$PY scripts/migrate_team_to_db.py --apply --date "$DATE"

echo "──── [4/4] 復驗（快層新鮮度 + FinMind 抽查 30）────"
$PY scripts/reverify_team.py --date "$DATE" --finmind 30

echo "════════ 完成 $(date '+%F %T %Z') ════════"
