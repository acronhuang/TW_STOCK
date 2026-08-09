#!/usr/bin/env bash
# 重啟 Streamlit 儀表板：PID 精準殺（非 pkill，避免自我匹配殺到自己）+ setsid 重拉
# （脫離當前 session，避免 SSH 斷線帶走行程 / 卡住）。
# 背景：dashboard 目前非 systemd 常駐（twstock-dashboard.service inactive），改碼後須重啟才生效
#       （Streamlit 長駐會快取舊模組）。
# 綁定位址：預設沿用現況 0.0.0.0；ADR-010 建議改 127.0.0.1 + 反代認證——
#          此處不預設改，避免鎖死你目前的存取方式（要改：DASH_ADDR=127.0.0.1 bash ...）。
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="${DASH_PORT:-8501}"
ADDR="${DASH_ADDR:-0.0.0.0}"
VENV="${VENV:-/home/mdsadmin/Stock/.venv}"
LOG="logs/dashboard.log"
PAT="streamlit run dashboard/app.py"

mkdir -p logs

# 1) 精準找 PID（pgrep -f 針對完整指令列，不會匹配到本腳本）
pids="$(pgrep -f "$PAT" || true)"
if [ -n "$pids" ]; then
  echo "[dashboard] 停止既有行程 PID: $pids"
  kill $pids 2>/dev/null || true
  sleep 2
  pids2="$(pgrep -f "$PAT" || true)"
  if [ -n "$pids2" ]; then
    echo "[dashboard] 仍在，強制結束 $pids2"
    kill -9 $pids2 2>/dev/null || true
    sleep 1
  fi
else
  echo "[dashboard] 無既有行程"
fi

# 2) setsid 重拉（< /dev/null 防卡；stdout/err 進 log）
echo "[dashboard] 啟動 :$PORT ($ADDR)"
setsid "$VENV/bin/streamlit" run dashboard/app.py \
  --server.port "$PORT" --server.address "$ADDR" \
  --server.headless true --browser.gatherUsageStats false \
  > "$LOG" 2>&1 < /dev/null &

# 3) 驗證：最多等 20 秒確認在監聽
for _ in $(seq 1 20); do
  sleep 1
  if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
    echo "[dashboard] OK：已監聽 :$PORT（log: $LOG）"
    exit 0
  fi
done
echo "[dashboard] WARN：20s 內未見 :$PORT 監聽，末 15 行 log："
tail -n 15 "$LOG" 2>/dev/null || true
exit 1
