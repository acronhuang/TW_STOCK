#!/bin/bash
# 在 .27 啟動 Hermes 專用的獨立 Ollama 實例（連接埠 11435，與正式實例 11434 分開）。重複執行無害。
# 單並行、q8 KV、64K 上下文，一次只載一個模型，避免跟正式實例的模型搶顯存。
# 部署：複製到 .27 的 ~/ollama_hermes/start.sh，並在該機 crontab 加
#   @reboot sleep 45 && /bin/bash $HOME/ollama_hermes/start.sh
#   */5 * * * * /bin/bash $HOME/ollama_hermes/start.sh     # 掛掉就拉起
set -u
PORT=11435
HOST_IP=172.16.9.27
BASE="$HOME/ollama_hermes"

if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
    exit 0
fi

mkdir -p "$BASE/models"
export OLLAMA_HOST="${HOST_IP}:${PORT}"
export OLLAMA_MODELS="$BASE/models"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KEEP_ALIVE=10m
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_CONTEXT_LENGTH=65536
exec nohup ollama serve >> "$BASE/serve.log" 2>&1 < /dev/null
