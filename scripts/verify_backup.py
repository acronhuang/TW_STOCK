#!/usr/bin/env python3
"""
備份可還原性驗證（P3 · 治本）。
週備份 mongodump 若不能還原，等於沒備份。本腳本：取最新備份 → 還原到暫存 DB →
比對關鍵表筆數是否合理 → 刪暫存。驗證「備份真的能救回來」。

用法:
  verify_backup.py            驗證最新備份
  verify_backup.py --file X   驗證指定 .tar.gz
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

from pymongo import MongoClient

BACKUP_DIR = os.path.expanduser("~/Stock/mongodb_backups")
LIVE_DB = "tw_stock_analysis"
SCRATCH_DB = "tw_stock_analysis_restore_test"
# 關鍵表：還原後這些至少要有合理筆數（vs live 比例）
KEY_COLLECTIONS = ["stock_price", "stock_factors", "quarterly_earnings",
                   "institutional_flow", "taiwan_stock_info"]
MIN_RATIO = 0.80  # 還原筆數 ≥ live 的 80%（備份較舊，容許差異）


def _line(msg):
    try:
        sys.path.insert(0, os.path.expanduser("~/Stock/tw-stock-analysis"))
        from src.alerts.line_notifier import LineNotifier
        n = LineNotifier()
        if n.enabled:
            n.send(f"💾 {datetime.now():%Y-%m-%d %H:%M} 備份驗證\n{msg}")
    except Exception as e:
        print("LINE 發送失敗:", e)


def _find_dump_dir(root):
    """在解開的目錄樹中找含 *.bson / *.bson.gz 的 DB 目錄。"""
    for dirpath, _, files in os.walk(root):
        if any(f.endswith(".bson") or f.endswith(".bson.gz") for f in files):
            return dirpath
    return None


def main():
    ap = argparse.ArgumentParser(description="備份可還原性驗證")
    ap.add_argument("--file", help="指定 .tar.gz（預設取最新）")
    args = ap.parse_args()

    backup = args.file or (sorted(glob.glob(f"{BACKUP_DIR}/*.tar.gz")) or [None])[-1]
    if not backup or not os.path.exists(backup):
        print("❌ 找不到備份檔"); _line("❌ 找不到備份檔，無法驗證"); sys.exit(1)
    print(f"驗證備份: {backup}")
    print(f"  檔案時間: {datetime.fromtimestamp(os.path.getmtime(backup)):%F %T}  大小: {os.path.getsize(backup)//1024//1024} MB")

    client = MongoClient("mongodb://localhost:27017")
    tmp = tempfile.mkdtemp(prefix="verify_restore_")
    ok = True
    try:
        # 1) 解開
        print("── 解開備份 ──")
        subprocess.run(["tar", "-xzf", backup, "-C", tmp], check=True, timeout=600)
        dump_dir = _find_dump_dir(tmp)
        if not dump_dir:
            print("❌ 解開後找不到 .bson"); _line("❌ 備份解開後找不到 dump，備份可能損壞"); sys.exit(1)

        # 2) 還原到暫存 DB
        print(f"── 還原到 {SCRATCH_DB} ──")
        client.drop_database(SCRATCH_DB)
        gz = any(f.endswith(".bson.gz") for f in os.listdir(dump_dir))
        # 用 --db 直接把該目錄的 collection bson 還原進暫存 DB（比 nsFrom/nsTo 對散裝 bson 目錄可靠）
        cmd = ["mongorestore", "--drop", "--db", SCRATCH_DB, "--quiet", dump_dir]
        if gz:
            cmd.insert(1, "--gzip")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            print("❌ mongorestore 失敗:", r.stderr[-300:])
            _line("❌ 備份還原失敗（mongorestore 錯誤），備份不可用"); sys.exit(1)

        # 3) 比對關鍵表筆數
        print("── 比對筆數（還原 vs 現行）──")
        live = client[LIVE_DB]
        restored = client[SCRATCH_DB]
        rows = []
        for c in KEY_COLLECTIONS:
            n_live = live[c].estimated_document_count()
            n_rest = restored[c].estimated_document_count()
            ratio = (n_rest / n_live) if n_live else (1 if n_rest else 0)
            status = "✅" if ratio >= MIN_RATIO else "❌"
            if ratio < MIN_RATIO:
                ok = False
            rows.append(f"  {status} {c:22} 還原 {n_rest:>9,} / 現行 {n_live:>9,}  ({ratio*100:.0f}%)")
        print("\n".join(rows))

    finally:
        # 4) 清理
        client.drop_database(SCRATCH_DB)
        shutil.rmtree(tmp, ignore_errors=True)
        print("── 已清理暫存 DB 與檔案 ──")

    if ok:
        print("\n✅ 備份可正常還原，關鍵表筆數合理")
        _line(f"✅ 備份驗證通過\n{os.path.basename(backup)}\n關鍵表還原筆數正常")
    else:
        print("\n❌ 備份還原後筆數異常，備份可能不完整")
        _line(f"❌ 備份驗證失敗：還原後關鍵表筆數不足\n{os.path.basename(backup)}\n" + "\n".join(rows))
        sys.exit(1)


if __name__ == "__main__":
    main()
