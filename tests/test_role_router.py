"""角色模型端點路由測試。"""
import importlib
import os
from unittest.mock import patch

import pytest

import src.moe.role_router as role_router


@pytest.mark.unit
def test_qwen3_30b_uses_configured_altos_url():
    """Altos 的 qwen3:30b 必須只在設定 URL 後走向該節點。"""
    with patch.dict(
        os.environ,
        {'OLLAMA_ALTOS_URL': 'http://172.16.9.44:30957'},
        clear=False,
    ):
        configured_router = importlib.reload(role_router)
        try:
            assert (
                configured_router.MODEL_TO_URL['qwen3:30b']
                == 'http://172.16.9.44:30957'
            )
        finally:
            importlib.reload(configured_router)