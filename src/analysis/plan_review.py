"""買賣計畫審查：把使用者陳述的計畫對照風險資料與持倉，逐項檢查風控是否完整。

只檢查計畫的完整性與風險是否可控；不預測漲跌、不保證報酬、不代為下單。
門檻是風控慣例（海龜單位風險約 2%、2N 停損等），不是績效結論。純函式，不連網。
"""

import importlib.util
import re
from pathlib import Path


def _sibling(name):
    """Hermes 外掛以檔案路徑載入本模組，沒有 src 套件可 import，所以同層模組也用路徑載入。"""
    spec = importlib.util.spec_from_file_location(f"_twstock_{name}", Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


atr_sizing = _sibling("atr_sizing")

PASS, WARN, FAIL, MISSING = "通過", "警告", "不通過", "資料不足"
BUY_ACTIONS = ("買進", "加碼")
SELL_ACTIONS = ("賣出", "減碼")
_ACTION_ALIASES = {
    "買進": "買進", "買": "買進", "buy": "買進", "加碼": "加碼", "加倉": "加碼", "add": "加碼",
    "賣出": "賣出", "賣": "賣出", "sell": "賣出", "減碼": "減碼", "減倉": "減碼", "reduce": "減碼",
}
_SYMBOL = re.compile(r"[0-9A-Za-z]{4,8}")
LOT = atr_sizing.LOT

STOP_TOO_TIGHT = 1.0   # 止損離進場價小於幾倍 N 算太近
STOP_TOO_WIDE = 3.0
RISK_WARN = 2.0        # 停損時虧損占總資金 %（海龜單位風險約 2%）
RISK_FAIL = 5.0
CONCENTRATION_FAIL = 30.0
CHASE_MA_BIAS = 9.0    # 2024 年起全市場個股日資料的第 90 百分位（9.1）
CHASE_RSI = 72.0       # 同上（71.5）
CHASE_RETURN_1M = 14.0  # 同上（14.3）
RESIST_BLOCK = 3       # 與 signal_rules.PARAMS["resist_block"] 一致（測試比對）
DISCLAIMER = "計畫審查（只檢查計畫的風控是否完整，不預測漲跌、不保證報酬、不代為下單）"


def _n(value, digits=2):
    text = f"{float(value):.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    if isinstance(value, str):
        try:
            number = float(value.replace(",", "").strip())
        except ValueError:
            return None
        return number if number == number else None
    return None


def normalize(args):
    """回 (計畫 dict, 錯誤訊息)；參數不合法時計畫為 None。"""
    if not isinstance(args, dict):
        return None, "參數必須是物件"
    symbol = args.get("symbol")
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        return None, "symbol 必須是 4 到 8 碼的英數字股票代號"
    action = _ACTION_ALIASES.get(str(args.get("action", "")).strip().lower())
    if action is None:
        return None, "action 必須是 買進、加碼、賣出、減碼"
    plan = {"symbol": symbol, "action": action}
    for key in ("entry", "stop", "capital"):
        if args.get(key) in (None, ""):
            continue
        value = _num(args[key])
        if value is None or value <= 0:
            return None, f"{key} 必須是大於 0 的數字"
        plan[key] = value
    if args.get("stop_pct") not in (None, ""):
        pct = _num(args["stop_pct"])
        if pct is None or not 0 < pct < 100:
            return None, "stop_pct 必須在 0 到 100 之間（百分比）"
        if "stop" in plan:
            return None, "止損價與止損幅度只能給一個"
        plan["stop_pct"] = pct
    for key, factor in (("shares", 1), ("lots", LOT)):
        if args.get(key) in (None, ""):
            continue
        value = _num(args[key])
        if value is None or value <= 0 or int(value) != value:
            return None, f"{key} 必須是正整數"
        if "shares" in plan:
            return None, "shares 與 lots 只能給一個"
        plan["shares"] = int(value) * factor
    return plan, ""


def _plan_text(plan):
    parts = [f"{plan['symbol']} {plan['action']}"]
    if "entry" in plan:
        parts.append(f"進場價 {_n(plan['entry'])} 元")
    if "stop" in plan:
        parts.append(f"止損價 {_n(plan['stop'])} 元")
    if "stop_pct" in plan:
        parts.append(f"止損幅度 {_n(plan['stop_pct'])}%")
    if "shares" in plan:
        parts.append(f"{plan['shares']} 股")
    if "capital" in plan:
        parts.append(f"總資金 {_n(plan['capital'], 0)} 元")
    return "；".join(parts)


def _check(item, status, detail):
    return {"item": item, "status": status, "detail": detail}


def _stop_of(plan, entry):
    if "stop" in plan:
        return plan["stop"]
    if "stop_pct" in plan and entry:
        return entry * (1 - plan["stop_pct"] / 100)
    return None


def check_stop(plan, entry, atr):
    stop = _stop_of(plan, entry)
    hint = f"參考：海龜 2N 停損價 {_n(atr['stop_2n'])} 元。" if atr and atr.get("stop_2n") is not None else ""
    if "stop" not in plan and "stop_pct" not in plan:
        return _check("止損", FAIL, f"計畫沒有止損價或止損幅度；沒有事先決定的出場點，虧損沒有上限。{hint}"), None
    if entry is None:
        return _check("止損", MISSING, "沒有進場價，也查不到現價，無法檢查止損位置。"), stop
    if stop >= entry:
        return _check("止損", FAIL, f"止損價 {_n(stop)} 元不低於進場價 {_n(entry)} 元，買進後立即觸發。"), stop
    distance = entry - stop
    base = f"止損 {_n(stop)} 元，距離進場價 {_n(distance)} 元（{_n(distance / entry * 100)}%）"
    n = atr.get("n") if atr else None
    if not n:
        return _check("止損", PASS, f"{base}；ATR 資料不足，未檢查距離是否合理。"), stop
    mult = distance / n
    if mult < STOP_TOO_TIGHT:
        return _check("止損", WARN, f"{base}，只有 {_n(mult)} 倍 N（N＝{_n(n)} 元），一般波動就可能觸發。{hint}"), stop
    if mult > STOP_TOO_WIDE:
        return _check("止損", WARN, f"{base}，達 {_n(mult)} 倍 N（N＝{_n(n)} 元），停損時的虧損會偏大。{hint}"), stop
    return _check("止損", PASS, f"{base}，約 {_n(mult)} 倍 N（N＝{_n(n)} 元；海龜用 2 倍）。"), stop


def check_risk(plan, entry, stop):
    missing = [name for name, ok in (("股數", "shares" in plan), ("總資金", "capital" in plan),
                                      ("進場價", entry is not None), ("止損", stop is not None)) if not ok]
    if missing:
        return _check("單筆風險", MISSING, "缺少" + "、".join(missing) + "，無法算停損時虧損占總資金的比例。")
    if stop >= entry:
        return _check("單筆風險", MISSING, "止損價不低於進場價，無法算風險。")
    loss = plan["shares"] * (entry - stop)
    pct = loss * 100 / plan["capital"]
    suggested = atr_sizing.shares_for_risk(plan["capital"], entry, stop, 1.0)
    advice = "若要把停損虧損壓在總資金 1% 內，" + (f"約 {suggested // LOT} 張。" if suggested else "連 1 張都超過（可改用零股）。")
    detail = (f"停損時虧損約 {_n(loss, 0)} 元，占總資金 {_n(pct)}%（門檻：超過 {_n(RISK_WARN)}% 警告、"
              f"超過 {_n(RISK_FAIL)}% 不通過）。{advice}")
    status = PASS if pct <= RISK_WARN else WARN if pct <= RISK_FAIL else FAIL
    return _check("單筆風險", status, detail)


def check_size(plan, entry, risk):
    if "shares" not in plan or "capital" not in plan or entry is None:
        return _check("倉位占比", MISSING, "缺少股數、總資金或進場價，無法算這筆占總資金的比例。")
    pct = plan["shares"] * entry * 100 / plan["capital"]
    cap = ((risk or {}).get("position_sizing") or {}).get("max_position_pct")
    cap = _num(cap)
    base = f"這筆約占總資金 {_n(pct)}%"
    if pct > CONCENTRATION_FAIL:
        return _check("倉位占比", FAIL, f"{base}，超過單檔集中度上限 {_n(CONCENTRATION_FAIL)}%。")
    if cap is not None and cap <= 0:
        return _check("倉位占比", WARN, f"{base}；系統風控的半凱利上限為 0%（近一年報酬統計不支持建立部位），請自行確認理由。")
    if cap is not None and pct > cap:
        return _check("倉位占比", WARN, f"{base}，超過系統風控的單檔上限 {_n(cap)}%（半凱利）。")
    return _check("倉位占比", PASS, base + (f"，未超過系統風控的單檔上限 {_n(cap)}%。" if cap is not None else "。"))


def _holding(positions, symbol):
    rows = [r for r in positions if isinstance(r, dict) and str(r.get("symbol")) == symbol]
    shares = sum(_num(r.get("shares")) or 0 for r in rows)
    if not rows or shares <= 0:
        return None
    cost = sum((_num(r.get("shares")) or 0) * (_num(r.get("avg_cost")) or 0) for r in rows)
    return {"shares": int(shares), "avg_cost": cost / shares}


def check_average_down(plan, entry, positions):
    if positions is None:
        return _check("攤平", MISSING, "查不到持倉資料，無法判斷是否攤平。")
    held = _holding(positions, plan["symbol"])
    if held is None:
        return _check("攤平", PASS, "目前沒有這檔的持倉紀錄，視為新倉，不是攤平。")
    if entry is None:
        return _check("攤平", MISSING, "已持有這檔，但沒有進場價也查不到現價，無法比較均價。")
    base = f"已持有 {held['shares']} 股，均價 {_n(held['avg_cost'])} 元"
    if entry < held["avg_cost"]:
        return _check("攤平", WARN, f"{base}；這筆買價 {_n(entry)} 元低於均價，屬向下攤平。除非這是事前就計畫好的加碼點，"
                                    "否則先檢討原本的買進理由，不要為了降低成本而加碼。")
    return _check("攤平", PASS, f"{base}；這筆買價 {_n(entry)} 元不低於均價，不是向下攤平。")


def check_chase(factors):
    if not factors:
        return _check("追高", MISSING, "查不到技術因子資料。")
    bias, rsi, month = _num(factors.get("ma_bias_20")), _num(factors.get("rsi_14")), _num(factors.get("return_1m"))
    if bias is None and rsi is None and month is None:
        return _check("追高", MISSING, "技術因子資料沒有 20 日均線乖離、RSI、近一月報酬。")
    flags = []
    if bias is not None and bias >= CHASE_MA_BIAS:
        flags.append(f"現價高出 20 日均線 {_n(bias)}%")
    if rsi is not None and rsi >= CHASE_RSI:
        flags.append(f"RSI {_n(rsi)}")
    if month is not None and month >= CHASE_RETURN_1M:
        flags.append(f"近一月已漲 {_n(month)}%")
    shown = "、".join(f"{label} {_n(v)}{unit}" for label, v, unit in
                     (("20 日均線乖離", bias, "%"), ("RSI", rsi, ""), ("近一月報酬", month, "%")) if v is not None)
    if flags:
        return _check("追高", WARN, "追高疑慮：" + "、".join(flags) +
                      f"（門檻約為 2024 年起全市場個股日資料的前 10%：乖離 {_n(CHASE_MA_BIAS)}%、RSI {_n(CHASE_RSI)}、"
                      f"近一月 {_n(CHASE_RETURN_1M)}%）。")
    return _check("追高", PASS, f"{shown}，未達追高門檻。")


def check_resistance(resistance):
    """近期在同價位衝高失敗的次數。歷史驗證的效果小於一次來回成本，所以只當風險提示。"""
    count = _num(resistance.get("failed_touches")) if isinstance(resistance, dict) else None
    if count is None:
        return _check("同價位受阻", MISSING, "查不到近期價格資料，無法計算同價位受阻次數。")
    count, window, zone = int(count), int(_num(resistance.get("window")) or 30), _num(resistance.get("zone_high"))
    if count >= RESIST_BLOCK:
        where = f"{_n(zone)} 元附近" if zone is not None else "近期高點附近"
        return _check("同價位受阻", WARN, f"近 {window} 日在{where}有 {count} 次衝高失敗（達 {RESIST_BLOCK} 次）。這只是風險提示："
                      "歷史驗證（2013 至 2026 年，開發期與留存期各一次）中，被這條規則標到的買進條件，之後 20 日平均落後未被標到者約 0.3 到 0.4%，"
                      "小於一次來回交易成本，不是進出場訊號。")
    return _check("同價位受阻", PASS, f"近 {window} 日同價位衝高失敗 {count} 次，未達 {RESIST_BLOCK} 次。")


def check_holding(plan, entry, positions):
    if positions is None:
        return _check("持倉", MISSING, "查不到持倉資料。")
    held = _holding(positions, plan["symbol"])
    if held is None:
        return _check("持倉", FAIL, "目前沒有這檔的持倉紀錄，無從賣出。")
    base = f"持有 {held['shares']} 股，均價 {_n(held['avg_cost'])} 元"
    if "shares" in plan and plan["shares"] > held["shares"]:
        return _check("持倉", FAIL, f"{base}；計畫賣 {plan['shares']} 股，超過持有數量。")
    if entry is None:
        return _check("持倉", PASS, f"{base}。")
    pnl = (entry - held["avg_cost"]) / held["avg_cost"] * 100
    return _check("持倉", PASS, f"{base}；以 {_n(entry)} 元計，相對均價 {_n(pnl)}%。")


def verdict(checks):
    statuses = [c["status"] for c in checks]
    result = FAIL if FAIL in statuses else WARN if WARN in statuses else PASS
    missing = statuses.count(MISSING)
    return f"{result}（另有 {missing} 項資料不足，未能檢查）" if missing else result


_SKIP = object()


def review(plan, risk, factors, positions, resistance=_SKIP):
    """plan 要先經 normalize；risk、factors、positions 取不到時傳 None。回 {plan, checks, verdict}。"""
    risk = risk if isinstance(risk, dict) and not risk.get("error") else None
    factors = factors if isinstance(factors, dict) else None
    positions = positions if isinstance(positions, list) else None
    price = _num((risk or {}).get("current_price"))
    if price is None and isinstance(factors, dict):
        price = _num(factors.get("close"))
    entry = plan.get("entry") or price
    atr = (risk or {}).get("atr")
    if plan["action"] in BUY_ACTIONS:
        stop_check, stop = check_stop(plan, entry, atr)
        checks = [stop_check, check_risk(plan, entry, stop), check_size(plan, entry, risk),
                  check_average_down(plan, entry, positions), check_chase(factors)]
        if resistance is not _SKIP:
            checks.append(check_resistance(resistance))
    else:
        checks = [check_holding(plan, entry, positions)]
    return {"plan": plan, "checks": checks, "verdict": verdict(checks)}


def render(result):
    lines = [DISCLAIMER, f"我理解的計畫：{_plan_text(result['plan'])}", f"結論：{result['verdict']}"]
    lines += [f"{i}. {c['item']}：{c['status']} —— {c['detail']}" for i, c in enumerate(result["checks"], 1)]
    return "\n".join(lines)
