#!/usr/bin/env bash
# 台股分析助理（唯讀）：在中性目錄啟動 Hermes，避免它吃進專案的 CLAUDE.md。
# 用法：hq            互動對話
#       hq 問題文字   一次性提問，例如：hq 鴻海外資昨天買賣超幾張
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/hermes_work" && cd "$HOME/hermes_work" || exit 1
if [ $# -eq 0 ]; then
  exec hermes
fi
exec hermes -z "$*"
