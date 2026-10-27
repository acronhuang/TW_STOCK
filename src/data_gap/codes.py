import re

# 結尾帶字母的 ETF/ETN（槓桿、反向、期貨、債券、主動式），例如 00631L、00679B、00400A。
LETTER_ETF = re.compile(r"00[0-9]{3,4}[A-Z]")


def is_letter_etf(code):
    return LETTER_ETF.fullmatch(str(code).strip()) is not None


def is_price_code(code):
    """日常價格表收錄的代號：純數字代號，加上結尾帶字母的 ETF；特別股與權證字母代號不收。"""
    code = str(code).strip()
    return code.isdigit() or is_letter_etf(code)
