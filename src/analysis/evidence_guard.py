"""EvidenceGuard —— 事後驗證國際新聞 LLM 輸出是否受外部證據約束。

背景：`international_news.generate_analysis` 以 `SYSTEM` 六條規範要求模型只依外部
新聞證據作答，但 14B 模型在證據稀少時仍可能腦補台股標的或因果（可行性報告最沒把握
第 1 項）。單元測試只能驗證「提示內容」，無法驗證「輸出遵守度」——本模組補這一段：
在顯示前檢查輸出，逸出證據時標記 `flagged=True` 並附原因，供 UI 降級呈現。

不改寫模型輸出（避免二次失真），只做偵測與標記。
"""
from __future__ import annotations

import re

# 台股代號：4 位數字（可含興櫃 6 位、上市櫃 4~6 位），前後為非數字邊界。
_TW_SYMBOL = re.compile(r"(?<!\d)(\d{4,6})(?!\d)")
# 段落：以中文全形標題冒號或換行切分的實質行。
_SECTION_SPLIT = re.compile(r"[\r\n]+")


def extract_citations(text: str) -> list[int]:
    """抽出所有 [n] 引用編號（去重、保序）。"""
    seen, out = set(), []
    for m in re.findall(r"\[(\d+)\]", text or ""):
        n = int(m)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _substantive_lines(text: str) -> list[str]:
    """回傳需要引用的實質段落行（跳過空行與純標題行）。"""
    lines = []
    for raw in _SECTION_SPLIT.split(text or ""):
        line = raw.strip()
        if not line:
            continue
        # 純標題行（如「可能影響：」結尾無內容）不強制引用
        if re.fullmatch(r"[\u4e00-\u9fa5A-Za-z／/·、]+[:：]?", line):
            continue
        lines.append(line)
    return lines


def guard_analysis(text: str, n_sources: int, evidence_text: str = "") -> dict:
    """驗證分析輸出。回 {flagged: bool, reasons: [str], citations: [int]}。

    規則：
      1. 空輸出 → flagged。
      2. 任一引用編號 > n_sources 或 < 1 → flagged（引用不存在的證據）。
      3. 任一實質段落缺 [n] 引用 → flagged（無據推論）。
      4. 輸出出現台股代號但不在 evidence_text 中 → flagged（疑似逸出證據）。
    """
    reasons: list[str] = []
    text = (text or "").strip()
    if not text:
        return {"flagged": True, "reasons": ["輸出為空"], "citations": []}

    citations = extract_citations(text)

    # 規則 2：引用範圍
    bad = [n for n in citations if n < 1 or n > max(0, n_sources)]
    if bad:
        reasons.append(f"引用編號超出證據範圍（證據數 {n_sources}）：{bad}")

    # 規則 3：每個實質段落須有引用（「資料不足」等法定回退句免引用，見 SYSTEM 規則 4）
    for line in _substantive_lines(text):
        if "資料不足" in line:
            continue
        if "[" not in line or not re.search(r"\[\d+\]", line):
            reasons.append(f"段落缺少引用：{line[:30]}")

    # 規則 4：台股代號需在證據中出現
    ev_symbols = set(_TW_SYMBOL.findall(evidence_text or ""))
    for sym in _TW_SYMBOL.findall(text):
        if sym not in ev_symbols:
            reasons.append(f"輸出提及台股代號 {sym} 但外部證據未包含（疑似逸出證據）")

    return {"flagged": bool(reasons), "reasons": reasons, "citations": citations}
