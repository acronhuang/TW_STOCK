"""答案數字核對：LLM 只負責敘述，數字必須是程式帶進 prompt 的原文。

找不到出處的數字不是一定錯（可能是模型自己算的），但不得被當成資料採用，頁面會列出來請使用者核對。
"""
from __future__ import annotations

import re

_DATE = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}/\d{1,2}")
_NUMBER = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?%?")


def _plain(token: str) -> str:
    return token.replace(",", "").replace("%", "").lstrip("+-")


def _is_figure(plain: str, token: str) -> bool:
    """帶小數、百分比，或整數位數達 3 位以上才算「數字」；人數、項數這類小整數不核對。"""
    return "." in plain or token.endswith("%") or len(plain) >= 3


def unsupported_numbers(answer: str, context: str) -> list[str]:
    supported = {float(_plain(t)) for t in _NUMBER.findall(context)}
    flagged: list[str] = []
    for token in _NUMBER.findall(_DATE.sub(" ", answer)):
        plain = _plain(token)
        if not _is_figure(plain, token) or plain in flagged:
            continue
        value = float(plain)
        whole = "." not in plain
        if value in supported or (whole and any(round(s) == value for s in supported)):
            continue
        flagged.append(plain)
    return flagged
