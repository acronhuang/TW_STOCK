#!/bin/bash
# =============================================================================
# 每日 50 檔（各行業龍頭 + 成交額補滿）團隊分析 — 兩階段
#   Phase 1 精簡：6 角色 + 資料佐證（省顧問整合，~2 小時）→ LINE 摘要
#   Phase 2 完整：重用 Phase1 的 6 角色報告，只補跑投資顧問整合 → LINE 摘要
# 串接執行(&& )：Phase2 只在 Phase1 完成後才跑，避免兩排程搶寫同檔。
# 由 com.twstock.daily_team_verified 於每日 18:30 觸發。
# =============================================================================
set -uo pipefail
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
PY=/home/mdsadmin/Stock/.venv/bin/python3

# ── 讓路給週跑（單向）────────────────────────────────────────────────
# 週跑 --universe all 已涵蓋 industry50，重疊只是重複計算又互搶同一顆 GPU。
# 2026-08-19 實測：週跑(phase1+phase2) + 本工作並存 → .28 佇列爆滿回
# 503 server busy，risk-manager 200 檔逾時 61 檔，且錯誤字串被合議採用。
# 單向：只有每日讓週跑，不可反向 —— 每日管線 20:00 起跑數小時，若週跑也讓路，
# 週五 21:00 的週跑會被自己的守衛永久擋掉。
if pgrep -f 'team_daily_verified\.py --universe all' >/dev/null; then
  echo "⏭ 週跑進行中，跳過每日 industry50 團隊分析（--universe all 已涵蓋）"
  echo "   這是刻意跳過，不是失敗（exit 75）。"
  exit 75
fi

echo "============================================================"
echo "  Phase 1 精簡（6角色+佐證）  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
"$PY" scripts/team_daily_verified.py --universe industry50 --quick

echo "============================================================"
echo "  Phase 2 完整（補顧問整合）  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
"$PY" scripts/team_daily_verified.py --universe industry50 --phase2

echo "完成：$(date '+%Y-%m-%d %H:%M:%S')"
