#!/usr/bin/env bash
# Phase 0-G 護欄：阻擋「新增」的硬編碼 IP / 絕對路徑。
#
# 策略：只檢查相對 base 分支「新增的行」(diff +)，不追究既有 490 處 baseline，
# 只擋新的技術債流入。既有硬編碼由 Phase 1 設定收斂逐步清除。
#
# 用法：
#   scripts/check_no_hardcode.sh              # CI：自動判斷 base(PR/推送)
#   BASE_REF=main scripts/check_no_hardcode.sh # 本機指定 base
set -euo pipefail

# 決定 base ref：PR 用 origin/<base>；否則用前一 commit。
if [[ -n "${GITHUB_BASE_REF:-}" ]]; then
    BASE="origin/${GITHUB_BASE_REF}"
elif [[ -n "${BASE_REF:-}" ]]; then
    BASE="${BASE_REF}"
else
    BASE="HEAD~1"
fi

echo "▏比對 base：${BASE}"

# 只看程式碼目錄的新增行；排除設定單一真相源與範例檔。
DIFF=$(git diff "${BASE}...HEAD" -- src/ scripts/ dashboard/ \
       ':(exclude)src/config.py' ':(exclude)*.env*' ':(exclude)**/__pycache__/**' \
       2>/dev/null || git diff "${BASE}" -- src/ scripts/ dashboard/)

# 抽出新增行（+ 開頭，排除 diff 標頭 +++），去掉前導 + 與空白。
ADDED=$(printf '%s\n' "${DIFF}" | grep -E '^\+' | grep -Ev '^\+\+\+' | sed -E 's/^\+[[:space:]]*//')

# 過濾純註解行（# 開頭）——文件/註解中的 IP 不算技術債；
# 以及標注 `# allow-hardcode` 的刻意設定預設行（待 Phase 1 收斂至 config）。
CODE=$(printf '%s\n' "${ADDED}" | grep -Ev '^#' | grep -v 'allow-hardcode' || true)

# 偵測：原始 IPv4、或 /home/<user>/ 絕對路徑。
VIOLATIONS=$(printf '%s\n' "${CODE}" \
    | grep -nE '([0-9]{1,3}\.){3}[0-9]{1,3}|/home/[a-zA-Z0-9_]+/' || true)

if [[ -n "${VIOLATIONS}" ]]; then
    echo "❌ 偵測到新增的硬編碼 IP / 絕對路徑（請改用 src/config.py 或環境變數）："
    printf '%s\n' "${VIOLATIONS}"
    exit 1
fi

echo "✅ 無新增硬編碼 IP / 絕對路徑"
