"""融資融券籌碼訊號分類器(規則式,決定性)。

把判讀心法寫成程式:融資增減% × 近5日股價 × 券資比 → 一個訊號標籤。
門檻為啟發式,可調(見常數)。dashboard 與委員可共用。
"""

# 門檻(可調)
UP, DOWN = 2.0, -2.0        # 近5日股價 漲/跌 判定(%)
MJUMP = 5.0                 # 融資暴增(占餘額%)
MMOVE = 1.0                 # 融資增/減 判定(占餘額%)
RATIO_HI = 10.0            # 券資比高(%)——軋空候選(台股整體券資比僅~2%,P98≈10%,故10%已屬顯著偏高)
SCOVER = 0.05             # 融券大減(占融資餘額比例)


def margin_signal(margin_bal, mchg, schg, ratio, price_chg):
    """回 (label, emoji, tone)。tone: 'bull'|'bear'|'warn'|''。
    margin_bal/mchg/schg=張,ratio=券資比%,price_chg=近5日股價%。全防呆。"""
    if margin_bal is None or mchg is None or price_chg is None or margin_bal <= 0:
        return ("—", "", "")
    mpct = mchg / margin_bal * 100
    up = price_chg > UP
    flat = DOWN <= price_chg <= UP
    down = price_chg < DOWN

    # 優先序:先示警(斷頭)→ 最強多方訊號 → 機會 → 過熱 → 回補
    if mpct > MMOVE and down:
        return ("斷頭風險", "🔴", "bear")          # 融資增+股價跌:散戶套牢加碼,籌碼沉重
    if mpct < -MMOVE and (up or flat):
        return ("主力吃貨", "⭐", "bull")           # 融資減+股價撐/漲:散戶下車股價撐,籌碼換手
    if ratio is not None and ratio > RATIO_HI and not down:
        return ("軋空候選", "🎯", "bull")           # 券資比高+股價不跌:空單多,易軋空
    if mpct > MJUMP and up:
        return ("融資過熱", "⚠️", "warn")           # 融資暴增+股價漲:散戶追價過熱,慎追
    if schg is not None and schg < -SCOVER * margin_bal and up:
        return ("空單回補", "🟢", "bull")           # 融券大減+股價漲:回補助漲
    if mpct < -MMOVE and down:
        return ("認賠殺出", "🔵", "")               # 融資減+股價跌:散戶認賠,或打底待止穩
    return ("中性", "", "")
