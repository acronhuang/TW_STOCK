"""MoE 決策守門 —— 阻斷『錯誤訊息當意見』污染投資判斷。

背景（實測，見 role_router.py / team_daily_verified.py 註解）：
  角色 LLM 呼叫失敗時，呼叫端會把 reports[role] 寫成「分析失敗: …」字串，
  而顧問整合(investment-advisor)與合議(consensus)照樣拿它去整合、投票——
  流程全綠、log 正常，實際上是一段錯誤訊息參與了投資決策。
  2026-08-19 實測：risk-manager 200 檔中 61 檔如此。

本模組把守門邏輯集中化（原本只存在於 team_daily_verified 的區域函式，
team_analyze 無法共用），提供單一真相源給所有呼叫端。

投票層(consensus.deliberate/_finalize)已自行以 vote=None 排除 ERR 委員，
不需經本模組；本模組專責『角色報告 → 顧問整合』這條資料流。
"""
from __future__ import annotations

# 呼叫端寫入失敗報告時使用的前綴（team_analyze / team_daily_verified 一致）。
FAIL_PREFIX = "分析失敗"
# 顧問整合失敗前綴（供其他守門判斷共用）。
_INTEGRATION_FAIL_PREFIX = "整合失敗"


def is_failed_report(value) -> bool:
    """判斷一份角色報告是否其實是錯誤訊息（不得參與決策）。

    非字串（如 None、dict）視為『非可用報告』但不在此拋錯，交由上游處理。
    """
    if not isinstance(value, str):
        return False
    text = value.lstrip()
    return text.startswith(FAIL_PREFIX) or text.startswith(_INTEGRATION_FAIL_PREFIX)


def usable_reports(reports: dict | None) -> dict:
    """濾掉『內容其實是錯誤訊息』的角色報告，回傳可安全餵給顧問整合的子集。

    - 保留原始 reports 供稽核／--skip-done 判斷；此函式只回可用子集。
    - 全部失敗時回空 dict，由呼叫端決定略過整合（不以錯誤訊息做決策）。
    """
    return {
        role: text
        for role, text in (reports or {}).items()
        if not is_failed_report(text)
    }


def partition_reports(reports: dict | None) -> tuple[dict, list[str]]:
    """回 (可用報告, 失敗角色清單)。供呼叫端記錄／告警哪些角色靜默降級。"""
    reports = reports or {}
    ok = usable_reports(reports)
    failed = [role for role in reports if role not in ok]
    return ok, failed
