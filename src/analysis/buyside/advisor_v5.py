"""v5 草案 — advisor 整合判準的『追高防制』regime-aware 包裝(影子,不動 live)。

診斷(docs/plans/verdict_buyside_v3.md §8-9):追高偏誤源自 advisor 把 technical
『上升趨勢』天真當買進理由(現行 prompt 甚至要求評級呼應技術型態方向)。
v5 只在『趨勢市』附加追高防制條款,盤整市維持(已達標);不改 live prompt,
由影子 runner 用本包裝重跑 advisor 整合寫平行評級,回測驗證後才議切換。
"""
from __future__ import annotations

TRENDING = ("多頭", "空頭")

ANTI_CHASE_CLAUSE = (
    "⚠️ 追高防制（趨勢市專用）：近期上升趨勢／技術偏多『本身不構成』買進理由。\n"
    "給『買進／強力買進』前,須至少一項獨立佐證:\n"
    "  (1) 估值未偏貴（value-analyst 判低估或合理）;\n"
    "  (2) 品質佳（fundamental 三率向上 或 高 ROE）;\n"
    "  (3) 明確反轉／回檔後再起訊號(非追在漲勢末端)。\n"
    "若僅有動能／技術偏多而無上述任一佐證,評級最高只能『觀望』。\n"
    "(本條僅趨勢市套用;盤整市維持原判準,不受影響。)"
)


def build_advisor_prompt_v5(base_prompt: str, regime: str | None) -> str:
    """在現行 advisor prompt 之上,趨勢市附加追高防制條款;盤整/未知市況維持原樣。

    base_prompt = 現行 build_expert_prompt('investment-advisor', ...) 的輸出。
    regime = classify_regime(...) 的回傳。
    """
    if regime in TRENDING:
        return base_prompt + "\n\n" + ANTI_CHASE_CLAUSE
    return base_prompt
