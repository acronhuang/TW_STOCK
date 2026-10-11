"""Ollama 前置檢查：分析以 Ollama 為硬性前提，節點或模型缺席就在開跑前停下。"""
from __future__ import annotations

import time

import requests


class OllamaNotReady(RuntimeError):
    pass


def required_models(roles: list[str], include_consensus: bool = True) -> dict[str, set[str]]:
    """節點 -> 該節點必須有的模型；節點對應與 ask_role／合議實際使用的是同一份表。"""
    from src.moe import consensus, role_router

    required: dict[str, set[str]] = {}

    def need(url: str, model: str) -> None:
        required.setdefault(url.rstrip("/"), set()).add(model)

    for role in [*roles, "investment-advisor"]:
        model = role_router.ROLE_TO_MODEL[role]
        need(role_router.MODEL_TO_URL.get(model, role_router.OLLAMA_URL), model)
    if include_consensus:
        for model in consensus.COMMITTEE:
            need(consensus.COMMITTEE_MODEL_URL.get(model, consensus.CONSENSUS_URL), model)
        need(consensus.FACILITATOR_URL, consensus.FACILITATOR_MODEL)
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
        missing = sorted(models - have)
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
