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

# ── 防重疊 ──────────────────────────────────────────────────────────
# 2026-08-15 實測：8/07 那輪週跑已執行 7 天仍未完成，8/14 這輪又疊上去，
# 四個團隊分析同時搶 .27/.28 的 GPU，吞吐掉到約 10 檔/小時（單輪預期 ~14 小時）。
# 此腳本原本沒有任何防重疊機制，每週五都會再疊一輪，越積越慢。
#
# 兩道檢查：flock 保證之後每一輪都 race-free；pgrep 補抓「加鎖前就已啟動、
# 因此不持有鎖」的舊進程。舊進程全部結束後 pgrep 那道自然不再觸發，可安全長留。
LOCK=logs/.weekly_team_full.lock
exec 200>>"$LOCK" || exit 1          # 用 >> 不用 >：> 會在 flock 失敗前先截斷檔案
if ! flock -n 200; then
  echo "⏭ 已有另一輪週跑持有鎖，本次跳過 $(date '+%F %T')"
  echo "   這是刻意跳過，不是失敗（exit 75）。"
  exit 75
fi

OLD=$(pgrep -f 'team_daily_verified\.py --universe all' | tr '\n' ' ')
if [ -n "${OLD// /}" ]; then
  echo "⏭ 偵測到既有的全市場團隊分析仍在執行 (PID: ${OLD})，本次跳過 $(date '+%F %T')"
  echo "   這是刻意跳過，不是失敗（exit 75）。確認舊進程確實無用後再人工重跑。"
  exit 75
fi

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
