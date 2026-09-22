"""設定中心 —— 單一真相源 (Single Source of Truth)。

Phase 1 設定收斂：把散落全樹的 MongoDB URI、Ollama 節點、專案路徑、API token
集中於此。所有值皆 `os.getenv` 讀取，預設值與遷移前的硬編碼一致（不改行為）；
需多環境部署或換節點時，只改環境變數，不動程式碼。

用法：
    from src.config import MONGODB_URI, MONGODB_DATABASE, get_db, OLLAMA_URL
    db = get_db()                      # 依 config 連 MongoDB
    db = get_db("other_database")      # 指定 DB 名

設計原則：
    - 不在此硬編碼 IP/路徑以外的預設；預設僅為「維持現狀」的相容值。
    - PROJECT_ROOT 由本檔位置推導 → 可攜（Linux/Windows 皆可），非綁定單機。
"""
from __future__ import annotations

import os
from pathlib import Path

from pymongo import MongoClient  # 供 get_db();測試可 monkeypatch 本名稱


# ── MongoDB ────────────────────────────────────────────────────────────
# 既有全樹慣例：os.getenv('MONGODB_URI', 'mongodb://localhost:27017')。
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "tw_stock_analysis")


# ── Ollama 推理節點 ────────────────────────────────────────────────────
# 主力節點 .28（qwen3/gemma2）；合議節點 .27（qwen2.5-14b/llama3.1）。
# 與 consensus.py / role_router.py 既有 env 名一致。
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://172.16.9.28:11434")
OLLAMA_CONSENSUS_URL = os.getenv("OLLAMA_CONSENSUS_URL", "http://172.16.9.27:11434")
OLLAMA_FACILITATOR_URL = os.getenv("OLLAMA_FACILITATOR_URL", OLLAMA_URL)


# ── 專案路徑（可攜，非綁定 /home/mdsadmin）────────────────────────────
# 由本檔位置推導：src/config.py → 專案根 = 上上層。env 可覆寫。
PROJECT_ROOT = Path(os.getenv("TWSTOCK_PROJECT_ROOT", str(Path(__file__).resolve().parent.parent)))
RESULTS_DIR = Path(os.getenv("TWSTOCK_RESULTS_DIR", str(PROJECT_ROOT / "results")))


# ── 外部 API ───────────────────────────────────────────────────────────
FINMIND_API_TOKEN = os.getenv("FINMIND_API_TOKEN", "")


def get_db(database: str | None = None, **client_kwargs):
    """依 config 建立 MongoDB 連線並回傳 database 物件。

    集中連線建立點，供各模組逐步取代散落的 `MongoClient(...)`（Phase 2 正式收斂）。
    """
    client = MongoClient(MONGODB_URI, **client_kwargs)
    return client[database or MONGODB_DATABASE]
