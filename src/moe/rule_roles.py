"""不經 LLM 的角色：風控與籌碼的輸出本來就是把已算好的數字改寫成句子。

離線分析：這兩個角色的多空立場幾乎不帶資訊（籌碼 99% 中性、風控本身不分多空），
且風控的部位與停損早已由程式算好；改用固定模板可省兩次最慢的 LLM 呼叫，輸出格式與原本一致。
價值角色（2026-10-21 起）：立場本來就是 valuation.composite.verdict；影子測試（48 檔）與 LLM 版的最後裁決一致率 88%，
落在同編制重跑的雜訊（81%）內，每檔省約 11% 耗時（docs/adr/0023）。
TEAM_RULE_ROLES 可覆寫（逗號分隔；設成空字串＝全部回到 LLM；只想讓價值回到 LLM 就設 risk-manager,chip-analyst）。
"""
import os

DEFAULT_RULE_ROLES = ("risk-manager", "chip-analyst", "value-analyst")
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


def value_report(data, profile=""):
    val = data.get("valuation") or {}
    comp, price = val.get("composite") or {}, val.get("current_price")
    if comp.get("fair_value") is None or price is None:
        # 估值模型各自會寫 reason（淨利為負、無股利…）；有現價就把原因帶出去，別只說資料不足
        reasons = [f"{label}{m['reason']}" for label, m in (("DCF：", val.get("dcf")), ("DDM：", val.get("ddm")), ("PE Band：", val.get("pe_band")))
                   if isinstance(m, dict) and m.get("reason")]
        if price is None or not reasons:
            return "估值資料不足，無法推估合理價。"
        return "\n".join([f"{comp.get('verdict') or '無法判定'}（現價{price}元，沒有可用的合理價）", "；".join(reasons), f"📌引用數值：current_price={price}"])

    def model(label, m, extra=""):
        m = m or {}
        return f"{label}合理價{_num(m.get('fair_value'))}元（{_num(m.get('upside_pct'))}%{extra}）"

    pe = val.get("pe_band") or {}
    pe_extra = f"，{pe.get('zone', '區間無資料')}、本益比{_num(pe.get('current_pe'))}、歷史百分位{_num(pe.get('pe_percentile'))}%" if pe else ""
    cited = [("current_price", price), ("composite_fair_value", comp.get("fair_value")),
             ("dcf_fair_value", (val.get("dcf") or {}).get("fair_value")), ("ddm_fair_value", (val.get("ddm") or {}).get("fair_value")),
             ("pe_band_fair_value", pe.get("fair_value"))]
    lines = [
        f"{comp.get('verdict') or '資料不足'}（現價{price}元、綜合合理價{comp['fair_value']}元，安全邊際{_num(comp.get('upside_pct'))}%；採用{_num(comp.get('models_used'))}個模型）",
        "；".join([model("DCF ", val.get("dcf")), model("DDM ", val.get("ddm")), model("PE Band ", pe, pe_extra)]),
    ]
    if profile:
        lines.append("四維畫像：" + profile)
    lines.append("📌引用數值：" + "、".join(f"{k}={v}" for k, v in cited if v is not None))
    return "\n".join(lines)


_RENDERERS = {
    "risk-manager": lambda data, hint, profile: risk_report(data, hint),
    "chip-analyst": lambda data, hint, profile: chip_report(data),
    "value-analyst": lambda data, hint, profile: value_report(data, profile),
}


def render(role, data, hint="", profile=""):
    return {"role": role, "model": MODEL_LABEL, "response": _RENDERERS[role](data, hint, profile), "elapsed_sec": 0.0}
