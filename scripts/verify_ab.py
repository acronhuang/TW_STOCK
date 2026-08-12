"""獨立重驗 A/B:直接讀三個原始 JSON,不看 ab_verdict.txt。
印出每個檔的所有 annual_return(含 v2.0/v2.1)、檔案時間、以及 runner 的 dig() 會抓到哪個。"""
import json
import os
from datetime import datetime

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"


def all_annual(o, path=""):
    """遞迴列出所有 annual_return 的 (路徑, 值)。"""
    found = []
    if isinstance(o, dict):
        for kk, v in o.items():
            if kk == "annual_return":
                found.append((path, v))
            else:
                found += all_annual(v, f"{path}.{kk}")
    return found


def dig_first(o):
    """複製 runner 的 dig():回傳第一個 annual_return。"""
    if isinstance(o, dict):
        if "annual_return" in o:
            return o["annual_return"]
        for v in o.values():
            x = dig_first(v)
            if x is not None:
                return x
    return None


print("獨立重驗(直接讀原始 JSON,非 verdict):\n")
for src in ("none", "fundamental", "legacy"):
    jf = f"{ROOT}/ab_{src}.json"
    if not os.path.exists(jf):
        print(f"{src}: 檔案不存在!")
        continue
    mt = datetime.fromtimestamp(os.path.getmtime(jf)).strftime("%m-%d %H:%M:%S")
    with open(jf, encoding="utf-8") as f:
        d = json.load(f)
    ars = all_annual(d)
    first = dig_first(d)
    print(f"=== {src}  (檔案時間 {mt}) ===")
    print(f"  所有 annual_return: {[(p, round(v*100,2) if abs(v)<100 else v) for p,v in ars]}")
    print(f"  runner dig() 抓到: {round(first*100,2) if first is not None and abs(first)<100 else first}")
