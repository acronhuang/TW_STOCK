"""M2 買方再評分器（純函式,決定論,影子模式)。

規則(依 verdict_detail 實證:買進偏向追高+反轉):
  「追高」(事前 20 日動能 > PRIOR_HI)且(價值差 PE 百分位高 或 品質差 ROE 低)
  → 降級持有;否則維持買進。
特徵不足(coverage_ok=False)→ 一律維持買進,絕不亂動 live 判斷。
"""
from __future__ import annotations

# 門檻（可調;升級 live 前須以 out-of-sample 回測校準,見 docs/plans/verdict_buyside_v1.md)
PRIOR_HI = 0.05   # 事前 20 日動能 > 5% 視為追高
PE_HI = 70.0      # PE 百分位 > 70 = 相對貴(價值差)
ROE_LO = 8.0      # ROE < 8% = 品質差


def rescore(feat: dict) -> dict:
    """回 {v2: '買進'|'降級持有', score: float, reason: str}。"""
    if not feat.get("coverage_ok"):
        return {"v2": "買進", "score": 0.0, "reason": "特徵不足,維持原判"}

    prior = feat.get("prior_20d")
    pe_p = feat.get("pe_pctile")
    roe = feat.get("roe")

    chase = prior is not None and prior > PRIOR_HI
    pricey = pe_p is not None and pe_p > PE_HI
    lowq = roe is not None and roe < ROE_LO

    if chase and (pricey or lowq):
        # 分數:懲罰越大越該降級（供排序/檢視;不影響決策)
        score = round((pe_p or 0) / 100.0 + (1.0 if lowq else 0.0), 3)
        why = "追高且" + ("價值差" if pricey else "品質差")
        return {"v2": "降級持有", "score": score, "reason": why}

    return {"v2": "買進", "score": 0.0, "reason": "維持買進"}
