"""合議軌跡評估：把一筆團隊分析紀錄當成一條『軌跡』，量角色覆蓋、失敗角色、委員票數、輪數與空洞投票。

借自 daily_stock_analysis 的 agent_trajectory 評估（期望工具命中、失敗、重試、步數），改成本專案的角色與委員：
純函式、不碰資料庫與模型；缺欄位當成「沒有」，不補 0 也不補預設通過。
"""
EXPECTED_ROLES = ("macro-analyst", "technical-analyst", "fundamental-analyst", "value-analyst", "risk-manager", "chip-analyst")
EXPECTED_VOTES = 3
FAILURE_PREFIX = "分析失敗"
HOLLOW_MARK = "合議壞票"


def failed_roles(doc: dict) -> list[str]:
    reports = doc.get("reports") or {}
    return [role for role in EXPECTED_ROLES
            if role in reports and (not str(reports[role] or "").strip() or str(reports[role]).startswith(FAILURE_PREFIX))]


def trajectory(doc: dict) -> dict:
    reports = doc.get("reports") or {}
    consensus = doc.get("consensus") or {}
    flags = (doc.get("shadow_lint") or {}).get("flags") or []
    missing = [role for role in EXPECTED_ROLES if role not in reports]
    votes = consensus.get("n")
    hollow = sum(1 for flag in flags if HOLLOW_MARK in str(flag))
    violations = []
    if missing:
        violations.append(f"缺角色：{'、'.join(missing)}")
    if failed_roles(doc):
        violations.append(f"角色失敗：{'、'.join(failed_roles(doc))}")
    if consensus and (votes is None or votes < EXPECTED_VOTES):
        violations.append(f"委員票數 {votes} 少於 {EXPECTED_VOTES}")
    if hollow:
        violations.append(f"空洞投票 {hollow} 張")
    return {
        "symbol": doc.get("symbol"),
        "role_hit_rate": (len(EXPECTED_ROLES) - len(missing)) / len(EXPECTED_ROLES),
        "missing_roles": missing,
        "failed_roles": failed_roles(doc),
        "has_consensus": bool(consensus),
        "votes": votes,
        "rounds": consensus.get("rounds_run"),
        "dissent": len(consensus.get("dissent") or []),
        "hollow_votes": hollow,
        "violations": violations,
    }


def summarize(docs: list[dict]) -> dict:
    runs = [trajectory(doc) for doc in docs]
    with_consensus = [r for r in runs if r["has_consensus"]]
    rounds = [r["rounds"] for r in with_consensus if r["rounds"] is not None]
    return {
        "records": len(runs),
        "with_consensus": len(with_consensus),
        "role_hit_rate": sum(r["role_hit_rate"] for r in runs) / len(runs) if runs else None,
        "records_with_failed_role": sum(1 for r in runs if r["failed_roles"]),
        "vote_shortfall": sum(1 for r in with_consensus if r["votes"] is None or r["votes"] < EXPECTED_VOTES),
        "hollow_vote_records": sum(1 for r in runs if r["hollow_votes"]),
        "two_round_share": (sum(1 for n in rounds if n >= 2) / len(rounds)) if rounds else None,
        "dissent_share": (sum(1 for r in with_consensus if r["dissent"]) / len(with_consensus)) if with_consensus else None,
        "violating": [r for r in runs if r["violations"]],
    }
