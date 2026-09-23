"""verdict A/B 前瞻框架 —— 三臂比較 + Ollama vs 規則 差異評估。

背景：多窗回測顯示「買進」在多情境落後大盤（含下跌市），傾向結構性偏弱。
在下定論改模型前，以前瞻 A/B 平行記錄三種決策，日後比超額報酬，避免過擬合歷史：

  ① base      —— 現行 pipeline 的最終 verdict（Ollama MoE 合議）
  ② rule_gate —— 我的規則式動能閘門（買進但非上升趨勢 → 降為持有）
  ③ ollama    —— 讓 Ollama 帶入動能情境「重新判斷」

同時量化「Ollama 判斷 vs 我的規則判斷」的差異（一致率 / 分歧矩陣），
回答『用 Ollama 分析的結果與規則分析差在哪』。

設計：純函式核心（可測）；Ollama 呼叫以 ask_role_fn 注入 → 可 mock、可離線測試。
"""
from __future__ import annotations

from src.audit.verdict_tracker import normalize_verdict

_SYN = [
    ("賣出", ("賣出", "賣", "減碼", "出場", "sell", "看空")),
    ("買進", ("買進", "買", "加碼", "進場", "buy", "看多")),
    ("持有", ("持有", "觀望", "中立", "不動", "hold", "續抱")),
]


def _parse_verdict(text: str) -> str | None:
    """從文字抽票別（賣>買>持 順序避免『不建議買進』誤判）。"""
    if not text:
        return None
    for scope in (text.strip().split("\n", 1)[0], text):
        for canon, kws in _SYN:
            if any(k in scope for k in kws):
                return canon
    return None


def trend_signal(price: float, ma20: float, ma60: float) -> str:
    """依價與均線判趨勢：價>MA20>MA60→up；價<MA20<MA60→down；其餘 neutral。"""
    if price is None or ma20 is None or ma60 is None:
        return "neutral"
    if price > ma20 > ma60:
        return "up"
    if price < ma20 < ma60:
        return "down"
    return "neutral"


def apply_momentum_gate(verdict: str, trend: str) -> str:
    """規則式動能閘門：買進但非上升趨勢 → 降為持有（排除逆勢買）。其餘不變。"""
    v = normalize_verdict(verdict)
    if v == "買進" and trend != "up":
        return "持有"
    return v


def ollama_momentum_verdict(symbol: str, base_verdict: str, indicators: dict,
                            ask_role_fn) -> str | None:
    """Ollama 臂：帶入動能情境讓模型重新判斷。ask_role_fn 注入以便測試/離線。

    回傳 買進/賣出/持有；呼叫失敗（回 dict 含 error 或無 response）回 None。
    """
    price = indicators.get("price")
    ma20 = indicators.get("ma20")
    ma60 = indicators.get("ma60")
    trend = trend_signal(price, ma20, ma60)
    prompt = (
        f"針對 {symbol}，主分析師初步判斷為「{base_verdict}」。\n"
        f"技術動能：現價 {price}、MA20 {ma20}、MA60 {ma60}（趨勢：{trend}）。\n"
        f"請結合動能重新判斷：第一行只寫「買進」或「持有」或「賣出」，第二行一句理由。\n"
        f"注意：逆勢買進（價在均線下仍買）風險高，需有明確止穩訊號才維持買進。"
    )
    resp = ask_role_fn("technical-analyst", prompt)
    if not isinstance(resp, dict) or "error" in resp or not resp.get("response"):
        return None
    return _parse_verdict(resp["response"])


def build_trend_series(docs, value_key: str, ts_key: str = "ts"):
    """將歷史快照 docs → 依時間遞增排序的 [(ts, value)]。

    純函式（免 DB，可測），供 Dashboard 畫趨勢線。value 為 None
    或非數值者跳過；ts 缺失者跳過。同一呼叫不改變輸入。
    """
    pts = []
    for d in docs or []:
        ts = d.get(ts_key)
        v = d.get(value_key)
        if ts is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        pts.append((ts, float(v)))
    pts.sort(key=lambda p: p[0])
    return pts


def compare_verdict_sets(base: dict, variant: dict) -> dict:
    """比較兩組 {symbol: verdict}（Ollama vs 規則，或任兩臂）。

    只比對兩者都有的標的。回 {n, agreement, agreement_rate, changed, matrix}。
    matrix: {(base_verdict, variant_verdict): count}
    """
    common = [s for s in base if s in variant]
    n = len(common)
    matrix: dict = {}
    changed = []
    agreement = 0
    for s in common:
        b = normalize_verdict(base[s])
        v = normalize_verdict(variant[s])
        matrix[(b, v)] = matrix.get((b, v), 0) + 1
        if b == v:
            agreement += 1
        else:
            changed.append(s)
    return {
        "n": n,
        "agreement": agreement,
        "agreement_rate": (agreement / n) if n else None,
        "changed": changed,
        "matrix": matrix,
    }
