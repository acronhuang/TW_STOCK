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

echo "============================================================"
echo "  Phase 1 精簡（6角色+佐證）  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
"$PY" scripts/team_daily_verified.py --universe industry50 --quick

echo "============================================================"
echo "  Phase 2 完整（補顧問整合）  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
"$PY" scripts/team_daily_verified.py --universe industry50 --phase2

echo "完成：$(date '+%Y-%m-%d %H:%M:%S')"
