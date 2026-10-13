"""Ollama 前置檢查：分析以 Ollama 為硬性前提，節點或模型缺席就在開跑前停下。"""
from __future__ import annotations

import time

import requests

from src.moe import model_nodes


class OllamaNotReady(RuntimeError):
    pass


_canon = model_nodes.canonical  # Ollama 把沒寫標籤的模型名視為 :latest


def _registered(table: dict[str, str], model: str) -> str:
    url = table.get(model)
    if url is None:
        raise OllamaNotReady(f"模型 {model} 沒有登記節點（src/moe/model_nodes.py）")
    return url


def required_models(roles: list[str], include_consensus: bool = True,
                    include_aux: bool = False) -> dict[str, set[str]]:
    """節點 -> 該節點必須有的模型；節點對應與 ask_role／合議實際使用的是同一份表。"""
    from src.moe import consensus, model_nodes, role_router

    required: dict[str, set[str]] = {}

    def need(url: str, model: str) -> None:
        required.setdefault(url.rstrip("/"), set()).add(model)

    for role in [*roles, "investment-advisor"]:
        model = role_router.ROLE_TO_MODEL[role]
        need(_registered(role_router.MODEL_TO_URL, model), model)
    if include_consensus:
        for model in consensus.COMMITTEE:
            need(_registered(consensus.COMMITTEE_MODEL_URL, model), model)
        need(consensus.FACILITATOR_URL, consensus.FACILITATOR_MODEL)
    if include_aux:
        need(model_nodes.answer_url(), model_nodes.ANSWER_MODEL)
        need(model_nodes.embed_url(), model_nodes.EMBED_MODEL)
    return required


def check_ollama(required: dict[str, set[str]], get=requests.get, timeout: int = 10) -> list[str]:
    problems = []
    for url, models in sorted(required.items()):
        try:
            response = get(f"{url}/api/tags", timeout=timeout)
            response.raise_for_status()
            have = {m.get("name") for m in response.json().get("models", [])}
        except Exception as error:  # noqa: BLE001 - any failure means the node cannot serve.
            problems.append(f"{url} 無法連線：{error}")
            continue
        have_canon = {_canon(name) for name in have if name}
        missing = sorted(model for model in models if _canon(model) not in have_canon)
        if missing:
            problems.append(f"{url} 缺少模型：{', '.join(missing)}")
    return problems


def ensure_ready(required: dict[str, set[str]], get=requests.get, timeout: int = 10) -> None:
    problems = check_ollama(required, get=get, timeout=timeout)
    if problems:
        raise OllamaNotReady("; ".join(problems))


def wait_until_ready(required: dict[str, set[str]], retries: int, interval_sec: int,
                     sleep=time.sleep, get=requests.get, on_wait=None) -> None:
    """節點掛掉時等它回來：最多重試 retries 次、每次間隔 interval_sec；用完仍不通就拋 OllamaNotReady。"""
    for attempt in range(retries + 1):
        try:
            ensure_ready(required, get=get)
            return
        except OllamaNotReady as error:
            if attempt == retries:
                raise
            if on_wait:
                on_wait(f"Ollama 未就緒（{error}），{interval_sec} 秒後重試 {attempt + 1}/{retries}")
            sleep(interval_sec)
