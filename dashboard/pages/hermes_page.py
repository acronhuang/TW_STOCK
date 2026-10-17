"""Hermes 唯讀助理頁：把問題交給 hq（本機模型加唯讀工具加數字核對外掛），顯示回答。"""

import shutil
import subprocess
import threading
import time
from pathlib import Path

MAX_QUESTION = 500
TIMEOUT_SECONDS = 150
_busy = threading.Lock()  # 一次只處理一題：頁面對區網開放，不能讓多人同時把模型與正式 API 拖慢


def hq_path():
    return shutil.which("hq") or str(Path.home() / ".local" / "bin" / "hq")


def ask(question, run=subprocess.run, hq=None):
    """回 (文字, 是否失敗)。問題以單一參數交給 hq，不經 shell。"""
    question = (question or "").strip()
    if not question:
        return "請先輸入問題。", True
    if len(question) > MAX_QUESTION:
        return f"問題太長（上限 {MAX_QUESTION} 字）。", True
    if not _busy.acquire(blocking=False):
        return "助理正在處理另一個問題，請稍後再試。", True
    try:
        done = run([hq or hq_path(), question], capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"超過 {TIMEOUT_SECONDS} 秒沒有回應（全市場掃描這類重查詢可能較慢）。", True
    except OSError as error:
        return f"無法啟動助理：{error}", True
    finally:
        _busy.release()
    text = (done.stdout or "").strip()
    if done.returncode != 0 or not text:
        detail = (done.stderr or "").strip()[-200:]
        return "助理沒有回答" + (f"：{detail}" if detail else "。"), True
    return text, False


def show():
    import streamlit as st

    st.subheader("🤖 Hermes 助理（唯讀）")
    st.caption("只能查詢，不能下單或修改資料；回答由本機模型產生，外掛會核對數字出處。"
               "全市場掃描、選股排行這類重查詢要 20 秒以上。")
    question = st.text_area("問題", max_chars=MAX_QUESTION, placeholder="例：2330 的公平價是多少？我的持倉有哪些？")
    if st.button("詢問", type="primary"):
        started = time.time()
        with st.spinner("Hermes 作答中（通常 15~30 秒）…"):
            text, failed = ask(question)
        if failed:
            st.warning(text)
        else:
            st.markdown(text)
            st.caption(f"耗時 {time.time() - started:.0f} 秒")
