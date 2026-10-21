"""模型編制與模型到 Ollama 節點的唯一對照。

換模型只改這個檔（或用環境變數 MODEL_NODES 登記節點、各 *_MODEL 環境變數指定模型）；
其他程式不得再寫死模型名，tests/test_model_nodes.py 會掃描並擋下。
"""

import os

NODE_28 = os.getenv("OLLAMA_URL", "http://172.16.9.28:11434")  # 主力
NODE_27 = os.getenv("OLLAMA_CONSENSUS_URL", "http://172.16.9.27:11434")  # 合議

# 預設編制（2026-10-19 換新，舊的四個模型已停用）：
#   .28 放 MoE 主力（總經/基本面/技術/顧問/主持人；價值、籌碼與風控已改規則模板，見 rule_roles.py）、嵌入與 IBM 委員；
#   .27 放密集 27B（知識庫回答/委員）與 Google 委員。
# 技術與價值/籌碼走主力 MoE：同提示詞實測 MoE 約 6 秒、密集 27B 約 41 秒，全放 .27 會拖垮整批。
# 委員三位來自三家不同訓練來源（Alibaba、Google、IBM），主持人用主力 MoE（不投票）。
# 第三席不用 ministral-3:8b：12 檔實測 12 票全是賣出、輸出格式也不守「第二行寫理由」；granite4.2:8b 票型分散且守格式。
DEFAULT_MAIN = "qwen3.5:35b-a3b-q4_K_M"
DEFAULT_VIEW = DEFAULT_MAIN
DEFAULT_EMBED = "bge-m3"
DEFAULT_RISK = "qwen3.8:27b-q4_K_M"
DEFAULT_TECH = DEFAULT_MAIN
DEFAULT_MEMBER_GOOGLE = "gemma4:12b-it-q4_K_M"
DEFAULT_MEMBER_IBM = "granite4.2:8b-q4_K_M"
DEFAULT_COMMITTEE = (DEFAULT_RISK, DEFAULT_MEMBER_GOOGLE, DEFAULT_MEMBER_IBM)
DEFAULT_DEVIL = DEFAULT_RISK

DEFAULT_NODES = {
    DEFAULT_MAIN: NODE_28,
    DEFAULT_EMBED: NODE_28,
    DEFAULT_MEMBER_IBM: NODE_28,
    DEFAULT_RISK: NODE_27,
    DEFAULT_MEMBER_GOOGLE: NODE_27,
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

# 專案知識庫回答、決策問答、國際新聞分析共用的回答模型。
ANSWER_MODEL = os.getenv("ANSWER_MODEL", DEFAULT_RISK)
# 知識庫嵌入模型；換了要重建語料（向量維度不同）並改 stockrag_ingest.DIM。
EMBED_MODEL = os.getenv("EMBED_MODEL", DEFAULT_EMBED)
HERMES_MODEL = "hermes-qwen3-4b"  # Hermes 總指揮用（.27，由 ~/.hermes/config.yaml 指定），不在團隊分析編制內，所以不進 DEFAULT_NODES


def canonical(name):
    """Ollama 把沒寫標籤的模型名視為 :latest，比對節點清單時要先統一。"""
    return name if ":" in name else f"{name}:latest"


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
