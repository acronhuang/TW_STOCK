#!/usr/bin/env bash
# 單人版 CD（P8a G1）：拉碼 → 測試綠燈才部署 → smoke → 重啟 API+儀表板 → health 檢查。
# 用法：bash scripts/deploy.sh
# 原則：測試未過即中止,不重啟(不把未過測試的碼推上線)。會重啟生產服務,勿盤中隨意跑。
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-/home/mdsadmin/Stock/.venv/bin/python3}"

echo "== [1/6] git pull --ff-only =="
git pull --ff-only

echo "== [2/6] crontab 漂移檢查（警示,不擋）=="
bash scripts/check_crontab_drift.sh || echo "  ⚠️ crontab 與版控快照不一致(見上);如以線上為準記得回寫 deploy/crontab.txt"

echo "== [3/6] 測試綠燈閘（未過→set -e 中止,不部署）=="
"$PY" -m pytest tests/ -m "not slow" -k "not api" -q

echo "== [4/6] 資料契約 + 新鮮度 smoke 硬閘（有 🔴 即中止;transient 🔴 重試1次,G5）=="
smoke() {  # $1=腳本 $2=名稱;失敗重試1次(避免 latest-batch 在批次寫入瞬間閃現 🔴 而誤擋)
  "$PY" "$1" --strict && return 0
  echo "  ⚠️ $2 首次未過,5s 後重試(可能為批次寫入瞬間)..."; sleep 5
  "$PY" "$1" --strict
}
smoke scripts/schema_contract_audit.py 契約稽核 || { echo "  🔴 契約稽核兩次未過,中止部署"; exit 1; }
smoke scripts/data_freshness_audit.py 新鮮度稽核 || { echo "  🔴 新鮮度稽核兩次未過,中止部署"; exit 1; }

echo "== [5/6] 重啟服務 =="
# API：kill -9 讓 systemd(Restart=on-failure,RestartSec=5) 自動重生。
#      注意須用 -9(SIGKILL);SIGTERM 可能被 uvicorn 乾淨處理→exit 0→on-failure 不重生。
#      (實測 mdsadmin 無免密 sudo,故不用 systemctl restart。)
api_pid="$(pgrep -f 'src/api/server.py' || true)"
if [ -n "$api_pid" ]; then
  echo "  API: kill -9 $api_pid → systemd 5s 內自動重生"
  kill -9 $api_pid 2>/dev/null || true
else
  echo "  API: 無執行中行程(systemd 會拉起)"
fi
# 儀表板：專用重啟腳本(PID 精準殺 + setsid)
bash scripts/restart_dashboard.sh

echo "== [6/6] API health 檢查 =="
ok=0
for _ in $(seq 1 12); do
  sleep 2
  if curl -sf http://localhost:8888/api/health >/dev/null 2>&1; then echo "  API health OK"; ok=1; break; fi
done
if [ "$ok" != 1 ]; then
  echo "  ⚠️ API health 未通過,請查 systemctl status twstock-api"
  exit 1
fi
# G7 可追溯:記錄本次部署的版本/commit(DEPLOYED.txt 不入版控,每台各自狀態)
{ echo "deployed_at=$(date '+%F %T')"; echo "version=$(git describe --tags --always 2>/dev/null)"; echo "commit=$(git rev-parse --short HEAD)"; } > deploy/DEPLOYED.txt
echo "  版本記錄 -> deploy/DEPLOYED.txt: $(git describe --tags --always 2>/dev/null) ($(git rev-parse --short HEAD))"
echo "== 部署完成 =="
