#!/usr/bin/env python3
"""每個交易日盤後，請 Hermes 對自選清單逐檔整理估值與法人買賣超，寫成當日摘要檔。

只讀：Hermes 走已部署的唯讀工具與守衛外掛；這裡不連資料庫、不推播，只寫 logs/hermes_digest/。
自選清單在 ~/.hermes/watchlist.txt，每行一個代號，# 開頭為註解。
"""
import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "logs" / "hermes_digest"
HERMES = Path.home() / ".local" / "bin" / "hermes"
WORKDIR = Path.home() / "hermes_work"  # 中性目錄，避免 Hermes 吃進專案的 CLAUDE.md
WATCHLIST = Path.home() / ".hermes" / "watchlist.txt"
SYMBOL = re.compile(r"[0-9A-Za-z]{4,8}")
MAX_SYMBOLS = 20
CALL_TIMEOUT = 240
TOTAL_BUDGET = 1200
FLAG = "⚠️"


def read_watchlist(text):
    """每行一個代號；空行、# 註解與格式不對的行略過，重複只留第一次，最多 MAX_SYMBOLS 檔。"""
    symbols = []
    for line in (text or "").splitlines():
        code = line.split("#", 1)[0].strip()
        if SYMBOL.fullmatch(code) and code not in symbols:
            symbols.append(code)
    return symbols[:MAX_SYMBOLS]


def build_question(symbol):
    return f"{symbol} 的估值（DCF、本益比區間）判定與最新一天三大法人買賣超是幾張？只列資料中的數字與判定，不要建議；欄位一律用中文名稱，不要寫英文欄位名。"


def ask_hermes(question, timeout=CALL_TIMEOUT):
    """回 (答案文字, 錯誤訊息)；Hermes 逾時、非零結束或沒有輸出都算錯誤。"""
    env = {**os.environ, "PATH": f"{HERMES.parent}:{os.environ.get('PATH', '')}"}
    try:
        done = subprocess.run(
            [str(HERMES), "-z", question], cwd=WORKDIR, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except subprocess.TimeoutExpired:
        return "", f"逾時（{timeout} 秒）"
    except OSError as error:
        return "", f"無法執行 Hermes：{error}"
    text = done.stdout.strip()
    if done.returncode != 0:
        return "", f"Hermes 結束碼 {done.returncode}：{done.stderr.strip()[-200:]}"
    return (text, "") if text else ("", "Hermes 沒有輸出")


def collect(symbols, ask, budget=TOTAL_BUDGET, clock=time.monotonic):
    """依序詢問；超過時間預算的剩餘代號標為未執行。回 [{symbol, answer, error}]。"""
    deadline = clock() + budget
    results = []
    for symbol in symbols:
        if clock() > deadline:
            results.append({"symbol": symbol, "answer": "", "error": "未執行（超過時間預算）"})
            continue
        answer, error = ask(build_question(symbol))
        results.append({"symbol": symbol, "answer": answer, "error": error})
    return results


def render_digest(stamp, results):
    failed = [r for r in results if r["error"]]
    flagged = [r for r in results if not r["error"] and FLAG in r["answer"]]
    lines = [
        f"# Hermes 盤後摘要 {stamp}",
        "",
        f"共 {len(results)} 檔；失敗 {len(failed)} 檔；回答附提醒 {len(flagged)} 檔。"
        "回答由小模型整理，數字與單位請對照分析頁面；附 ⚠️ 的請特別核對。",
    ]
    for r in results:
        lines += ["", f"## {r['symbol']}", ""]
        lines.append(f"【失敗】{r['error']}" if r["error"] else r["answer"])
    return "\n".join(lines) + "\n"


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None, ask=ask_hermes, now=datetime.now):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--watchlist", type=Path, default=WATCHLIST)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    try:
        symbols = read_watchlist(args.watchlist.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"讀不到自選清單 {args.watchlist}：{error}", file=sys.stderr)
        return 2
    if not symbols:
        print(f"自選清單是空的：{args.watchlist}", file=sys.stderr)
        return 2
    moment = now()
    results = collect(symbols, ask)
    path = args.out_dir / f"digest_{moment:%Y%m%d}.md"
    write_atomic(path, render_digest(f"{moment:%Y-%m-%d %H:%M}", results))
    failed = [r["symbol"] for r in results if r["error"]]
    print(f"已寫入 {path}；{len(results)} 檔，失敗 {len(failed)} 檔" + (f"：{','.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
