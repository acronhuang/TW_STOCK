"""模型編制與模型到 Ollama 節點的唯一對照。

換模型只改這個檔（或用環境變數 MODEL_NODES 登記節點、各 *_MODEL 環境變數指定模型）；
其他程式不得再寫死模型名，tests/test_model_nodes.py 會掃描並擋下。
"""

import os

NODE_28 = os.getenv("OLLAMA_URL", "http://172.16.9.28:11434")  # 主力
NODE_27 = os.getenv("OLLAMA_CONSENSUS_URL", "http://172.16.9.27:11434")  # 合議

# 預設編制：.28 放主力、換視角與嵌入；.27 放風控與技術角色。
DEFAULT_MAIN = "qwen3-14b:latest"
DEFAULT_VIEW = "gemma2:9b"
DEFAULT_EMBED = "bge-m3"
DEFAULT_RISK = "qwen2.5-14b:latest"
DEFAULT_TECH = "llama3.1:8b"
DEFAULT_COMMITTEE = (DEFAULT_VIEW, DEFAULT_RISK, DEFAULT_TECH)
DEFAULT_DEVIL = DEFAULT_RISK

DEFAULT_NODES = {
    DEFAULT_MAIN: NODE_28,
    DEFAULT_VIEW: NODE_28,
    DEFAULT_EMBED: NODE_28,
    DEFAULT_RISK: NODE_27,
    DEFAULT_TECH: NODE_27,
}


class UnregisteredModel(KeyError):
    def __str__(self):
        return self.args[0]


def parse_overrides(text):
    """'模型=網址,模型=網址' 轉成 dict；格式不對就丟 ValueError，不靜默略過。"""
    result = {}
    for item in (part.strip() for part in text.split(",")):
        if not item:
            continue
        model, sep, url = item.partition("=")
        model, url = model.strip(), url.strip()
        if not sep or not model or not url.startswith(("http://", "https://")):
            raise ValueError(f"MODEL_NODES 格式應為 模型=http://主機:埠，收到：{item!r}")
        result[model] = url.rstrip("/")
    return result


MODEL_NODES = {**DEFAULT_NODES, **parse_overrides(os.getenv("MODEL_NODES", ""))}

# 選用的外部節點（環境變數 OLLAMA_ALTOS_URL）上的模型。
ALTOS_MODEL = "qwen3:30b"

# 專案知識庫回答、決策問答、國際新聞分析共用的回答模型。
ANSWER_MODEL = os.getenv("ANSWER_MODEL", DEFAULT_RISK)
# 知識庫嵌入模型；換了要重建語料（向量維度不同）並改 stockrag_ingest.DIM。
EMBED_MODEL = os.getenv("EMBED_MODEL", DEFAULT_EMBED)


def node_of(model):
    try:
        return MODEL_NODES[model]
    except KeyError:
        raise UnregisteredModel(
            f"模型 {model} 沒有登記節點；請加進 src/moe/model_nodes.py 的 DEFAULT_NODES，或設環境變數 MODEL_NODES"
        ) from None


def answer_url():
    return os.getenv("RAG_OLLAMA_URL", "").rstrip("/") or node_of(ANSWER_MODEL)


def embed_url():
    return os.getenv("RAG_EMBED_URL", "").rstrip("/") or node_of(EMBED_MODEL)
