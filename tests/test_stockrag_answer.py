"""專案知識庫回答器的模型端點測試。"""
import importlib
import os
from unittest.mock import patch

import pytest

from scripts import stockrag_answer


@pytest.mark.unit
def test_rag_uses_consensus_ollama_endpoint_by_default():
    """qwen2.5-14b 已部署在合議節點，RAG 應預設向 .27 請求。"""
    with patch.dict(os.environ, {}, clear=True):
        configured_answerer = importlib.reload(stockrag_answer)
        try:
            assert configured_answerer.OLLAMA == 'http://172.16.9.27:11434'
        finally:
            importlib.reload(configured_answerer)