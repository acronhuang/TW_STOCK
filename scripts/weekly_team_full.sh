#!/bin/bash
# 每週五晚上：全市場團隊分析 phase1(6角色) ‖ phase2(顧問整合 + .27 合議) 流水線。
# 兩階段用 --date 釘在同一天（phase1 啟動日），避免跨午夜/時區的存讀檔錯位。
# 排程：crontab  0 21 * * 5
#
# 2026-08-15 改為流水線（原本是 phase1 全部跑完才開始 phase2）
# ------------------------------------------------------------------
# 實測：phase1 4.8 天 + phase2 4.7 天 = 9.5 天，但排程是 7 天一輪 —— 結構性跑不完，
# 這就是曾疊出四個進程的原因。
#
# 為什麼流水線可行：phase2 本來就是增量的（只挑「缺 advisor」的標的），
# 且已改為從 DB 取待辦（load_pending_from_db），MongoDB 逐文件 upsert，
# 不像原本兩階段共寫一個 JSON 會整檔覆蓋。故 phase2 可邊等邊消化 phase1 的產出。
#
# 為什麼有效（實測 .28 吞吐飽和曲線）：
#   併發 1 → 0.84 req/分            併發 6 → 1.54 (1.84x, +38%)
#   併發 3 → 1.11 (1.33x, +33%)     併發 9 → 1.74 (2.07x, +13%)
# 天花板約 2.07x，在併發 6~9 才趨於飽和 —— 代表 GPU 仍有餘裕，
# 疊上 phase2 不會只是排隊。預估 4.5 天 → 3.3 天。
#
# 但流水線真正的價值不在省 1.2 天，而在：原本 phase1 全部跑完前（第 4.5 天）
# 沒有任何一檔有完整結果（合議定案在 phase2 才產生）；改流水線後第 1 天就開始有。
set -u
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
PY=/home/mdsadmin/Stock/.venv/bin/python3
DATE="${WEEKLY_DATE:-$(date +%Y%m%d)}"
UNIVERSE="${WEEKLY_UNIVERSE:-all}"          # 測試時可設 industry50 等小 universe
POLL_SEC="${WEEKLY_POLL_SEC:-300}"          # phase2 找不到待辦時的輪詢間隔
JSON="results/team_analysis/team_${DATE}.json"

echo "════════ 週末全市場團隊分析 開始 $(date '+%F %T %Z') · date=${DATE} universe=${UNIVERSE} ════════"

# ── 防重疊 ──────────────────────────────────────────────────────────
# 2026-08-15 實測：8/07 那輪週跑已執行 7 天仍未完成，8/14 這輪又疊上去，
# 四個團隊分析同時搶 .27/.28 的 GPU，吞吐掉到約 10 檔/小時。
# 此腳本原本沒有任何防重疊機制，每週五都會再疊一輪，越積越慢。
#
# 兩道檢查：flock 保證之後每一輪都 race-free；pgrep 補抓「加鎖前就已啟動、
# 因此不持有鎖」的舊進程。舊進程全部結束後 pgrep 那道自然不再觸發，可安全長留。
# WEEKLY_SKIP_GUARD=1 僅供測試（小 universe 驗流水線）時繞過，正式排程絕不要設。
if [ "${WEEKLY_SKIP_GUARD:-0}" != "1" ]; then
  LOCK=logs/.weekly_team_full.lock
  exec 200>>"$LOCK" || exit 1        # 用 >> 不用 >：> 會在 flock 失敗前先截斷檔案
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
fi

# ── [1/4] phase1 背景啟動 ───────────────────────────────────────────
echo "──── [1/4] phase1：6 角色分析（quick，universe=${UNIVERSE}）背景啟動 ────"
$PY -u scripts/team_daily_verified.py --universe "$UNIVERSE" --quick --no-line --date "$DATE" &
P1=$!
echo "phase1 PID=${P1} 啟動 $(date '+%F %T')"

# ── [2/4] phase2 輪詢消化，與 phase1 併行 ───────────────────────────
# 從 DB 取待辦（不讀寫 JSON）→ 不會與 phase1 的 save_results 互相覆蓋。
# phase1 還活著就持續輪詢；phase1 結束後再跑最後一輪把剩餘的排乾。
echo "──── [2/4] phase2：顧問整合 + .27 合議【序列討論】與 phase1 併行 ────"
ROUND=0
while kill -0 "$P1" 2>/dev/null; do
  ROUND=$((ROUND + 1))
  echo "── phase2 第 ${ROUND} 輪 $(date '+%F %T')（phase1 仍在跑）──"
  CONSENSUS_MODE=discuss $PY -u scripts/team_daily_verified.py \
      --phase2 --no-line --date "$DATE"
  # 消化完就等一下再查，避免 phase1 還沒產出時空轉洗版
  kill -0 "$P1" 2>/dev/null && sleep "$POLL_SEC"
done
wait "$P1" 2>/dev/null
P1RC=$?
echo "phase1 結束 $(date '+%F %T') (rc=${P1RC})"

echo "── phase2 收尾輪（phase1 已結束，排乾剩餘）──"
CONSENSUS_MODE=discuss $PY -u scripts/team_daily_verified.py \
    --phase2 --no-line --date "$DATE"
echo "phase2 結束 $(date '+%F %T')"

if [ ! -s "$JSON" ]; then
  echo "⚠️ 找不到 phase1 存檔 ${JSON}（DB 應已有資料，僅影響 JSON→DB 補同步）"
fi

echo "──── [3/4] 同步 JSON → DB（team_analysis）────"
$PY scripts/migrate_team_to_db.py --apply --date "$DATE"

echo "──── [4/4] 復驗（快層新鮮度 + FinMind 抽查 30）────"
$PY scripts/reverify_team.py --date "$DATE" --finmind 30

echo "════════ 完成 $(date '+%F %T %Z') ════════"
