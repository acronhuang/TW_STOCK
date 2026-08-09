#!/usr/bin/env bash
# 偵測線上 crontab 與版控快照 deploy/crontab.txt 的漂移 (G3)。
# 背景：deploy/crontab.txt 是匯出快照，但排程常被手改卻沒回寫版控，
#       導致「.166 全毀時照快照重建會少排程」。此腳本讓漂移能被抓到。
# 用法：bash scripts/check_crontab_drift.sh   (可接每日 cron 或 deploy 前置檢查)
# 結束碼：0=一致  1=有漂移  2=快照不存在
set -euo pipefail
cd "$(dirname "$0")/.."
SNAP="deploy/crontab.txt"
[ -f "$SNAP" ] || { echo "[DRIFT-CHECK] 找不到快照 $SNAP"; exit 2; }

# 只比對有效行（去掉註解與空行），排序後比對（不在意排列順序）
tmp_live="$(mktemp)"; tmp_snap="$(mktemp)"
trap 'rm -f "$tmp_live" "$tmp_snap"' EXIT
crontab -l 2>/dev/null | grep -vE '^[[:space:]]*#|^[[:space:]]*$' | sort > "$tmp_live"
grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$SNAP" | sort > "$tmp_snap"

if diff "$tmp_live" "$tmp_snap" >/dev/null; then
  echo "[DRIFT-CHECK] OK：crontab 與版控快照一致（$(wc -l < "$tmp_live") 條有效排程）"
  exit 0
fi

echo "[DRIFT-CHECK] WARN：偵測到漂移（< 線上獨有 / > 快照獨有）"
diff "$tmp_live" "$tmp_snap" || true
echo ""
echo "[修復] 若以線上為準： crontab -l > $SNAP && git add $SNAP && git commit -m 'chore(deploy): 同步 crontab'"
exit 1
