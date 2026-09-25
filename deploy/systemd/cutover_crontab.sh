#!/usr/bin/env bash
# 切換:把「已遷 systemd」的排程行從 user crontab 註解掉（可逆),避免與 timer 雙跑。
# 先備份 crontab；只註解結尾 `# <name>` 屬於遷移清單者。安裝 timer 後執行。
#   bash deploy/systemd/cutover_crontab.sh          # 實際切換
#   bash deploy/systemd/cutover_crontab.sh --revert # 還原（移除本腳本加的註解前綴）
set -euo pipefail
TAG="#[migrated→systemd] "
NAMES="weekly_outstanding_shares weekly_team_verify weekly_team_full \
data_health_weekly_finmind verify_backup_weekly tdcc_shareholding weekly_media_news \
history_continuity evening_data_check weekly_corp_actions foreign_shareholding_weekly \
weekly_rag_ingest requirement_weekly_summary macro_signal_reminder monthly_revenue_sync \
quarterly_earnings_sync monthly_verdict_sli"

bak="$HOME/crontab.bak.$(date +%Y%m%d_%H%M%S)"
crontab -l > "$bak"; echo "已備份 crontab → $bak"
cur="$(cat "$bak")"

if [[ "${1:-}" == "--revert" ]]; then
  cur="$(printf '%s\n' "$cur" | sed "s|^${TAG}||")"
  printf '%s\n' "$cur" | crontab -
  echo "已還原（移除遷移註解前綴）"; exit 0
fi

for n in $NAMES; do
  # 只註解「未註解且結尾為 # <name>」的行
  cur="$(printf '%s\n' "$cur" | sed -E "s|^([^#].*#[[:space:]]*${n})[[:space:]]*$|${TAG}\1|")"
done
printf '%s\n' "$cur" | crontab -
echo "=== 切換後仍在 cron（未被註解）的遷移任務（應為空）==="
crontab -l | grep -vE '^\s*#' | grep -Ew "$(echo $NAMES | tr ' ' '|')" || echo "  （無，已全部切走）"
