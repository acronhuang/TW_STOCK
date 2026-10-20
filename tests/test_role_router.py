"""角色模型端點路由測試。"""
import importlib
import os
from unittest.mock import patch

import pytest

import src.moe.role_router as role_router


@pytest.mark.unit
def test_the_retired_altos_node_is_no_longer_routable_even_if_its_env_is_still_set():
    with patch.dict(os.environ, {'OLLAMA_ALTOS_URL': 'http://172.16.9.44:30957'}, clear=False):
        reloaded = importlib.reload(role_router)
        try:
            assert 'qwen3:30b' not in reloaded.MODEL_TO_URL
            assert not hasattr(reloaded, 'OLLAMA_ALTOS_URL')
        finally:
            importlib.reload(reloaded)
