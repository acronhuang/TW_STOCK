"""根據外部新聞標題產生受證據限制的國際事件分析。"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from urllib.parse import urlparse

OLLAMA = os.getenv("RAG_OLLAMA_URL", "http://172.16.9.27:11434").rstrip("/")
MODEL = "qwen2.5-14b:latest"

# 防提示注入/資源耗用：使用者輸入長度上限。
MAX_QUESTION_LEN = 500
MAX_EVENT_TYPE_LEN = 40
# SSRF (CWE-918) 白名單：只允許連到已知 Ollama 主機；env 可覆寫（逗號分隔）。
_DEFAULT_ALLOWED = "172.16.9.27,172.16.9.28,localhost,127.0.0.1"
ALLOWED_OLLAMA_HOSTS = {
    h.strip() for h in os.getenv("RAG_OLLAMA_ALLOWED_HOSTS", _DEFAULT_ALLOWED).split(",") if h.strip()
}


def assert_allowed_host(url: str) -> None:
    """校驗 URL 主機在白名單內，否則拋 ValueError（防 SSRF）。"""
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_OLLAMA_HOSTS:
        raise ValueError(f"Ollama 主機不在白名單：{host!r}（允許：{sorted(ALLOWED_OLLAMA_HOSTS)}）")

SYSTEM = """你是台股國際事件分析助理。只能依據提供的外部新聞證據作答。

規則：
1. 使用繁體中文，每一句事實與推論都須附上至少一個來源編號，例如 [1]。
2. 輸出固定四節：可能影響、受影響產業、台股關聯標的、風險與不確定性。
3. 每節只描述新聞標題直接支持的內容或以「可能」表達的合理影響；不可補充新聞未提及的事實。
4. 台股關聯標的只能列出新聞證據明確提到的台灣公司或股票代號；沒有時寫「資料不足，新聞證據未明示台股標的。」
5. 在風險與不確定性的第一項，固定寫：`新聞僅為標題，無法確認完整內容、時效性和因果關係 [1]。`
6. 不可使用專案內資料、訓練知識或未提供的網路內容。"""


def build_prompt(question: str, event_type: str, articles: list[dict[str, str]]) -> str:
    """建立僅含外部 RSS 標題與連結的分析提示。"""
    # 防提示注入/資源耗用：截斷使用者可控輸入。
    question = (question or "")[:MAX_QUESTION_LEN]
    event_type = (event_type or "")[:MAX_EVENT_TYPE_LEN]
    evidence = []
    for index, article in enumerate(articles, 1):
        evidence.append(
            f"[{index}] {article.get('source', 'Google News RSS')} · "
            f"{article.get('published_at', '時間不明')}\n"
            f"標題:{article.get('title', '')}\n連結:{article.get('url', '')}"
        )
    return (
        f"事件類型:{event_type}\n問題:{question}\n\n"
        f"外部新聞證據:\n{chr(10).join(evidence)}\n\n"
        "只能依據提供的外部新聞證據，依序產生「可能影響、受影響產業、台股關聯標的、風險與不確定性」。"
    )


def generate_analysis(question: str, event_type: str, articles: list[dict[str, str]], timeout: int = 120) -> tuple[str, float]:
    """以外部 RSS 證據生成分析；無證據時不呼叫模型。"""
    if not articles:
        return "沒有可用的外部新聞證據，無法進行國際新聞分析。", 0.0
    payload = {
        "model": MODEL,
        "system": SYSTEM,
        "prompt": build_prompt(question, event_type, articles),
        "stream": False,
        "options": {"num_predict": 700, "temperature": 0.1, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    assert_allowed_host(OLLAMA)  # SSRF 防護：呼叫前校驗主機白名單
    started_at = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read())
    return result.get("response", "").strip(), time.time() - started_at