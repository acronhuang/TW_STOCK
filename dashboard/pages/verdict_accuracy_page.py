"""🎯 判斷準確度 —— 合議 verdict 的事後績效、分層診斷與回推。

資料來源:verdict_detail(逐筆,由 scripts/verdict_orthogonality_backtest.py 累積)
        + verdict_performance(快照,含委員偏態)。

⚠️ 讀這頁前必須知道的一件事:命中率有兩種基準,數字差很大。
   超額命中 = 該檔報酬 減去「同一分析日、分析池的橫斷面平均報酬」後仍為正。
   絕對命中 = 該檔報酬本身為正。
   空頭區間中,跌得比池均少是正確的相對判斷,但絕對命中會記成沒中。
   衡量「選股力」要看超額命中;絕對命中只是對照,兩者的差距等於期間池均漲跌。
"""
import sys
from datetime import datetime

import pandas as pd
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")

# 門檻與需求編號一律從 production 腳本取，不在此重新定義（ADR-0006）。
# 舊版在這裡寫死 0.55/0.015，與腳本各有一份 —— 兩份一旦分岔，網頁與告警會說不同的話。
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "_vob", "/home/mdsadmin/Stock/tw-stock-analysis/scripts/verdict_orthogonality_backtest.py")
_vob = _ilu.module_from_spec(_spec)
_sv = sys.argv
sys.argv = ["x"]
_spec.loader.exec_module(_vob)
sys.argv = _sv
QUAL_HIT = _vob.QUAL_HIT
excess_threshold = _vob.excess_threshold
REQ_ID = _vob.REQ_ID
TARGET_ANNUAL = _vob.TARGET_ANNUAL_EXCESS
BANDS = ["事前弱(跌最多)", "事前中", "事前強(漲最多)"]


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


@st.cache_data(ttl=900, show_spinner="讀逐筆判斷紀錄…")
def _load(window):
    rows = list(_db().verdict_detail.find(
        {"window": window},
        {"_id": 0, "symbol": 1, "date": 1, "verdict": 1, "fwd_ret": 1,
         "excess": 1, "prior_20d": 1, "mom_excluded": 1}))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=900)
def _windows():
    return sorted(_db().verdict_detail.distinct("window"))


@st.cache_data(ttl=900)
def _snapshot():
    return _db().verdict_performance.find_one({}, sort=[("ts", -1)])


@st.cache_data(ttl=900)
def _names(codes):
    out = {}
    for d in _db().taiwan_stock_info.find({"stock_id": {"$in": list(codes)}},
                                          {"stock_id": 1, "stock_name": 1}):
        out[d["stock_id"]] = d.get("stock_name")
    return out


def _stats(sub, side):
    """回 (n, 超額命中, 絕對命中, 均超額, 中位超額, 期間池均)。"""
    n = len(sub)
    if not n:
        return None
    up = (lambda s: s > 0) if side == "買進" else (lambda s: s < 0)
    return {
        "n": n,
        "hit": up(sub["excess"]).mean(),
        "hit_abs": up(sub["fwd_ret"]).mean(),
        "mean_ex": sub["excess"].mean(),
        "med_ex": sub["excess"].median(),
        "bench": (sub["fwd_ret"] - sub["excess"]).mean(),
    }


def _fmt(s):
    return (f"N={s['n']}　超額命中 **{s['hit']*100:.1f}%**　均超額 **{s['mean_ex']*100:+.2f}%**"
            f"　中位 {s['med_ex']*100:+.2f}%　｜對照 絕對命中 {s['hit_abs']*100:.1f}%"
            f"（期間池均 {s['bench']*100:+.2f}%）")


def show():
    st.header("🎯 判斷準確度")
    st.caption("合議 verdict 的事後績效。基準=同一分析日、分析池的橫斷面平均報酬"
               "（市場 beta 構造性移除，衡量的是選股力而非擇時力）。")

    wins = _windows()
    if not wins:
        st.warning("verdict_detail 尚無資料。請先執行："
                   "`python3 scripts/verdict_orthogonality_backtest.py --windows 5,10,20`")
        return

    c1, c2 = st.columns([1, 3])
    window = c1.selectbox("前瞻視窗（交易日）", wins,
                          index=wins.index(20) if 20 in wins else len(wins) - 1)
    df = _load(window)
    if df.empty:
        st.warning("此視窗無資料")
        return

    dmin, dmax = df["date"].min(), df["date"].max()
    ndays = df["date"].nunique()
    c2.info(f"樣本 {len(df):,} 筆　分析日 **{ndays}** 天"
            f"（{dmin:%Y-%m-%d} ~ {dmax:%Y-%m-%d}）\n\n"
            f"⚠️ 同一天多檔在重疊視窗內高度相關，**有效自由度接近分析日數而非樣本數**，"
            f"不要拿 {len(df):,} 去算 t 值。")

    # ── 回推開關:套用反動能過濾會怎樣 ────────────────────────────────
    st.markdown("### 回推：套用反動能過濾")
    st.caption("依據：買進判斷力隨事前 20 日動能單調遞減，動能最高的那一批買進反而虧損。"
               "此過濾已套用在 core_pool 的選股漏斗（`CORE_POOL_MOM_FILTER_PCT`）。"
               "⚠️ 此為 in-sample 切片，尚未樣本外驗證，這裡讓你自己看它在各視窗是否站得住。")
    apply_f = st.toggle("排除事前動能最高的買進", value=False,
                        help="mom_excluded=True 的買進會被排除；賣出不受影響")

    view = df.copy()
    n_ex = 0
    if apply_f:
        mask = (view["verdict"] == "買進") & (view["mom_excluded"] == True)  # noqa: E712
        n_ex = int(mask.sum())
        view = view[~mask]
        st.caption(f"已排除 {n_ex} 筆買進判斷（不靜默截斷：這個數字就是被拿掉的量）")

    # ── 主結果 ──────────────────────────────────────────────────────
    st.markdown("### 整體")
    buy = _stats(view[view["verdict"] == "買進"], "買進")
    sell = _stats(view[view["verdict"] == "賣出"], "賣出")
    if buy:
        st.markdown(f"**買進**　{_fmt(buy)}")
    if sell:
        st.markdown(f"**賣出**　{_fmt(sell)}")

    if buy and buy["n"] >= 30:
        thr = excess_threshold(window)
        req = REQ_ID.get(window)
        ok = buy["hit"] >= QUAL_HIT and buy["mean_ex"] >= thr
        label = req or f"前瞻 {window} 日（無需求編號，僅參考）"
        (st.success if ok else st.error)(
            f"{label}（買進 超額命中 ≥{QUAL_HIT*100:.0f}% 且 均超額 ≥{thr*100:.2f}%）："
            f"{'✅ 達標' if ok else '🔴 未達標'}")
        st.caption(f"均超額門檻由目標年化超額 {TARGET_ANNUAL*100:.0f}% 反推："
                   f"5 日 {excess_threshold(5)*100:.2f}%、20 日 {excess_threshold(20)*100:.2f}%。"
                   f"同一個數字在不同視窗代表的年化幅度差一個數量級，故不共用（ADR-0008）。")

    # ── 事前動能分層:把判斷力與均值回歸分開 ──────────────────────────
    st.markdown("### 事前動能分層")
    st.caption("為什麼要分層：若買進組本來就挑漲多的、賣出組挑跌多的，"
               "光是均值回歸就能讓兩組報酬拉開，看起來像有（或沒有）判斷力。"
               "**在同一動能區間內比較**才是真正的判斷力。")
    wp = view[view["prior_20d"].notna()].copy()
    if len(wp) >= 30:
        wp["band"] = pd.qcut(wp["prior_20d"], 3, labels=BANDS)
        recs = []
        for b in BANDS:
            g = wp[wp["band"] == b]
            bb, ss = g[g["verdict"] == "買進"], g[g["verdict"] == "賣出"]
            recs.append({
                "動能區間": b,
                "買進N": len(bb), "買進超額命中": f"{bb['excess'].gt(0).mean()*100:.1f}%" if len(bb) else "-",
                "買進均超額": f"{bb['excess'].mean()*100:+.2f}%" if len(bb) else "-",
                "賣出N": len(ss),
                "賣出均超額": f"{ss['excess'].mean()*100:+.2f}%" if len(ss) else "-",
                "買-賣價差": (f"{(bb['excess'].mean()-ss['excess'].mean())*100:+.2f} pp"
                           if len(bb) and len(ss) else "-"),
            })
        st.dataframe(pd.DataFrame(recs), hide_index=True, width='stretch')
        gap = None
        b_, s_ = wp[wp["verdict"] == "買進"], wp[wp["verdict"] == "賣出"]
        if len(b_) and len(s_):
            gap = (b_["prior_20d"].mean() - s_["prior_20d"].mean()) * 100
            st.caption(f"買進組與賣出組的事前動能差 = **{gap:+.2f} pp**"
                       + ("　⚠️ 兩組體質差異大，整體價差混入均值回歸，請以分層結果為準"
                          if abs(gap) > 3 else "　（差距小，整體價差可直接解讀）"))
    else:
        st.info("有事前動能的樣本不足 30 筆，不分層")

    # ── 逐分析日走勢 ────────────────────────────────────────────────
    st.markdown("### 逐分析日走勢")
    st.caption("每個點是一個分析日。單日樣本少時噪音大，看趨勢不看單點。")
    bd = view[view["verdict"] == "買進"]
    if len(bd):
        daily = bd.groupby(bd["date"].dt.date).agg(
            買進檔數=("excess", "size"),
            超額命中=("excess", lambda s: (s > 0).mean() * 100),
            均超額=("excess", lambda s: s.mean() * 100)).reset_index()
        daily.columns = ["分析日", "買進檔數", "超額命中%", "均超額%"]
        st.line_chart(daily.set_index("分析日")[["超額命中%", "均超額%"]])
        with st.expander("逐日數字"):
            st.dataframe(daily.round(2), hide_index=True, width='stretch')

    # ── 逐筆明細 ────────────────────────────────────────────────────
    st.markdown("### 逐筆明細")
    f1, f2 = st.columns([1, 2])
    vsel = f1.multiselect("評級", sorted(view["verdict"].unique()), default=["買進"])
    only_miss = f2.checkbox("只看判斷失準的（超額方向相反）", value=False)
    det = view[view["verdict"].isin(vsel)] if vsel else view
    if only_miss and len(det):
        det = det[((det["verdict"] == "買進") & (det["excess"] <= 0)) |
                  ((det["verdict"] == "賣出") & (det["excess"] >= 0))]
    if len(det):
        nm = _names(tuple(sorted(det["symbol"].unique())))
        out = det.assign(
            名稱=det["symbol"].map(nm),
            分析日=det["date"].dt.strftime("%Y-%m-%d"),
            報酬=(det["fwd_ret"] * 100).round(2),
            超額=(det["excess"] * 100).round(2),
            事前20日=(det["prior_20d"] * 100).round(2),
        ).sort_values("超額", ascending=False)
        st.dataframe(
            out[["分析日", "symbol", "名稱", "verdict", "報酬", "超額", "事前20日", "mom_excluded"]]
            .rename(columns={"symbol": "代號", "verdict": "評級", "報酬": "報酬%",
                             "超額": "超額%", "事前20日": "事前20日%",
                             "mom_excluded": "反動能過濾排除"}),
            hide_index=True, width='stretch', height=420)
        st.download_button("下載 CSV", out.to_csv(index=False).encode("utf-8-sig"),
                           f"verdict_detail_w{window}.csv", "text/csv")

    # ── 委員偏態 ────────────────────────────────────────────────────
    st.markdown("### 委員票種偏態")
    st.caption("單一票種佔比 >75% 的委員等於「恆說同一句話」，出席但不提供資訊。"
               "本專案曾有 hermes3:8b 出席 8,913 次、84.7% 都投買進而長期無人察覺，"
               "直到 2026-08-06 才被 gemma2:9b 取代。"
               "**只有現任委員會觸發告警**——已退役者的歷史無法再改變，列出僅供追溯。")
    snap = _snapshot()
    cm = (snap or {}).get("committee") or {}
    if cm.get("bias"):
        rows = []
        for m, b in sorted(cm["bias"].items(),
                           key=lambda x: (not x[1].get("active"), -(x[1].get("seats") or 0))):
            top = max(b.get("buy%", 0), b.get("hold%", 0), b.get("sell%", 0))
            act = b.get("active")
            rows.append({"模型": m, "在職": "現任" if act else "已退役",
                         "任期迄": str(b.get("last_seen"))[:10],
                         "出席": b.get("seats"), "買進%": b.get("buy%"),
                         "持有%": b.get("hold%"), "賣出%": b.get("sell%"),
                         "棄權%": b.get("null%"),
                         "狀態": ("🔴 退化" if top > 75 else "✅") if act
                                 else ("⚪ 已退役(當年退化)" if top > 75 else "⚪ 已退役")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        if cm.get("drift"):
            d = cm["drift"]
            st.info(f"ⓘ 設定檔與實際投票名單不一致 —— "
                    f"設定有但沒在投：`{d.get('設定有但沒在投') or '—'}`；"
                    f"在投但設定沒有：`{d.get('在投但設定沒有') or '—'}`。"
                    f"剛改設定尚未跑到屬正常；若持續多輪不收斂，代表設定沒生效。")
        mp = cm.get("max_corr_pair")
        if mp:
            st.caption(f"最高相關委員對：**{mp['a']} × {mp['b']}**　"
                       f"同票 {mp['agree']*100:.1f}%　corr {mp['corr']:+.2f}"
                       + ("　⚠️ 兩位委員高度重疊，合議實際上少一個獨立意見"
                          if (mp.get("corr") or 0) > 0.7 else ""))
        for x in (cm.get("degenerate") or []):
            st.error(f"🔴 {x['model']}：{x['reason']} {x['value']*100:.1f}% > 上限 {x['limit']*100:.0f}%")
        red = cm.get("redundant") or []
        for p in red:
            st.error(f"🔴 冗餘委員對 **{p['a']} × {p['b']}**：同票 {p['agree']*100:.1f}%"
                     f"（上限 {p['limit']*100:.0f}%）corr {p['corr']:+.2f} —— "
                     f"三人合議實際上只有兩個獨立意見")
        if red:
            st.caption("⚠️ 冗餘與模型家族無關：2026-08-15 實測 gemma2:9b × qwen2.5:7b "
                       "雖是不同家族，同票率仍達 86.7%、corr +0.91，比換血前的 qwen 手足對更高。"
                       "換家族不保證拿到多樣性，只能換完後實測同票率。")
    else:
        st.info("尚無 verdict_performance 快照（跑一次 SLI 不加 --dry-run 即可產生）")

    if snap and snap.get("ts"):
        st.caption(f"快照時間：{snap['ts']:%Y-%m-%d %H:%M}")
