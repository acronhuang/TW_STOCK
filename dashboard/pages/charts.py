"""
K線圖與技術指標頁面
"""
import streamlit as st
from pymongo import MongoClient
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# 日線→週線沿用既有轉換器（W-FRI 週五收盤），不另寫一份重採樣
from pattern_recognition.timeframe_converter import TimeframeConverter


def load_holders(db, symbol, start_date, end_date):
    """大戶持股（shareholding，每週一筆）：回傳含 date/big_pct/big400_pct/total_holders 的 DataFrame。

    資料本質為「週」快照 —— 集保與 norway 皆無每日版本，故日線圖上只能是離散的
    週點（畫成帶點的折線，不做日內插值以免暗示有每日資料）。
    2023-03 以前無資料（norway 歷史起點）。

    total_holders（總股東人數）與 big_pct 天生反向：人數增加＝籌碼分散到散戶手上。
    它是三年歷史上唯一可得的散戶動向代理（retail_pct 僅 TDCC 起算後才有）。
    """
    cur = db.shareholding.find(
        {'stock_id': symbol, 'date': {'$gte': start_date, '$lte': end_date}},
        {'_id': 0, 'date': 1, 'big_pct': 1, 'big400_pct': 1, 'total_holders': 1}
    ).sort('date', 1)
    rows = [d for d in cur if d.get('big_pct') is not None]
    if not rows:
        return pd.DataFrame()
    hdf = pd.DataFrame(rows)
    hdf['date'] = pd.to_datetime(hdf['date'])
    return hdf


def calculate_ma(df, window):
    """計算移動平均線"""
    return df['close'].rolling(window=window).mean()


def calculate_rsi(df, period=14):
    """計算 RSI"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(df, fast=12, slow=26, signal=9):
    """計算 MACD"""
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    
    return macd, macd_signal, macd_hist


def calculate_bollinger_bands(df, window=20, num_std=2):
    """計算布林通道"""
    ma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()
    
    upper = ma + (std * num_std)
    lower = ma - (std * num_std)
    
    return upper, ma, lower


def show():
    st.title("📊 K線圖與技術指標")
    
    # 連接 MongoDB
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        db = client['tw_stock_analysis']
        
        # 選單只列「有股價的上市櫃個股」(taiwan_stock_info∩stock_price，~2400 檔)，
        # 避免直接用 stock_price.distinct('symbol') 把 1.5 萬筆權證/ETF 塞進下拉選單而卡死。
        priced = set(s for s in db.stock_price.distinct('symbol') if s)
        name_map = {d['stock_id']: d.get('stock_name', '')
                    for d in db.taiwan_stock_info.find({}, {'stock_id': 1, 'stock_name': 1})}
        symbols = sorted(sid for sid in name_map if sid in priced)
        if not symbols:                       # 後備：資訊表為空時退回原全清單
            symbols = sorted(priced)

        if not symbols:
            st.warning("⚠️ 沒有股票數據")
            return

        # 側邊欄參數設置
        st.sidebar.markdown("### 📊 圖表參數")
        st.sidebar.caption("🆕 選股 v2（輸入代碼按 Enter）")

        # 股票選擇：直接輸入代碼（避免上千筆下拉選單在瀏覽器卡死；可輸入代碼或名稱關鍵字）
        query = st.sidebar.text_input(
            "股票代碼 / 名稱",
            value='2330',
            help="輸入代碼(如 2330)或名稱關鍵字(如 台積)；下方可挑選符合的結果"
        ).strip()

        # 解析輸入 → 候選清單
        if query in priced:
            selected_symbol = query
        else:
            matches = [s for s in symbols
                       if query and (query in s or query in name_map.get(s, ''))][:50]
            if not matches:
                st.sidebar.warning(f"查無「{query}」對應的股票")
                st.info(f"⚠️ 找不到「{query}」，請輸入正確的股票代碼或名稱")
                return
            if len(matches) == 1:
                selected_symbol = matches[0]
            else:
                selected_symbol = st.sidebar.selectbox(
                    f"符合的股票（{len(matches)} 筆）",
                    options=matches,
                    format_func=lambda s: f"{s} {name_map.get(s, '')}".strip()
                )
        st.sidebar.caption(f"目前：**{selected_symbol} {name_map.get(selected_symbol, '')}**")
        
        # 日期範圍選擇
        date_range = st.sidebar.selectbox(
            "時間範圍",
            options=['1個月', '3個月', '6個月', '1年', '3年', '5年', '自定義'],
            index=3  # 默認 1 年
        )
        
        # 計算日期範圍
        end_date = datetime.now()
        if date_range == '1個月':
            start_date = end_date - timedelta(days=30)
        elif date_range == '3個月':
            start_date = end_date - timedelta(days=90)
        elif date_range == '6個月':
            start_date = end_date - timedelta(days=180)
        elif date_range == '1年':
            start_date = end_date - timedelta(days=365)
        elif date_range == '3年':
            start_date = end_date - timedelta(days=1095)
        elif date_range == '5年':
            start_date = end_date - timedelta(days=1825)
        else:  # 自定義
            col1, col2 = st.sidebar.columns(2)
            with col1:
                start_date = st.date_input("開始日期", value=end_date - timedelta(days=365))
            with col2:
                end_date = st.date_input("結束日期", value=end_date)
            start_date = datetime.combine(start_date, datetime.min.time())
            end_date = datetime.combine(end_date, datetime.min.time())
        
        # K線週期：週/月線由日線重採樣（W-FRI / 月底），指標一併改以該週期計算
        timeframe_label = st.sidebar.radio(
            "K線週期", options=['日線', '週線', '月線'], index=0, horizontal=True,
            help="週線＝重採樣至週五收盤，月線＝月底收盤；所有技術指標將改用該週期計算"
        )
        TF = {'日線': ('D', '日'), '週線': ('W', '週'), '月線': ('M', '月')}
        tf_code, unit = TF[timeframe_label]
        needs_resample = tf_code != 'D'

        # 技術指標選擇
        st.sidebar.markdown("### 📈 技術指標")
        show_ma = st.sidebar.checkbox("移動平均線 (MA)", value=True)
        if show_ma:
            ma_windows = st.sidebar.multiselect(
                f"MA 週期（單位：{unit}）",
                options=[5, 10, 20, 30, 60, 120, 240],
                default=[5, 20, 60]
            )
            if needs_resample:
                st.sidebar.caption(f"⚠️ {timeframe_label}下 MA5 ＝ 5 **{unit}**，非 5 日")

        show_bb = st.sidebar.checkbox("布林通道 (Bollinger Bands)", value=False)
        show_volume = st.sidebar.checkbox("成交量", value=True)
        show_holders = st.sidebar.checkbox("大戶持股 (千張大戶%)", value=False,
                                           help="集保股權分散表，每週一筆；2023-03 起")
        show_rsi = st.sidebar.checkbox("相對強弱指標 (RSI)", value=True)
        show_macd = st.sidebar.checkbox("MACD", value=False)
        
        # 查詢數據
        st.info(f"📊 載入 **{selected_symbol}** 數據中...")
        
        query = {
            'symbol': selected_symbol,
            'date': {'$gte': start_date, '$lte': end_date}
        }
        
        cursor = db.stock_price.find(query).sort('date', 1)
        data = list(cursor)
        
        if not data:
            st.warning(f"⚠️ 沒有 {selected_symbol} 在指定時間範圍的數據")
            return
        
        # 轉換為 DataFrame
        df = pd.DataFrame(data)
        
        # 確保 date 欄位是 datetime 類型
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # 轉換 Decimal128 為 float
        from bson import Decimal128
        
        def safe_float(x):
            """安全地轉換為 float"""
            if x is None:
                return None
            if isinstance(x, Decimal128):
                return float(x.to_decimal())
            try:
                return float(x)
            except (ValueError, TypeError):
                return None
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(safe_float)

        # 週/月線重採樣（必須在 Decimal128→float 之後：resample 的 max/sum 無法運算 Decimal128）
        if needs_resample:
            df = TimeframeConverter().convert_timeframe(df, tf_code)
            if df.empty or len(df) < 2:
                st.warning(f"⚠️ {selected_symbol} 在此範圍內的{timeframe_label}資料不足"
                           f"（僅 {len(df)} 根），請拉長時間範圍")
                return

        # 顯示基本資訊
        col1, col2, col3, col4, col5 = st.columns(5)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2] if len(df) > 1 else latest
        
        price_change = latest['close'] - previous['close']
        price_change_pct = (price_change / previous['close']) * 100
        
        with col1:
            st.metric(
                "最新收盤價",
                f"${latest['close']:.2f}",
                f"{price_change:+.2f} ({price_change_pct:+.2f}%)"
            )
        
        with col2:
            st.metric("最高價", f"${latest['high']:.2f}")
        
        with col3:
            st.metric("最低價", f"${latest['low']:.2f}")
        
        with col4:
            st.metric("成交量", f"{int(latest['volume']):,}")
        
        with col5:
            # 本益比在 stock_factors，不在 stock_price；取該股最新一筆因子
            _sf = db.stock_factors.find_one(
                {'symbol': selected_symbol, 'pe_ratio': {'$ne': None}},
                {'pe_ratio': 1}, sort=[('date', -1)])
            _pe = safe_float(_sf.get('pe_ratio')) if _sf else None
            st.metric("本益比", f"{_pe:.2f}" if _pe else "-")
        
        # 週/月線時 MA5 意為 5 週/5 月，標籤須隨之改變（圖例與下方數值表共用同一組標籤）
        def ma_label(w):
            return f'MA{w}{unit}' if needs_resample else f'MA{w}'

        # 大戶持股：先取資料，沒有就不佔一列子圖（避免畫出空白格）
        hdf = load_holders(db, selected_symbol, start_date, end_date) if show_holders else pd.DataFrame()
        # 月線時把週快照抽稀成「每月最後一筆」。
        # 注意這是抽稀不是聚合：大戶佔比是「時點存量」，取月底那筆才有意義，取月平均沒有。
        # 且刻意用 groupby+idxmax 而非 resample('ME')：後者會把索引重貼成月底，
        # 使 07-09 的快照被標成 07-31（未來日期、集保根本沒這天的資料）→ hover 謊報資料日。
        # 這裡保留每筆的真實集保資料日，寧可與月 K 棒略微錯開，也不偽造日期。
        if needs_resample and tf_code == 'M' and not hdf.empty:
            hdf = hdf.loc[hdf.groupby(hdf['date'].dt.to_period('M'))['date'].idxmax()]
        plot_holders = show_holders and not hdf.empty
        if show_holders and hdf.empty:
            st.info(f"ℹ️ {selected_symbol} 在此範圍內無大戶持股資料（集保股權分散表自 2023-03 起，且每週一筆）")

        # 創建圖表
        num_subplots = 1  # K線圖
        if show_volume:
            num_subplots += 1
        if plot_holders:
            num_subplots += 1
        if show_rsi:
            num_subplots += 1
        if show_macd:
            num_subplots += 1
        
        # 設置子圖高度比例
        row_heights = [0.5]  # K線圖占 50%
        remaining_height = 0.5
        additional_plots = num_subplots - 1
        if additional_plots > 0:
            subplot_height = remaining_height / additional_plots
            row_heights.extend([subplot_height] * additional_plots)
        
        # 創建子圖（指標週期單位隨 K 線週期改變，標題一併標示）
        subplot_titles = [f'價格走勢（{timeframe_label}）']
        if show_volume:
            subplot_titles.append('成交量')
        if plot_holders:
            # 標題誠實反映實際點數：來源恆為每週，月線下只是抽稀成每月最後一筆
            hnote = '集保，每週' if tf_code != 'M' else '集保，每月取最後一筆週資料'
            subplot_titles.append(f'千張大戶持股比例 %（左）× 總股東人數（右）｜{hnote}')
        if show_rsi:
            subplot_titles.append(f'RSI(14{unit})')
        if show_macd:
            subplot_titles.append(f'MACD(12/26/9 {unit})')
        
        # 大戶子圖需要右軸（股東人數的單位是「人」，與左軸的「%」量級差 6 個數量級，
        # 共用一軸會讓大戶佔比被壓成一條直線）。secondary_y 必須在建圖時宣告，
        # 故先算出大戶落在第幾列。
        holder_row = (2 + (1 if show_volume else 0)) if plot_holders else None
        fig = make_subplots(
            rows=num_subplots,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
            subplot_titles=subplot_titles,
            specs=[[{"secondary_y": (r == holder_row)}] for r in range(1, num_subplots + 1)],
        )
        
        # K線圖
        fig.add_trace(
            go.Candlestick(
                x=df['date'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='K線',
                increasing_line_color='red',
                decreasing_line_color='green'
            ),
            row=1, col=1
        )
        
        # 移動平均線（週線下標籤加「週」，避免 MA5 被誤讀為 5 日線）
        if show_ma and ma_windows:
            colors = ['blue', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive']
            for i, window in enumerate(ma_windows):
                ma = calculate_ma(df, window)
                fig.add_trace(
                    go.Scatter(
                        x=df['date'],
                        y=ma,
                        name=ma_label(window),
                        line=dict(color=colors[i % len(colors)], width=1)
                    ),
                    row=1, col=1
                )
        
        # 布林通道
        if show_bb:
            upper, middle, lower = calculate_bollinger_bands(df)
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=upper,
                    name='BB Upper',
                    line=dict(color='rgba(250, 128, 114, 0.5)', width=1)
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=middle,
                    name='BB Middle',
                    line=dict(color='rgba(128, 128, 128, 0.5)', width=1, dash='dash')
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=lower,
                    name='BB Lower',
                    line=dict(color='rgba(250, 128, 114, 0.5)', width=1),
                    fill='tonexty',
                    fillcolor='rgba(250, 128, 114, 0.1)'
                ),
                row=1, col=1
            )
        
        current_row = 2
        
        # 成交量
        if show_volume:
            colors = ['red' if row['close'] >= row['open'] else 'green' 
                     for _, row in df.iterrows()]
            fig.add_trace(
                go.Bar(
                    x=df['date'],
                    y=df['volume'],
                    name='成交量',
                    marker_color=colors
                ),
                row=current_row, col=1
            )
            current_row += 1

        # 大戶持股（每週一筆）
        if plot_holders:
            # 帶點折線：點＝實際的週快照。刻意不做日內插值／不填滿，
            # 讓「這是每週一筆」在視覺上就看得出來，避免誤以為有每日資料。
            fig.add_trace(
                go.Scatter(
                    x=hdf['date'],
                    y=hdf['big_pct'],
                    name='千張大戶%',
                    mode='lines+markers',
                    marker=dict(size=4),
                    line=dict(color='darkviolet', width=2),
                    hovertemplate='%{x|%Y-%m-%d}<br>千張大戶 %{y:.2f}%<extra></extra>'
                ),
                row=current_row, col=1
            )
            if 'big400_pct' in hdf.columns and hdf['big400_pct'].notna().any():
                fig.add_trace(
                    go.Scatter(
                        x=hdf['date'],
                        y=hdf['big400_pct'],
                        name='400張+%',
                        mode='lines',
                        line=dict(color='rgba(148, 0, 211, 0.45)', width=1, dash='dot'),
                        hovertemplate='%{x|%Y-%m-%d}<br>400張+ %{y:.2f}%<extra></extra>'
                    ),
                    row=current_row, col=1
                )
            # 總股東人數（右軸）：與大戶佔比天生反向 —— 兩線交叉張開＝籌碼由大戶流向散戶。
            if 'total_holders' in hdf.columns and hdf['total_holders'].notna().any():
                fig.add_trace(
                    go.Scatter(
                        x=hdf['date'],
                        y=hdf['total_holders'],
                        name='總股東人數',
                        mode='lines',
                        line=dict(color='rgba(255, 140, 0, 0.9)', width=1.5),
                        hovertemplate='%{x|%Y-%m-%d}<br>股東 %{y:,.0f} 人<extra></extra>'
                    ),
                    row=current_row, col=1, secondary_y=True
                )
                fig.update_yaxes(title_text="股東人數", row=current_row, col=1,
                                 secondary_y=True, showgrid=False)
            fig.update_yaxes(title_text="持股 %", row=current_row, col=1, secondary_y=False)
            current_row += 1

        # RSI
        if show_rsi:
            rsi = calculate_rsi(df)
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=rsi,
                    name='RSI',
                    line=dict(color='purple', width=2)
                ),
                row=current_row, col=1
            )
            # RSI 超買超賣線
            fig.add_hline(y=70, line_dash="dash", line_color="red", 
                         opacity=0.5, row=current_row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", 
                         opacity=0.5, row=current_row, col=1)
            current_row += 1
        
        # MACD
        if show_macd:
            macd, signal, hist = calculate_macd(df)
            
            # MACD 柱狀圖
            colors = ['red' if val >= 0 else 'green' for val in hist]
            fig.add_trace(
                go.Bar(
                    x=df['date'],
                    y=hist,
                    name='MACD Histogram',
                    marker_color=colors
                ),
                row=current_row, col=1
            )
            
            # MACD 線
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=macd,
                    name='MACD',
                    line=dict(color='blue', width=2)
                ),
                row=current_row, col=1
            )
            
            # Signal 線
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=signal,
                    name='Signal',
                    line=dict(color='orange', width=2)
                ),
                row=current_row, col=1
            )
            current_row += 1
        
        # 更新圖表佈局
        fig.update_layout(
            title=f'{selected_symbol} {name_map.get(selected_symbol, "")} 技術分析圖表（{timeframe_label}）',
            height=800,
            showlegend=True,
            xaxis_rangeslider_visible=False,
            hovermode='x unified'
        )
        
        # 更新 x 軸
        fig.update_xaxes(title_text="日期", row=num_subplots, col=1)
        
        # 更新 y 軸
        fig.update_yaxes(title_text="價格 ($)", row=1, col=1)
        if show_volume:
            fig.update_yaxes(title_text="成交量", row=2, col=1)
        
        # 顯示圖表
        st.plotly_chart(fig, width="stretch")
        
        # 技術指標數值表格
        st.markdown("### 📊 技術指標數值")
        
        indicators_data = {
            '日期': df['date'].iloc[-1].strftime('%Y-%m-%d'),
            '收盤價': f"${latest['close']:.2f}",
            '漲跌': f"{price_change:+.2f} ({price_change_pct:+.2f}%)"
        }
        
        if show_ma and ma_windows:
            for window in ma_windows:
                ma_val = calculate_ma(df, window).iloc[-1]
                indicators_data[ma_label(window)] = f"${ma_val:.2f}" if not pd.isna(ma_val) else "-"
        
        if show_rsi:
            rsi_val = calculate_rsi(df).iloc[-1]
            indicators_data['RSI'] = f"{rsi_val:.2f}" if not pd.isna(rsi_val) else "-"
            
            # RSI 解讀
            if not pd.isna(rsi_val):
                if rsi_val > 70:
                    indicators_data['RSI 狀態'] = "🔴 超買"
                elif rsi_val < 30:
                    indicators_data['RSI 狀態'] = "🟢 超賣"
                else:
                    indicators_data['RSI 狀態'] = "⚪ 中性"
        
        if show_macd:
            macd_val, signal_val, hist_val = calculate_macd(df)
            indicators_data['MACD'] = f"{macd_val.iloc[-1]:.2f}" if not pd.isna(macd_val.iloc[-1]) else "-"
            indicators_data['Signal'] = f"{signal_val.iloc[-1]:.2f}" if not pd.isna(signal_val.iloc[-1]) else "-"
            indicators_data['Histogram'] = f"{hist_val.iloc[-1]:.2f}" if not pd.isna(hist_val.iloc[-1]) else "-"
        
        # 轉換為 DataFrame 並顯示
        indicators_df = pd.DataFrame([indicators_data])
        st.dataframe(indicators_df, width="stretch")
        
        # 數據下載
        st.markdown("### 💾 數據下載")
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 下載 CSV",
            data=csv,
            file_name=f"{selected_symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        client.close()
        
    except Exception as e:
        st.error(f"❌ 發生錯誤: {e}")
        import traceback
        st.code(traceback.format_exc())
