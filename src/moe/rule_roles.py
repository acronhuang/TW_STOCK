"""不經 LLM 的角色：風控與籌碼的輸出本來就是把已算好的數字改寫成句子。

離線分析：這兩個角色的多空立場幾乎不帶資訊（籌碼 99% 中性、風控本身不分多空），
且風控的部位與停損早已由程式算好；改用固定模板可省兩次最慢的 LLM 呼叫，輸出格式與原本一致。
TEAM_RULE_ROLES 可覆寫（逗號分隔；設成空字串＝全部回到 LLM）。
"""
import os

DEFAULT_RULE_ROLES = ("risk-manager", "chip-analyst")
MODEL_LABEL = "rule-based"


def active(roles):
    raw = os.getenv("TEAM_RULE_ROLES")
    chosen = set(DEFAULT_RULE_ROLES) if raw is None else {r.strip() for r in raw.split(",") if r.strip()}
    return [r for r in roles if r in chosen and r in _RENDERERS]


def _num(v, fmt="{}"):
    return "無資料" if v is None else fmt.format(v)


def _zhang(shares):
    return round(shares / 1000)


def risk_report(data, hint):
    risk = data.get("risk") or {}
    level, var, ret = risk.get("risk_level") or {}, risk.get("var") or {}, risk.get("returns") or {}
    dd, size, ratios = risk.get("drawdown") or {}, risk.get("position_sizing") or {}, risk.get("ratios") or {}
    price, var95 = risk.get("current_price"), var.get("daily_var_95")
    if not level:
        return "風險資料不足，無法評估風險等級與部位。"
    stop = (f"{price * (1 - var95 / 100):.2f}元（現價{price}元 − 日內 VaR 95% {var95}%）"
            if price is not None and var95 is not None else "資料不足")
    position = (hint or "").split("】", 1)[-1].strip() or "資料不足"
    cited = [("current_price", price), ("daily_var_95", var95), ("annual_volatility", ret.get("annual_volatility")),
             ("max_drawdown", dd.get("max_drawdown")), ("risk_level_score", level.get("score")),
             ("max_position_pct", size.get("max_position_pct"))]
    return "\n".join([
        f"風險等級：{level.get('level', '資料不足')}（分數 {_num(level.get('score'))}，{level.get('description', '')}；"
        f"年化波動 {_num(ret.get('annual_volatility'))}%、Beta {_num(ratios.get('beta'))}、最大回撤 {_num(dd.get('max_drawdown'))}%）",
        f"建議部位/張數：{position}",
        f"停損價：{stop}",
        f"單檔上限：半凱利 {_num(size.get('half_kelly'))}、不超過資金的 {_num(size.get('max_position_pct'))}%",
        "📌引用數值：" + "、".join(f"{k}={v}" for k, v in cited if v is not None),
    ])


def chip_report(data):
    inst, chip = data.get("institutional") or [], data.get("chip") or {}
    margin, holder = chip.get("margin") or {}, chip.get("big_holder") or {}
    if not inst and not chip:
        return "籌碼資料不足，無法判讀法人與主力動向。"
    sums = {k: sum(d.get(k) or 0 for d in inst) for k in ("foreign_net", "trust_net", "dealer_net", "total_net")}
    total = sums["total_net"]
    last = inst[-1] if inst else {}
    cited = [("total_net", last.get("total_net")), ("margin_chg", margin.get("margin_chg")), ("short_bal", margin.get("short_bal")),
             ("big400_pct", holder.get("big400_pct")), ("big1000_pct", holder.get("big1000_pct")),
             ("holders_chg_pct", holder.get("holders_chg_pct"))]
    return "\n".join([
        f"法人近{len(inst)}日合計淨{'買超' if total >= 0 else '賣超'}{abs(_zhang(total)):,}張"
        f"（外資{_zhang(sums['foreign_net']):+,}、投信{_zhang(sums['trust_net']):+,}、自營商{_zhang(sums['dealer_net']):+,}）。",
        f"融資餘額{_num(margin.get('margin_bal'))}張（日變動{_num(margin.get('margin_chg'))}），"
        f"融券餘額{_num(margin.get('short_bal'))}張（日變動{_num(margin.get('short_chg'))}）。",
        f"集保大戶：400張以上持股{_num(holder.get('big400_pct'))}%、1000張以上{_num(holder.get('big1000_pct'))}%，"
        f"持股人數週變動{_num(holder.get('holders_chg_pct'))}%。",
        f"籌碼訊號：「{chip.get('籌碼訊號', '無')}」；近5日股價{_num(chip.get('近5日股價%'))}%。",
        "📌引用數值：" + "、".join(f"{k}={v}" for k, v in cited if v is not None),
    ])


_RENDERERS = {
    "risk-manager": lambda data, hint: risk_report(data, hint),
    "chip-analyst": lambda data, hint: chip_report(data),
}


def render(role, data, hint=""):
    return {"role": role, "model": MODEL_LABEL, "response": _RENDERERS[role](data, hint), "elapsed_sec": 0.0}
