"""中文財經標題的詞典情緒評分（與 src.sentiment.analyzer 即時分析共用同一份詞典）。"""
from __future__ import annotations

from src.sentiment.analyzer import NEGATIVE_WORDS, POSITIVE_WORDS


def score_text(text: str) -> float:
    """(正面詞數 − 負面詞數) / (兩者合計) × 100；沒命中任何詞為 0。"""
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    total = positive + negative
    return 0 if total == 0 else (positive - negative) / total * 100


def label(score: float | None) -> str:
    if score is None:
        return "無資料"
    if score > 30:
        return "強烈看多"
    if score > 10:
        return "偏多"
    if score > -10:
        return "中性"
    if score > -30:
        return "偏空"
    return "強烈看空"
