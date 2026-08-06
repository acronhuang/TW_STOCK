"""2560戰法(安德烈·布殊,4次世界交易冠軍)訊號。

價:25日均價線(MA25)堅決向上 + K線踩25日線起動(回踩不破)。
量:5日均量 vs 60日均量 → 四情境:
  ❌誘惑  5均量<60均量(無量硬拉)→ 放棄
  🟡衝量  踩線起動+5均量剛上穿60均量 → 短線,形態未穩
  ✅做量  踩線起動+5均量已站上60均量一段 → 波段,形態已成
  🎯縮量  5均量早在60均量上運行+近1-2日縮量(坑量)→ 牛股黑馬

純計算,dashboard 與 MoE 技術委員共用。用還原價+成交量。
"""


def _mean(a):
    return sum(a) / len(a) if a else None


def classify_2560(closes, vols, near=0.06):
    """回 dict(setup/scenario/label/emoji/tone/ma25/dist%/量比…)或 None(資料不足)。"""
    if closes is None or vols is None or len(closes) < 65 or len(vols) < 65:
        return None
    close = closes[-1]
    ma25 = _mean(closes[-25:])
    ma25_5ago = _mean(closes[-30:-5])
    vol60 = _mean(vols[-60:])
    if not ma25 or not ma25_5ago or not vol60:
        return None

    ma25_rising = ma25 > ma25_5ago
    dist = close / ma25 - 1
    touched = min(closes[-5:]) <= ma25 * 1.03           # 近5日曾回踩25線
    setup = ma25_rising and close >= ma25 * 0.99 and dist <= near and touched

    vol5 = _mean(vols[-5:])
    vol5_prev = _mean(vols[-10:-5])
    r = vol5 / vol60 if vol60 else 0.0
    prior_strong = (_mean(vols[-15:-3]) or 0) > vol60   # 前段量能在均量之上
    recent_low = vols[-1] <= min(vols[-15:-1]) * 1.25 or (_mean(vols[-2:]) or 0) <= vol60 * 0.9

    if not setup:
        return {"setup": False, "scenario": "", "label": "不符合(未踩25線起動或MA25未向上)",
                "emoji": "", "tone": "", "ma25": round(ma25, 2), "dist%": round(dist * 100, 1),
                "ma25_rising": ma25_rising, "vol5_60": round(r, 2), "close": round(close, 2)}
    if prior_strong and recent_low and r < 1.4:
        scen, emo, tone, lab = "縮量", "🎯", "bull", "縮量·牛股黑馬(洗盤坑量)"
    elif r >= 1.0 and vol5_prev >= vol60:
        scen, emo, tone, lab = "做量", "✅", "bull", "做量·波段機會(形態已成)"
    elif r >= 1.0 and vol5_prev < vol60:
        scen, emo, tone, lab = "衝量", "🟡", "warn", "衝量·短線機會(形態未穩)"
    else:
        scen, emo, tone, lab = "誘惑", "❌", "bear", "誘惑·無量放棄(5均量<60均量)"
    return {"setup": True, "scenario": scen, "label": lab, "emoji": emo, "tone": tone,
            "ma25": round(ma25, 2), "dist%": round(dist * 100, 1), "ma25_rising": ma25_rising,
            "vol5_60": round(r, 2), "close": round(close, 2)}
