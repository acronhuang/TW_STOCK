#!/bin/bash
# 機外停機偵測心跳（dead-man's switch）。
# 讀 .env 的 HEARTBEAT_URL（如 Healthchecks.io: https://hc-ping.com/<uuid>），定時 ping。
# 外部服務在心跳「停止」時主動通知 —— 這能偵測本機整機關機/斷網（機內告警做不到的盲區，
# 例：2026-09 停機 4 天無人察覺）。
# 未設 HEARTBEAT_URL 則 no-op：可先部署，之後在 .env 貼上 URL 即生效，不入版控。
set -uo pipefail
cd "$(dirname "$0")/.."
URL="$(grep -E '^HEARTBEAT_URL=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)"
[ -z "${URL:-}" ] && exit 0
if curl -fsS -m 10 --retry 2 "$URL" >/dev/null 2>&1; then
  echo "[heartbeat] ok   $(date '+%F %T')"
else
  echo "[heartbeat] FAIL $(date '+%F %T')  (本機對外網路異常或 URL 失效)"
fi
