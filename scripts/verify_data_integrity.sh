#!/bin/bash
#
# 資料完整性一鍵驗證（2026-10-01 新增）
# 依序跑三層檢查並彙整結論：
#   1) data_freshness_audit.py   資料新鮮度盤點（cadence-aware，有 🔴 落後回非零）
#   2) check_data_completeness.py 完整度檢查（純資訊性，永遠 exit 0）
#   3) prod_data_health_report.py prod_data 真實庫驗證（pytest marker；注意它即使 fail 也 exit 0，
#                                 本腳本改用 stdout 的 🔴 判定成敗）
#
# 用法：
#   bash scripts/verify_data_integrity.sh                 # 全跑，不寫 DB 告警
#   bash scripts/verify_data_integrity.sh --alert         # 有異常時寫 schedule_alerts（網頁🔔可查）
#   bash scripts/verify_data_integrity.sh --quick         # 略過第 3 層（較慢的 pytest）
#   bash scripts/verify_data_integrity.sh --uri mongodb://host:27017
#
# 環境變數：
#   VERIFY_PYTHON   指定 python 直譯器（預設找 repo .venv → 正式機 venv → PATH python3）
#
# 結束碼：全綠=0；任一層偵測到問題=1；無法連 DB 等執行錯誤=2
#
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || { echo "無法進入專案目錄: $PROJECT_DIR" >&2; exit 2; }

# --- 解析參數 ---
ALERT=0
QUICK=0
URI="mongodb://localhost:27017"
while [ $# -gt 0 ]; do
    case "$1" in
        --alert) ALERT=1; shift ;;
        --quick) QUICK=1; shift ;;
        --uri)   URI="$2"; shift 2 ;;
        --uri=*) URI="${1#--uri=}"; shift ;;
        -h|--help)
            sed -n '2,24p' "$0"; exit 0 ;;
        *) echo "未知參數: $1" >&2; exit 2 ;;
    esac
done

# --- 選 python 直譯器 ---
PYTHON="${VERIFY_PYTHON:-}"
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    for cand in "$PROJECT_DIR/.venv/bin/python3" "/home/mdsadmin/Stock/.venv/bin/python3"; do
        [ -x "$cand" ] && PYTHON="$cand" && break
    done
fi
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)"
if [ -z "$PYTHON" ]; then
    echo "找不到可用的 python 直譯器" >&2; exit 2
fi

# --- 輸出目錄 ---
TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$PROJECT_DIR/logs/integrity_checks"
mkdir -p "$OUT_DIR"
REPORT="$OUT_DIR/integrity_${TS}.log"

# 顏色（終端機才上色）
if [ -t 1 ]; then C_R='\033[31m'; C_G='\033[32m'; C_Y='\033[33m'; C_B='\033[1m'; C_0='\033[0m'
else C_R=''; C_G=''; C_Y=''; C_B=''; C_0=''; fi

banner() { printf "\n${C_B}======== %s ========${C_0}\n" "$1" | tee -a "$REPORT"; }
say()    { printf "%b\n" "$1" | tee -a "$REPORT"; }

# --- 先檢查 DB 是否可連（三層都要 DB，連不上就別白跑）---
banner "前置：MongoDB 連線檢查（$URI）"
if ! "$PYTHON" - "$URI" <<'PY' 2>>"$REPORT"
import sys
from pymongo import MongoClient
try:
    MongoClient(sys.argv[1], serverSelectionTimeoutMS=4000).admin.command("ping")
    print("MongoDB 可連線")
except Exception as e:
    print(f"MongoDB 不可連線: {type(e).__name__}: {e}")
    sys.exit(1)
PY
then
    say "${C_R}✗ 無法連線 MongoDB，略過所有檢查。${C_0}"
    say "  這通常代表你在部署 bundle（非正式機）上執行，或 DB 未啟動 / URI 不對。"
    say "  請在正式機（DB 所在）重跑，或用 --uri 指向正式 DB。"
    exit 2
fi
say "${C_G}✓ DB 連線正常${C_0}"

# 收集各層結論
declare -a RESULTS
OVERALL=0   # 0 綠 / 1 有問題

# forward --alert 給支援的腳本
FRESH_ALERT=(); PROD_ALERT=()
[ "$ALERT" -eq 1 ] && FRESH_ALERT=(--alert) && PROD_ALERT=(--alert)

# ===== 1) 新鮮度盤點 =====
banner "1/3 資料新鮮度盤點 data_freshness_audit.py"
# --strict：有 🔴 落後回非零；用它當這層的成敗判定
"$PYTHON" scripts/data_freshness_audit.py --uri "$URI" --strict "${FRESH_ALERT[@]}" 2>&1 | tee -a "$REPORT"
FRESH_RC=${PIPESTATUS[0]}
if [ "$FRESH_RC" -eq 0 ]; then
    RESULTS+=("新鮮度：✅ 無表超出更新頻率門檻")
else
    RESULTS+=("新鮮度：🔴 有表超出門檻（見上方『真正超出』清單）")
    OVERALL=1
fi

# ===== 2) 完整度檢查 =====
banner "2/3 完整度檢查 check_data_completeness.py（純資訊性）"
if "$PYTHON" scripts/check_data_completeness.py 2>&1 | tee -a "$REPORT"; then
    RESULTS+=("完整度：ℹ️  已產出報告（資訊性，請人工檢視上方數字）")
else
    RESULTS+=("完整度：⚠️  腳本執行出錯（見上方）")
    OVERALL=1
fi

# ===== 3) prod_data 真實庫驗證 =====
if [ "$QUICK" -eq 1 ]; then
    RESULTS+=("真實庫驗證：⏭️  已略過（--quick）")
else
    banner "3/3 prod_data 真實庫驗證 prod_data_health_report.py"
    PROD_OUT="$OUT_DIR/prod_data_${TS}.out"
    # 注意：此腳本即使測試 fail 也回 0，故以 stdout 的 🔴 判定
    "$PYTHON" scripts/prod_data_health_report.py "${PROD_ALERT[@]}" 2>&1 | tee -a "$REPORT" | tee "$PROD_OUT"
    if grep -q "🔴" "$PROD_OUT"; then
        PROD_LINE=$(grep -m1 "prod_data 驗證" "$PROD_OUT" || echo "prod_data 驗證：異常")
        RESULTS+=("真實庫驗證：🔴 ${PROD_LINE#*驗證:}")
        OVERALL=1
    elif grep -q "✅ 全過" "$PROD_OUT"; then
        RESULTS+=("真實庫驗證：✅ 全過")
    else
        RESULTS+=("真實庫驗證：⚠️  無法判定結果（見報告）")
        OVERALL=1
    fi
    rm -f "$PROD_OUT"
fi

# ===== 彙整結論 =====
banner "彙整結論"
for r in "${RESULTS[@]}"; do say "  • $r"; done
say ""
if [ "$OVERALL" -eq 0 ]; then
    say "${C_G}${C_B}✅ 資料完整性：全綠${C_0}"
else
    say "${C_R}${C_B}🔴 資料完整性：發現問題，請依上方各層細節處理${C_0}"
    say "   落後的表可用 scripts/backfill_*.py 對症補；不確定補哪支就把本報告貼回。"
fi
say ""
say "完整報告：$REPORT"
exit "$OVERALL"
