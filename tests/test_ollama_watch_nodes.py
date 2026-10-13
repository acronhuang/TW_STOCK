"""TDD: Ollama 監控涵蓋 Hermes 專用的獨立實例，它掛了要像正式節點一樣告警。"""

import importlib
import os
from unittest.mock import patch

import pytest

from scripts import ollama_watch

pytestmark = pytest.mark.unit


def test_the_lab_instance_is_watched_by_default():
    assert ollama_watch.NODES["獨立(.27:11435)"] == "http://172.16.9.27:11435"


def test_the_two_production_nodes_are_still_watched():
    assert {"主力(.28)", "合議(.27)"} <= set(ollama_watch.NODES)


def test_the_lab_url_can_be_overridden_by_env():
    with patch.dict(os.environ, {"OLLAMA_LAB_URL": "http://10.0.0.9:11435"}):
        reloaded = importlib.reload(ollama_watch)
        try:
            assert reloaded.NODES["獨立(.27:11435)"] == "http://10.0.0.9:11435"
        finally:
            importlib.reload(ollama_watch)
