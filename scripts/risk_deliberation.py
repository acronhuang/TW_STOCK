#!/usr/bin/env python3
"""持倉風控合議 (Phase 2)

對 portfolio_positions 每檔持倉跑 MoE 委員會投票：續抱 / 減碼 / 出場。
訊號：北大四大法則(止損/均線/主力階段/市場週期) + factor(波動/報酬/rsi) + 法人近10日 + 損益%。
重用 src.moe.consensus 的 _ask/COMMITTEE/.27 節點,但用風控專屬 prompt 與投票解析(不動 consensus)。
輸出：risk_analysis collection + LINE spool(進 digest 持倉風險) + console。

用法:
  python scripts/risk_deliberation.py                 # 全部持倉 + 發LINE(有LINE_SPOOL則spool)
  python scripts/risk_deliberation.py --no-line       # 不發
  python scripts/risk_deliberation.py --symbols 2603 5871
"""
import argparse
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bson.decimal128 import Decimal128
from pymongo import MongoClient

from src.moe.consensus import _ask, COMMITTEE, CONSENSUS_URL

RISK_VOTES = ("續抱", "減碼", "出場")
DB = MongoClient("localhost", 27017)["tw_stock_analysis"]


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


def _name(sym):
    ti = DB.taiwan_stock_info.find_one({"stock_id": sym}, {"stock_name": 1})
    return (ti or {}).get("stock_name", "")


def _extract_risk_vote(txt):
    # 出場 > 減碼 > 續抱：先強動作,避免『不建議出場』誤判;先看首行再全文
    for scope in (txt.strip().split("\n", 1)[0], txt):
        if any(k in scope for k in ("出場", "出清", "清倉", "全部賣", "全數賣", "停損出", "stop out")):
            return "出場"
        if any(k in scope for k in ("減碼", "部分賣", "降低部位", "減持", "trim")):
            return "減碼"
        if any(k in scope for k in ("續抱", "抱住", "保留", "續留", "持有", "不動", "hold", "keep")):
            return "續抱"
    return None


def build_context(sym, pos, market_desc):
    from src.strategy.trading_rules import TradingRules
    tr = TradingRules()
    cost = pos.get("avg_cost") or 0
    cat = pos.get("category") or "波段"
    p = DB.stock_price.find_one({"symbol": sym}, sort=[("date", -1)]) or {}
    px = _f(p.get("close"))
    pnl = ((px - cost) / cost * 100) if (px and cost) else None
    stop = tr.check_stop_loss(sym, cost) if cost else {}
    phase = tr.detect_institution_phase(sym) or {}
    f = DB.stock_factors.find_one({"symbol": sym}, sort=[("date", -1)]) or {}
    inst = list(DB.institutional_flow.find({"stock_id": sym}, {"foreign_net": 1}).sort("date", -1).limit(10))
    fnet = sum((_f(x.get("foreign_net")) or 0) for x in inst) / 1000.0

    head = f"{sym} {_name(sym)} [{cat}] 成本{cost}"
    if px is not None:
        head += f" 現價{px}"
    if pnl is not None:
        head += f" 損益{pnl:+.1f}%"
    lines = [head]
    lines.append(f"北大四大法則: 止損動作={stop.get('action', 'n/a')} 帳面{stop.get('pnl_pct', '?')}% "
                 f"均線={stop.get('ma_trend', '?')} 主力階段={phase.get('phase', '?')} 市場={market_desc}")
    lines.append(f"技術/factor: 波動30d={_f(f.get('volatility_30d'))} 近1月={_f(f.get('return_1m'))}% "
                 f"近3月={_f(f.get('return_3m'))}% rsi={_f(f.get('rsi_14'))} ma20乖離={_f(f.get('ma_bias_20'))}")
    lines.append(f"法人近10日外資淨={fnet:+.0f}張")
    try:
        from src.analysis.rolling_unwind import context_line as _roll_line
        _rl = _roll_line(DB, sym, cost, px)
        if _rl:
            lines.append(_rl)
    except Exception:
        pass
    if cat != "波段":
        lines.append(f"註：此為「{cat}」,不適用波段 5% 硬止損,請以長期/領息角度評估。")
    return "\n".join(lines), pnl, stop.get("action")


def deliberate(ctx):
    prompt = (
        "你是持倉風控委員,評估一檔【手上已持有】的部位現在該怎麼處理。\n"
        "三選一：續抱(繼續持有) / 減碼(賣一部分降低風險) / 出場(全部賣出、停損或停利)。\n"
        "考量：是否觸5%止損、均線趨勢、主力階段、帳面損益、波動、法人動向;分類非波段者以長期/領息看。\n"
        "規則：第一行只寫「續抱」或「減碼」或「出場」三選一,第二行用一句話說明理由。 套牢處理:拒絕死扛與盲目補倉——若上方有「套牢評估」,評估『建議停損』(結構轉壞)→傾向出場;評估『可滾動解套』(箱型/跌深有撐+籌碼穩)→續抱並照參考價高拋低吸降成本,勿死抱等回本。\n\n"
        "【部位風險資料】\n" + ctx + "\n\n【你的判定】\n")
    votes = []
    for m in COMMITTEE:
        raw = _ask(m, prompt, url=CONSENSUS_URL)
        votes.append({"model": m, "vote": _extract_risk_vote(raw or ""), "raw": (raw or "").strip()[:220]})
    valid = [x for x in votes if x["vote"]]
    tally = {v: sum(1 for x in valid if x["vote"] == v) for v in RISK_VOTES}
    if not valid:
        final = "續抱"
    else:
        top = max(tally.values())
        leaders = [v for v in RISK_VOTES if tally[v] == top]
        final = leaders[0] if len(leaders) == 1 else ("減碼" if "減碼" in leaders else leaders[0])  # 平手偏保守
    reason = ""
    for x in valid:
        if x["vote"] == final and "\n" in x["raw"]:
            reason = x["raw"].split("\n", 1)[1].strip()[:90]
            break
    return final, tally, votes, reason


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+")
    ap.add_argument("--no-line", action="store_true")
    a = ap.parse_args()

    from src.strategy.trading_rules import TradingRules
    mc = TradingRules().market_cycle()
    market_desc = mc.get("description", "?")

    q = {"symbol": {"$in": a.symbols}} if a.symbols else {}
    positions = list(DB.portfolio_positions.find(q))
    if not positions:
        print("無持倉,結束")
        return
    print(f"持倉風控合議：{len(positions)} 檔 | 市場:{market_desc} | 委員:{COMMITTEE}")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    ICON = {"續抱": "🟢續抱", "減碼": "🟡減碼", "出場": "🔴出場"}
    results = []
    for pos in positions:
        sym = pos["symbol"]
        ctx, pnl, ruleact = build_context(sym, pos, market_desc)
        final, tally, votes, reason = deliberate(ctx)
        print(f"  {sym} {_name(sym)} → {final} (抱{tally['續抱']}/減{tally['減碼']}/出{tally['出場']})")
        doc = {"date": today, "symbol": sym, "name": _name(sym), "category": pos.get("category"),
               "verdict": final, "tally": tally, "reason": reason, "pnl_pct": round(pnl, 1) if pnl is not None else None,
               "rules": ruleact, "cost": pos.get("avg_cost"), "votes": votes, "updated_at": datetime.now()}
        DB.risk_analysis.update_one({"date": today, "symbol": sym}, {"$set": doc}, upsert=True)
        results.append((sym, final, pnl, reason, tally))

    # LINE 訊息(標題含「持倉風控」→ 路由到 digest 持倉/風險主題)
    order = {"出場": 0, "減碼": 1, "續抱": 2}
    results.sort(key=lambda r: order.get(r[1], 9))
    lines = [f"🛡️ 持倉風控合議 ({datetime.now().strftime('%m/%d')})  {len(results)} 檔"]
    lines.append(f"🌡️ 市場: {market_desc}")
    for sym, final, pnl, reason, tally in results:
        pnls = f"{pnl:+.1f}%" if pnl is not None else "—"
        lines.append(f"{ICON.get(final, final)} {sym} {_name(sym)} 損益{pnls} 抱{tally['續抱']}/減{tally['減碼']}/出{tally['出場']}")
        if final != "續抱" and reason:
            lines.append(f"    理由: {reason}")
    msg = "\n".join(lines)
    print("\n" + "=" * 50 + "\n" + msg)

    if not a.no_line:
        try:
            from src.alerts.line_notifier import LineNotifier
            LineNotifier().send(msg)   # 有 LINE_SPOOL 則自動 spool 進 digest
            print("\n(LINE: 已送出/spool)")
        except Exception as e:
            print(f"LINE 失敗: {e}")


if __name__ == "__main__":
    main()
