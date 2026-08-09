#!/usr/bin/env python3
"""
大戶籌碼 × 量價多空勢 選股台

量能比 = 觀察窗內上漲日均量 / 下跌日均量
  > 1 → 上漲有量、下跌量縮 → 多方勢
  < 1 → 上漲量縮、下跌有量 → 空方勢
"""
from collections import defaultdict
from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo import MongoClient

# 台股慣例:紅漲綠跌
BULL = "#C2302C"
BEAR = "#0C8A57"


def _f(x):
    """Decimal128 / int / float -> float"""
    if x is None:
        return None
    try:
        return float(x.to_decimal()) if hasattr(x, "to_decimal") else float(x)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=3600, show_spinner="計算量價勢中…")
def load_universe(window: int) -> tuple:
    """回傳 (DataFrame, 集保日期, 股價日期)。不套任何門檻,篩選交給前端。

    除權息以 adjustment_factors 還原:除權息日的參考價 = 前一日收盤 × factor。
    這同時修正兩件事 —— 期間報酬不再把配息記成下跌,且除息日不再被誤判為下跌日
    (那會讓量能比的分母灌進一根假的下跌量)。
    """
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

    PROJ = {"stock_id": 1, "big400_pct": 1, "big_pct": 1,
            "big_holders": 1, "total_holders": 1, "_id": 0}
    hold_date = db.shareholding.find_one(sort=[("date", -1)])["date"]
    holders = {
        r["stock_id"]: r
        for r in db.shareholding.find({"date": hold_date}, PROJ)
        # 只留 4 碼普通股,排除 ETF / 受益憑證 / 權證
        if len(r["stock_id"]) == 4 and not r["stock_id"].startswith("00")
    }

    # 回溯期:TDCC 每週一期,取離目標日最近的一期(集保沒有剛好整月的期別)
    all_dates = sorted(db.shareholding.distinct("date"))
    back, back_dates = {}, {}
    for tag, days in (("1w", 7), ("1m", 30), ("3m", 91), ("6m", 182)):
        tgt = hold_date - timedelta(days=days)
        near = min(all_dates, key=lambda d: abs((d - tgt).days))
        back_dates[tag] = near
        back[tag] = {r["stock_id"]: r for r in db.shareholding.find({"date": near}, PROJ)}

    price_date = db.stock_price.find_one(sort=[("date", -1)])["date"]
    since = price_date - timedelta(days=int(window * 1.9) + 10)

    series = defaultdict(list)
    for r in db.stock_price.find(
        {"stock_id": {"$in": list(holders)}, "date": {"$gte": since}},
        {"_id": 0, "stock_id": 1, "date": 1, "close": 1, "volume": 1, "name": 1},
    ).sort([("stock_id", 1), ("date", 1)]):
        c, v = _f(r.get("close")), _f(r.get("volume"))
        if c and v is not None:
            series[r["stock_id"]].append((r["date"], c, v, r.get("name")))

    # 觀察窗內的除權息事件:{(stock_id, ex_date): factor}
    fac = {
        (r["stock_id"], r["ex_date"]): _f(r["factor"])
        for r in db.adjustment_factors.find(
            {"stock_id": {"$in": list(holders)}, "ex_date": {"$gte": since}},
            {"_id": 0, "stock_id": 1, "ex_date": 1, "factor": 1},
        )
    }

    rows = []
    for sid, bars in series.items():
        bars = bars[-(window + 1):]
        if len(bars) < window // 2:
            continue

        up, dn, cum = [], [], 1.0
        for prev, cur in zip(bars, bars[1:]):
            # 除權息日:當日基準是參考價(前收×factor),不是前收
            base = prev[1] * fac.get((sid, cur[0]), 1.0)
            cum *= fac.get((sid, cur[0]), 1.0)
            if cur[1] > base:
                up.append(cur[2])
            elif cur[1] < base:
                dn.append(cur[2])
        if not up or not dn:
            continue  # 單邊行情,量能比無意義
        h = holders[sid]
        # 籌碼集中度:股東數變化(%)與大戶比例變化(百分點)。缺回溯資料則為 None
        chips = {}
        th_now = h.get("total_holders") or 0
        for tag in ("1w", "1m", "3m", "6m"):
            p = back[tag].get(sid)
            th_old = (p or {}).get("total_holders") or 0
            chips[f"股東數{tag}"] = (th_now / th_old - 1) * 100 if (p and th_old and th_now) else None
            for fld in ("big400_pct", "big_pct"):
                old = (p or {}).get(fld)
                cur_ = h.get(fld)
                chips[f"{fld}_{tag}"] = (cur_ - old) if (old is not None and cur_ is not None) else None

        # 全精度存放 —— 篩選必須吃原值,四捨五入只在顯示時做
        rows.append({
            "代號": sid,
            "名稱": (bars[-1][3] or "").strip(),
            "big400_pct": h.get("big400_pct") or 0.0,
            "big_pct": h.get("big_pct") or 0.0,
            "股東數": th_now,
            **chips,
            "量能比": (sum(up) / len(up)) / (sum(dn) / len(dn)),
            "收盤": bars[-1][1],
            # 後復權:把期初價乘上窗內所有 factor,配息不再被記成下跌
            "期間%": (bars[-1][1] / (bars[0][1] * cum) - 1) * 100,
            "除權息": cum < 1.0,
            "日均額(億)": sum(b[1] * b[2] for b in bars) / len(bars) / 1e8,
        })

    return pd.DataFrame(rows), hold_date, price_date, back_dates


def show():
    st.title("🧲 大戶籌碼 × 量價多空勢")
    st.markdown("以集保大戶持股搭配量價關係篩股:**上漲有量、下跌量縮**為多方勢,反之為空方勢。")

    window = st.sidebar.select_slider("量價觀察窗(交易日)", [10, 20, 40, 60], value=20)
    df, hold_date, price_date, back_dates = load_universe(window)

    if df.empty:
        st.error("查無資料 —— 請確認 shareholding / stock_price 是否有近期資料。")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("集保持股基準日", hold_date.strftime("%Y-%m-%d"))
    c2.metric("股價基準日", price_date.strftime("%Y-%m-%d"))
    c3.metric("可分析普通股", f"{len(df):,} 檔")

    # ---- 篩選條件 ----
    st.sidebar.markdown("### 篩選條件")
    field_label = st.sidebar.radio("主篩選級距(用於下限/勢別/週月比)",
                                   [">400張", ">1000張(千張)"], horizontal=True)
    field = "big400_pct" if field_label == ">400張" else "big_pct"

    hold_min = st.sidebar.slider("大戶持股下限 (%)", 0.0, 95.0, 55.0, 0.5)
    mode = st.sidebar.radio("勢別", ["多方勢", "空方勢", "全部"], horizontal=True)
    ratio = st.sidebar.slider("量能比門檻 (×)", 1.0, 3.0, 1.2, 0.05)
    amt_min = st.sidebar.slider("日均成交額下限 (億)", 0.0, 20.0, 0.1, 0.05)
    ret_min = st.sidebar.slider("期間漲跌幅下限 (%)", -40, 40, -40, 1)

    st.sidebar.markdown("### 籌碼集中度")
    st.sidebar.caption("股東數減少 + 大戶比例上升 = 籌碼集中")
    period = st.sidebar.radio("比較期間", ["不套用", "周比", "月比", "季比", "半年比"], horizontal=True)
    TAG = {"周比": "1w", "月比": "1m", "季比": "3m", "半年比": "6m"}

    m = (df[field] >= hold_min) & (df["日均額(億)"] >= amt_min) & (df["期間%"] >= ret_min)
    if mode == "多方勢":
        m &= df["量能比"] >= ratio
    elif mode == "空方勢":
        m &= df["量能比"] <= 1 / ratio

    if period != "不套用":
        tag = TAG[period]
        th_max = st.sidebar.slider(f"股東數{period}變化上限 (%)", -20.0, 20.0, 0.0, 0.5,
                                   help="設 0 表示只要股東數沒增加")
        bg_min = st.sidebar.slider(f"大戶{period}增減下限 (百分點)", -10.0, 10.0, 0.0, 0.1)
        m &= df[f"股東數{tag}"].notna() & (df[f"股東數{tag}"] <= th_max)
        m &= df[f"{field}_{tag}"].notna() & (df[f"{field}_{tag}"] >= bg_min)

    out = df[m].copy()
    out["大戶%"] = out[field]                    # 主指標:散佈圖 x 軸與排序用
    out["大戶>400張%"] = out["big400_pct"]        # 級12-15
    out["大戶>1000張%"] = out["big_pct"]          # 級15 千張大戶
    for lbl, tag in TAG.items():
        out[f"股東{lbl}"] = out[f"股東數{tag}"]
        out[f"大戶{lbl}"] = out[f"{field}_{tag}"]
    out = out.sort_values("量能比", ascending=(mode == "空方勢"))

    st.markdown("---")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("符合檔數", f"{len(out):,}")
    k2.metric("多方勢", int((out["量能比"] >= ratio).sum()))
    k3.metric("空方勢", int((out["量能比"] <= 1 / ratio).sum()))
    k4.metric("期間報酬中位數", f"{out['期間%'].median():+.1f}%" if len(out) else "—")

    if out.empty:
        st.warning("沒有符合條件的股票 —— 試著放寬大戶下限或量能比門檻。")
        return

    # ---- 散佈圖:大戶% × 量能比 ----
    fig = px.scatter(
        out, x="大戶%", y="量能比", size="日均額(億)", color="期間%",
        color_continuous_scale=[BEAR, "#9DA8B6", BULL], color_continuous_midpoint=0,
        hover_name=out["代號"] + " " + out["名稱"],
        hover_data={"收盤": True, "日均額(億)": ":.2f"},
        size_max=32, height=420,
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color="#9DA8B6",
                  annotation_text="量能比 1.0(多空分界)", annotation_position="top left")
    fig.add_vline(x=hold_min, line_dash="dot", line_color="#D9A441")
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                      coloraxis_colorbar=dict(title="期間%"))
    st.plotly_chart(fig, width='stretch')

    # ---- 明細表 ----
    delta_cols = [f"{a}{b}" for a in ("大戶", "股東") for b in TAG]
    cols = (["代號", "名稱", "大戶>400張%", "大戶>1000張%", "股東數"] + delta_cols
            + ["量能比", "收盤", "期間%", "除權息", "日均額(億)"])

    def _sign(v):
        """大戶增(紅)/減(綠);股東數欄位語意相反,由呼叫端反轉"""
        if pd.isna(v) or v == 0:
            return ""
        return f"color:{BULL}" if v > 0 else f"color:{BEAR}"

    event = st.dataframe(
        out[cols].style.map(
            lambda v: f"color:{BULL}" if v > 0 else (f"color:{BEAR}" if v < 0 else ""),
            subset=["期間%"],
        ).map(
            lambda v: f"color:{BULL}" if v >= 1 else f"color:{BEAR}", subset=["量能比"]
        ).map(_sign, subset=[f"大戶{b}" for b in TAG]
        # 股東數減少才是籌碼集中,配色反轉
        ).map(lambda v: _sign(-v) if pd.notna(v) else "", subset=[f"股東{b}" for b in TAG]
        ).format({"大戶>400張%": "{:.1f}", "大戶>1000張%": "{:.1f}", "股東數": "{:,.0f}", "量能比": "{:.2f}", "收盤": "{:.2f}",
                  "期間%": "{:+.1f}", "日均額(億)": "{:.2f}",
                  **{f"大戶{b}": "{:+.2f}" for b in TAG},
                  **{f"股東{b}": "{:+.1f}%" for b in TAG}}, na_rep="—"),
        width='stretch', hide_index=True, height=560,
        column_config={
            "大戶>400張%": st.column_config.ProgressColumn(
                "大戶>400張%", min_value=0, max_value=100, format="%.1f"),
            "大戶>1000張%": st.column_config.ProgressColumn(
                "大戶>1000張%", min_value=0, max_value=100, format="%.1f"),
            "除權息": st.column_config.CheckboxColumn(
                "除權息", help="觀察窗內有除權息,期間報酬與量能比均已還原"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key="volprice_table",
    )

    csv = out[cols].round({"大戶>400張%": 1, "大戶>1000張%": 1, "量能比": 2, "收盤": 2, "期間%": 1, "日均額(億)": 2})
    st.download_button(
        "⬇️ 下載 CSV", csv.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"holder_volprice_{price_date:%Y%m%d}.csv", mime="text/csv",
    )

    n_ex = int(out["除權息"].sum())
    st.caption(
        "籌碼集中度基準期(TDCC 每週一期,取離目標日最近的一期):"
        + " / ".join(f"{k}={back_dates[v]:%Y-%m-%d}" for k, v in TAG.items())
        + f"。大戶欄為百分點增減、股東數欄為 % 變化;**股東數減少配紅**(籌碼集中)。"
        f"回溯期涵蓋較窄,本次 {int(out[f'股東數6m'].notna().sum())}/{len(out)} 檔有半年比。"
    )
    st.caption(
        f"量能比 = 近 {window} 交易日上漲日均量 ÷ 下跌日均量;單邊行情(全漲或全跌)無法計算已排除。"
        "大戶%取自集保(TDCC)最新一期。"
        f"期間報酬與漲跌日判定均已用 `adjustment_factors` **還原除權息**"
        f"(本次結果 {n_ex} 檔窗內有除權息)—— 除息日以參考價為基準,不再被當成下跌。"
    )

    # ---- drill-down:從選股結果鑽進單股股權分散趨勢(同頁內聯)----
    st.markdown("---")
    st.markdown("### 🔍 個股股權分散趨勢")
    st.caption("**直接點上表任一列**即可帶入該檔;或用下方選單。看它的總股東人數與大股東持有率歷史走勢。")
    # drill 選單改用全市場(df,含未通過排行榜篩選者,如大戶減碼的股);排行榜(out)維持只列選股結果
    name_map = dict(zip(df["代號"], df["名稱"]))
    opts = sorted(df["代號"].tolist())
    if opts:
        # row-click drill:點主表的列 -> 帶入該檔(只在點選變動時同步,避免蓋掉手動選單)
        sel = event.selection.rows if getattr(event, "selection", None) else []
        clicked = out.iloc[sel[0]]["代號"] if sel else None
        if clicked and clicked != st.session_state.get("_last_drill_click"):
            st.session_state["_last_drill_click"] = clicked
            st.session_state["_drill_stock"] = clicked
        # 用獨立 state 驅動 selectbox 的 index(避免「設 session_state[key] 後又拿同 key 當 widget」的 Streamlit 陷阱)
        cur = st.session_state.get("_drill_stock")
        idx = opts.index(cur) if cur in opts else 0
        dsel = st.selectbox(
            "選一檔（全市場任一檔，不受排行榜篩選；或直接點上表任一列）", opts, index=idx,
            format_func=lambda s: f"{s} {name_map.get(s, '')}",
            key="drill_sel")
        st.session_state["_drill_stock"] = dsel
        from pages.holder_trend import render_trend
        render_trend(dsel, kp="drill_")
