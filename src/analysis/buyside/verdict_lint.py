"""P2 影子一致性 lint — 標記買進 verdict 的內部矛盾,只寫 shadow 欄。

嚴格影子:絕不改 final_verdict / verdict / consensus / advisor。
只新增 team_analysis.shadow_lint 觀測欄(附加式,不動任何 live 判斷)。

破綻(源自 docs/plans/buyside_verdict_quality_audit.md):
  ① 追高    進場價 > 現價
  ② 0張買進  評級買進但張數 0
  ③ 風報比<1 技術自己的數字不划算卻買進
  ④ 合議壞票 空模板/無理由票被計入 tally
"""
from __future__ import annotations

import re

_HOLLOW = re.compile(r'投下了以下票數[:：]?\s*$|^\s*我是投資決策委員會的成員')


def _num(pattern: str, text: str):
    m = re.search(pattern, text or "")
    return float(m.group(1)) if m else None


def _is_hollow(reason: str) -> bool:
    r = (reason or "").strip()
    return bool(_HOLLOW.search(r)) or len(r) < 10


def lint_verdict(doc: dict) -> dict:
    """對單一 team_analysis 文件算一致性紅旗。純函式,可測。

    回 {chase_entry, buy_zero_shares, bad_risk_reward, risk_reward, entry_price,
        hollow_votes, hollow_vote_models, flags, score}
    score = 紅旗數(越高越不可信)。
    """
    adv = doc.get("advisor") or ""
    price = doc.get("price_at_analysis")
    reps = doc.get("reports") or {}
    tech = reps.get("technical-analyst", "") or ""
    flags: list[str] = []

    # ① 追高:進場價 > 現價(+0.5% 容差)
    entry = _num(r'進場價[:：]\s*([\d.]+)', adv)
    try:
        pf = float(price) if price is not None else None
    except (TypeError, ValueError):
        pf = None
    chase = bool(entry is not None and pf and entry > pf * 1.005)
    if chase:
        flags.append(f"追高:進場價{entry}>現價{price}")

    # ② 買進 × 0 張
    zero = bool(re.search(r'張數[:：]\s*0\s*張', adv))
    if zero:
        flags.append("買進但0張")

    # ③ 風報比 < 1(取技術報告中最小者)
    rrs = re.findall(r'風報比[=＝:：]?\s*([\d.]+)', tech)
    rr = min((float(x) for x in rrs), default=None)
    bad_rr = bool(rr is not None and rr < 1)
    if bad_rr:
        flags.append(f"風報比<1({rr})")

    # ④ 合議壞票(空模板/無理由)
    votes = (doc.get("consensus") or {}).get("votes") or []
    hollow = [v.get("model", "?") for v in votes if _is_hollow(v.get("reason"))]
    if hollow:
        flags.append(f"合議壞票×{len(hollow)}:{','.join(hollow)}")

    return {
        "chase_entry": chase,
        "buy_zero_shares": zero,
        "bad_risk_reward": bad_rr,
        "risk_reward": rr,
        "entry_price": entry,
        "hollow_votes": len(hollow),
        "hollow_vote_models": hollow,
        "flags": flags,
        "score": len(flags),
    }


def run_lint(db, only_buy: bool = True, dry_run: bool = False,
             field: str = "shadow_lint") -> dict:
    """對 team_analysis 買進列寫 shadow_lint。回統計摘要。絕不改 live 欄。"""
    q = {"final_verdict": "買進"} if only_buy else {}
    proj = {"advisor": 1, "price_at_analysis": 1, "reports": 1,
            "consensus": 1, "final_verdict": 1}
    n = 0
    agg = {"chase_entry": 0, "buy_zero_shares": 0, "bad_risk_reward": 0,
           "any_hollow": 0, "clean": 0}
    for d in db["team_analysis"].find(q, proj):
        res = lint_verdict(d)
        if not dry_run:
            db["team_analysis"].update_one({"_id": d["_id"]}, {"$set": {field: res}})
        n += 1
        agg["chase_entry"] += int(res["chase_entry"])
        agg["buy_zero_shares"] += int(res["buy_zero_shares"])
        agg["bad_risk_reward"] += int(res["bad_risk_reward"])
        agg["any_hollow"] += int(res["hollow_votes"] > 0)
        agg["clean"] += int(res["score"] == 0)
    agg["n"] = n
    return agg
