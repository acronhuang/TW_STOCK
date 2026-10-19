"""TDD: 只剩 11434 的兩個正式節點；Hermes 專用的 11435 已關閉，不能再被監控而一直告警。"""

import pytest

from scripts import ollama_watch

pytestmark = pytest.mark.unit


def test_only_the_two_production_nodes_are_watched():
    assert set(ollama_watch.NODES) == {"主力(.28)", "合議(.27)"}


def test_nothing_watches_the_closed_11435_port():
    assert all(":11435" not in url for url in ollama_watch.NODES.values())
