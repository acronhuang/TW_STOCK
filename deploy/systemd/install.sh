#!/usr/bin/env bash
# 安裝 tw-stock systemd user timers（Persistent 補跑)。在 .166 以 mdsadmin 執行。
#   cd /home/mdsadmin/Stock/tw-stock-analysis && bash deploy/systemd/install.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"
cp "$SRC"/tw-*.service "$SRC"/tw-*.timer "$DEST/"
loginctl enable-linger "$USER"            # 無登入也能跑（headless server）
systemctl --user daemon-reload
for t in "$SRC"/tw-*.timer; do
  systemctl --user enable --now "$(basename "$t")"
done
echo "=== 已啟用 timers（NEXT=下次觸發）==="
systemctl --user list-timers --all | grep -E "NEXT|tw-"
