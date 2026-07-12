"""
系統總覽頁面
"""
import streamlit as st
from pymongo import MongoClient
from datetime import datetime, timedelta
import pandas as pd


def format_date(date_value):
    """
    安全地格式化日期，支持字符串和 datetime 對象
    """
    if date_value is None:
        return "未知"
    
    # 如果已經是字符串，直接返回（假設格式正確）
    if isinstance(date_value, str):
        # 嘗試標準化格式
        try:
            dt = pd.to_datetime(date_value)
            return dt.strftime('%Y-%m-%d')
        except:
            return date_value
    
    # 如果是 datetime 對象，格式化
    if isinstance(date_value, datetime):
        return date_value.strftime('%Y-%m-%d')
    
    # 其他類型，嘗試轉換
    try:
        return str(date_value)
    except:
        return "未知"


def show():
    st.title("🏠 系統總覽")
    st.markdown("歡迎使用台股量化分析系統！以下是系統狀態概覽。")
    
    # 連接 MongoDB
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        db = client['tw_stock_analysis']
        
        # 測試連接
        client.server_info()
        
        # 系統狀態卡片
        st.markdown("### 📊 數據庫狀態")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            stock_count = db.stock_price.distinct('symbol').__len__()
            st.metric("股票數量", f"{stock_count}", "支")
        
        with col2:
            price_count = db.stock_price.count_documents({})
            st.metric("股價記錄", f"{price_count:,}", "筆")
        
        with col3:
            # 財報以 quarterly_earnings 為準（實際分析所用；financial_reports 為棄用舊表）
            financial_count = db.quarterly_earnings.count_documents({})
            st.metric("財報記錄", f"{financial_count:,}", "筆")
        
        with col4:
            factor_count = db.stock_factors.count_documents({})
            st.metric("因子記錄", f"{factor_count:,}", "筆")
        
        # 最新數據時間
        st.markdown("### ⏰ 資料更新時間")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            latest_price = db.stock_price.find_one(
                sort=[('date', -1)],
                projection={'date': 1}
            )
            if latest_price:
                st.info(f"**股價數據**: {format_date(latest_price['date'])}")
            else:
                st.warning("股價數據: 無")
        
        with col2:
            # quarterly_earnings 無日期欄位，以最新 年度/季度 表示
            latest_financial = db.quarterly_earnings.find_one(
                sort=[('year', -1), ('season', -1)],
                projection={'year': 1, 'season': 1}
            )
            if latest_financial:
                st.info(f"**財報數據**: {latest_financial.get('year')} Q{latest_financial.get('season')}")
            else:
                st.warning("財報數據: 無")
        
        with col3:
            latest_factor = db.stock_factors.find_one(
                sort=[('date', -1)],
                projection={'date': 1}
            )
            if latest_factor:
                st.info(f"**因子數據**: {format_date(latest_factor['date'])}")
            else:
                st.warning("因子數據: 無")
        
        # 熱門股票
        st.markdown("### 🔥 熱門股票（交易量前 10）")
        
        # 獲取最近一個交易日
        if latest_price:
            latest_date = latest_price['date']
            
            # 使用 $lookup 聚合連接 stock_price 和 stock_factors
            pipeline = [
                {'$match': {'date': latest_date}},
                {'$sort': {'volume': -1}},
                {'$limit': 10},
                {
                    '$lookup': {
                        'from': 'stock_factors',
                        'let': {'symbol': '$symbol', 'date': '$date'},
                        'pipeline': [
                            {
                                '$match': {
                                    '$expr': {
                                        '$and': [
                                            {'$eq': ['$symbol', '$$symbol']},
                                            {'$eq': ['$date', '$$date']}
                                        ]
                                    }
                                }
                            },
                            {'$project': {'pe_ratio': 1, 'pb_ratio': 1, '_id': 0}}
                        ],
                        'as': 'factors'
                    }
                },
                {
                    '$project': {
                        'symbol': 1,
                        'close': 1,
                        'volume': 1,
                        'pe_ratio': {'$arrayElemAt': ['$factors.pe_ratio', 0]},
                        'pb_ratio': {'$arrayElemAt': ['$factors.pb_ratio', 0]}
                    }
                }
            ]
            
            top_stocks = list(db.stock_price.aggregate(pipeline))
            
            if top_stocks:
                from bson import Decimal128
                
                df = pd.DataFrame(top_stocks)
                
                # 轉換 Decimal128 為 float
                for col in ['close', 'volume', 'pe_ratio', 'pb_ratio']:
                    if col in df.columns:
                        df[col] = df[col].apply(
                            lambda x: float(x.to_decimal()) if isinstance(x, Decimal128) 
                            else (float(x) if pd.notna(x) and x is not None else None)
                        )
                
                # 準備顯示欄位
                display_cols = ['symbol', 'close', 'volume']
                col_names = ['代碼', '收盤價', '交易量']
                
                # 添加因子欄位（如果存在且非空）
                if 'pe_ratio' in df.columns and not df['pe_ratio'].isna().all():
                    display_cols.append('pe_ratio')
                    col_names.append('PE')
                if 'pb_ratio' in df.columns and not df['pb_ratio'].isna().all():
                    display_cols.append('pb_ratio')
                    col_names.append('PB')
                
                df = df[display_cols]
                df.columns = col_names
                
                # 格式化數字
                df['收盤價'] = df['收盤價'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
                df['交易量'] = df['交易量'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "-")
                if 'PE' in df.columns:
                    df['PE'] = df['PE'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
                if 'PB' in df.columns:
                    df['PB'] = df['PB'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
                
                st.dataframe(df, width="stretch")
            else:
                st.info("暫無交易數據")
        
        # 回測結果摘要
        st.markdown("### 🎯 最近回測結果")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 均線交叉策略")
            st.markdown("""
            - **年化報酬**: 8.06%
            - **夏普比率**: 1.282
            - **最大回撤**: -3.99%
            - **勝率**: 77.78%
            - **評級**: ⭐⭐⭐⭐ 穩健
            """)
        
        with col2:
            st.markdown("#### 動能選股策略")
            st.markdown("""
            - **年化報酬**: 27.34%
            - **夏普比率**: 1.657
            - **最大回撤**: -13.82%
            - **勝率**: 50.00%
            - **評級**: ⭐⭐⭐⭐⭐ 優秀
            """)
        
        # 快速操作
        st.markdown("### ⚡ 快速操作")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 查看 K 線圖", width="stretch"):
                st.session_state.page = "📊 K線圖與技術指標"
                st.rerun()
        
        with col2:
            if st.button("📈 回測結果", width="stretch"):
                st.session_state.page = "📈 回測結果視覺化"
                st.rerun()
        
        with col3:
            if st.button("🧮 因子分析", width="stretch"):
                st.session_state.page = "🧮 因子分析面板"
                st.rerun()
        
        # 系統信息
        st.markdown("---")
        st.markdown("### ℹ️ 系統資訊")
        
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.markdown("""
            **已完成功能**:
            - ✅ 回測引擎（3 個內建策略）
            - ✅ 因子庫（17 個量化因子）
            - ✅ 自動數據更新（每小時）
            - ✅ MongoDB 數據存儲
            - ✅ 互動式儀表板
            """)
        
        with info_col2:
            st.markdown("""
            **技術棧**:
            - Python 3.10+
            - MongoDB 7.0
            - Streamlit 1.30+
            - Plotly 5.18+
            - Pandas, NumPy
            """)
        
        client.close()
        
    except Exception as e:
        st.error(f"❌ 無法連接到 MongoDB: {e}")
        st.info("請確認 MongoDB 服務正在運行：`mongod`")
