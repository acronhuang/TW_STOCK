# Priority 3 實盤準備 - 完整實施計劃

**文檔版本**: v1.0  
**創建日期**: 2026-02-23  
**預計完成**: 2026-03-31（5 週）  
**狀態**: 📋 規劃中

---

## 📋 執行摘要

### 目標
將 v2 優化策略（74.51% 年化）從回測階段推進至實盤交易，透過風控、自動化與監控系統確保穩定運行。

### 關鍵指標
- **回測績效**: 74.51% 年化（2024）、39.32% 三年平均
- **目標實盤**: 年化 >30%、夏普 >1.5、回撤 <-15%
- **測試資金**: 10-30 萬（初期 30% 配置）
- **測試期間**: 3 個月（2026-04 ~ 2026-06）

### 成功標準
1. ✅ 完成 4 個核心模組開發（風控、交易、監控、回報）
2. ✅ 通過 1 個月紙上交易測試（勝率 >60%）
3. ✅ 小資金實盤 3 個月達績效目標（年化 >30%）

---

## 🏗️ 系統架構

### 整體架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                    實盤交易系統 v1.0                         │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                             │
        ▼                                             ▼
┌──────────────────┐                         ┌──────────────────┐
│  策略引擎模組     │                         │  數據管理模組     │
├──────────────────┤                         ├──────────────────┤
│ MultiFactorStrategy                        │ MongoDB           │
│ - 因子計算        │◄─────────────────────►│ - stock_factors   │
│ - 選股排名        │                         │ - stock_price     │
│ - 信號生成        │                         │ - financial       │
└──────────────────┘                         └──────────────────┘
        │                                             │
        │                                             │
        ▼                                             ▼
┌──────────────────┐                         ┌──────────────────┐
│  風控管理器       │                         │  交易執行模組     │
├──────────────────┤                         ├──────────────────┤
│ RiskManager       │                         │ OrderExecutor     │
│ - 倉位管理        │◄─────────────────────►│ - 下單介面        │
│ - 止損監控        │                         │ - 委託追蹤        │
│ - 風險預警        │                         │ - 成交回報        │
└──────────────────┘                         └──────────────────┘
        │                                             │
        │                                             │
        ▼                                             ▼
┌──────────────────┐                         ┌──────────────────┐
│  監控預警系統     │                         │  績效分析模組     │
├──────────────────┤                         ├──────────────────┤
│ AlertManager      │                         │ PerformanceTracker│
│ - Line Notify     │◄─────────────────────►│ - 即時績效        │
│ - Telegram Bot    │                         │ - 歷史回顧        │
│ - Email 報告      │                         │ - 歸因分析        │
└──────────────────┘                         └──────────────────┘
        │                                             │
        └──────────────────┬──────────────────────────┘
                           ▼
                ┌──────────────────────┐
                │  Web Dashboard       │
                ├──────────────────────┤
                │ Streamlit 即時監控    │
                │ - 持倉視圖            │
                │ - 績效圖表            │
                │ - 風險儀表板          │
                └──────────────────────┘
```

---

## 📦 模組設計

### 模組 1: 風控管理器 (RiskManager)

**檔案位置**: `src/trading/risk_manager.py`

#### 核心功能

1. **倉位管理**
   - 單股上限：10%（10 支股票）
   - 總倉位：100%（滿倉策略）
   - 再平衡容忍度：±5%

2. **止損監控**
   - 單股止損：-5%（觸發後立即賣出）
   - 組合止損：-10%（觸發後減倉 50%）
   - 追蹤止損：價格回撤 -3%

3. **風險限制**
   - 單日最大交易金額：總資金 30%
   - 單月最大換手率：200%
   - 單個產業集中度：<40%

4. **風險預警**
   - Level 1（輕微）：單股虧損 -3%
   - Level 2（中等）：組合虧損 -5%
   - Level 3（嚴重）：組合虧損 -8%

#### 類別設計

```python
class RiskManager:
    """風控管理器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.single_stock_limit = config.get('single_stock_limit', 0.10)
        self.portfolio_stop_loss = config.get('portfolio_stop_loss', -0.10)
        self.single_stock_stop_loss = config.get('single_stock_stop_loss', -0.05)
        self.max_turnover = config.get('max_turnover', 2.0)
        self.sector_limit = config.get('sector_limit', 0.40)
    
    def validate_order(self, order: Order, portfolio: Portfolio) -> Tuple[bool, str]:
        """驗證訂單是否符合風控規則
        
        Returns:
            (is_valid, reason)
        """
        # 檢查單股倉位限制
        if not self._check_position_limit(order, portfolio):
            return False, "超過單股倉位限制 10%"
        
        # 檢查產業集中度
        if not self._check_sector_concentration(order, portfolio):
            return False, "超過產業集中度限制 40%"
        
        # 檢查換手率
        if not self._check_turnover(order, portfolio):
            return False, "超過單日換手率限制"
        
        return True, "通過風控檢查"
    
    def check_stop_loss(self, holdings: List[Holding]) -> List[StopLossSignal]:
        """檢查是否觸發止損
        
        Returns:
            需要止損的持倉清單
        """
        signals = []
        
        for holding in holdings:
            # 單股止損
            if holding.unrealized_pnl_pct < self.single_stock_stop_loss:
                signals.append(StopLossSignal(
                    stock_id=holding.stock_id,
                    reason='single_stock_stop_loss',
                    current_loss=holding.unrealized_pnl_pct,
                    action='close_all'
                ))
        
        # 組合止損
        portfolio_pnl = sum(h.unrealized_pnl_pct for h in holdings) / len(holdings)
        if portfolio_pnl < self.portfolio_stop_loss:
            signals.append(StopLossSignal(
                stock_id='PORTFOLIO',
                reason='portfolio_stop_loss',
                current_loss=portfolio_pnl,
                action='reduce_50pct'
            ))
        
        return signals
    
    def calculate_position_size(self, signal: TradingSignal, 
                                portfolio: Portfolio) -> int:
        """計算合理倉位大小
        
        Returns:
            應買入的股數
        """
        # 基礎倉位（等權重）
        base_position = portfolio.total_value * (1.0 / self.config['top_n'])
        
        # 根據因子分數調整（可選）
        if signal.factor_score > 0.8:
            adjusted_position = base_position * 1.1  # 強信號增加 10%
        elif signal.factor_score < 0.5:
            adjusted_position = base_position * 0.9  # 弱信號減少 10%
        else:
            adjusted_position = base_position
        
        # 計算股數（向下取整到張）
        price = self._get_current_price(signal.stock_id)
        shares = int(adjusted_position / price / 1000) * 1000  # 台股以千股為單位
        
        return shares
    
    def generate_alerts(self, portfolio: Portfolio) -> List[Alert]:
        """生成風險預警"""
        alerts = []
        
        # 檢查單股虧損
        for holding in portfolio.holdings:
            if holding.unrealized_pnl_pct < -0.03:
                alerts.append(Alert(
                    level='WARNING' if holding.unrealized_pnl_pct > -0.05 else 'ERROR',
                    message=f"{holding.stock_id} 虧損 {holding.unrealized_pnl_pct:.2%}",
                    timestamp=datetime.now()
                ))
        
        # 檢查組合虧損
        portfolio_pnl = portfolio.unrealized_pnl_pct
        if portfolio_pnl < -0.05:
            alerts.append(Alert(
                level='ERROR',
                message=f"組合虧損 {portfolio_pnl:.2%}，接近止損線",
                timestamp=datetime.now()
            ))
        
        return alerts
```

---

### 模組 2: 交易執行模組 (OrderExecutor)

**檔案位置**: `src/trading/order_executor.py`

#### 核心功能

1. **券商 API 介接**
   - 富邦證券 API（優先）
   - 元大證券 API（備選）
   - 永豐證券 API（備選）

2. **訂單管理**
   - 限價單（預設）
   - 市價單（緊急）
   - IOC/FOK 條件單

3. **委託追蹤**
   - 即時委託狀態查詢
   - 成交回報接收
   - 未成交自動撤單

4. **滑價控制**
   - 限價單價格：昨收 ±2%
   - 最大等待時間：5 分鐘
   - 未成交策略：調整價格或取消

#### 類別設計

```python
class OrderExecutor:
    """交易執行模組"""
    
    def __init__(self, broker_api, risk_manager: RiskManager):
        self.broker = broker_api
        self.risk_manager = risk_manager
        self.orders = {}  # order_id -> Order
        self.executions = []  # 成交記錄
    
    def submit_order(self, order: Order) -> Tuple[bool, str]:
        """提交訂單
        
        Returns:
            (success, order_id_or_error)
        """
        # 風控檢查
        is_valid, reason = self.risk_manager.validate_order(
            order, self.get_current_portfolio()
        )
        if not is_valid:
            logger.error(f"訂單被風控拒絕: {reason}")
            return False, reason
        
        # 提交至券商
        try:
            order_id = self.broker.place_order(
                stock_id=order.stock_id,
                action=order.action,  # 'BUY' or 'SELL'
                quantity=order.quantity,
                price=order.price,
                order_type=order.order_type  # 'LIMIT' or 'MARKET'
            )
            
            self.orders[order_id] = order
            logger.info(f"訂單已提交: {order_id} - {order}")
            
            return True, order_id
            
        except Exception as e:
            logger.error(f"提交訂單失敗: {e}")
            return False, str(e)
    
    def cancel_order(self, order_id: str) -> bool:
        """取消訂單"""
        try:
            self.broker.cancel_order(order_id)
            logger.info(f"訂單已取消: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消訂單失敗: {e}")
            return False
    
    def query_order_status(self, order_id: str) -> OrderStatus:
        """查詢訂單狀態"""
        return self.broker.get_order_status(order_id)
    
    def process_execution_report(self, report: ExecutionReport):
        """處理成交回報"""
        self.executions.append(report)
        
        # 更新訂單狀態
        if report.order_id in self.orders:
            order = self.orders[report.order_id]
            order.filled_quantity += report.filled_quantity
            order.avg_price = (
                (order.avg_price * (order.filled_quantity - report.filled_quantity) +
                 report.price * report.filled_quantity) / order.filled_quantity
            )
            
            if order.filled_quantity >= order.quantity:
                order.status = 'FILLED'
            else:
                order.status = 'PARTIALLY_FILLED'
        
        logger.info(f"成交回報: {report}")
    
    def execute_rebalance(self, signals: List[TradingSignal], 
                         current_holdings: List[Holding]) -> List[Order]:
        """執行再平衡
        
        Args:
            signals: 新的交易信號（目標持倉）
            current_holdings: 當前持倉
        
        Returns:
            執行的訂單清單
        """
        orders = []
        
        # 計算需要賣出的股票
        target_stocks = {s.stock_id for s in signals}
        for holding in current_holdings:
            if holding.stock_id not in target_stocks:
                # 賣出不在目標清單的股票
                order = Order(
                    stock_id=holding.stock_id,
                    action='SELL',
                    quantity=holding.quantity,
                    price=self._calculate_limit_price(holding.stock_id, 'SELL'),
                    order_type='LIMIT'
                )
                success, order_id = self.submit_order(order)
                if success:
                    orders.append(order)
        
        # 等待賣出訂單完成（最多 5 分鐘）
        time.sleep(300)
        
        # 計算需要買入的股票
        portfolio_value = self._get_available_cash()
        for signal in signals:
            quantity = self.risk_manager.calculate_position_size(
                signal, self.get_current_portfolio()
            )
            
            order = Order(
                stock_id=signal.stock_id,
                action='BUY',
                quantity=quantity,
                price=self._calculate_limit_price(signal.stock_id, 'BUY'),
                order_type='LIMIT'
            )
            success, order_id = self.submit_order(order)
            if success:
                orders.append(order)
        
        return orders
```

---

### 模組 3: 監控預警系統 (AlertManager)

**檔案位置**: `src/trading/alert_manager.py`

#### 核心功能

1. **Line Notify 整合**
   - 即時推送（止損、成交、預警）
   - 每日摘要（早上 9:00）
   - 每週報告（週六 10:00）

2. **Telegram Bot 整合**
   - 雙向互動（查詢持倉、績效）
   - 緊急指令（強制平倉）
   - 圖表推送

3. **Email 報告**
   - 每日詳細報告（PDF）
   - 每月績效總結
   - 異常告警

4. **預警分級**
   - 🟢 INFO：一般信息（成交確認）
   - 🟡 WARNING：需注意（單股虧損 -3%）
   - 🔴 ERROR：需處理（組合虧損 -5%）
   - ⚫ CRITICAL：緊急（觸發止損）

#### 類別設計

```python
class AlertManager:
    """監控預警系統"""
    
    def __init__(self, config: dict):
        self.line_token = config.get('line_notify_token')
        self.telegram_bot_token = config.get('telegram_bot_token')
        self.telegram_chat_id = config.get('telegram_chat_id')
        self.email_config = config.get('email')
    
    def send_alert(self, alert: Alert):
        """發送預警"""
        if alert.level == 'INFO':
            self._send_line(f"ℹ️ {alert.message}")
        elif alert.level == 'WARNING':
            self._send_line(f"⚠️ {alert.message}")
            self._send_telegram(f"⚠️ {alert.message}")
        elif alert.level == 'ERROR':
            self._send_line(f"🔴 {alert.message}")
            self._send_telegram(f"🔴 {alert.message}")
            self._send_email(alert)
        elif alert.level == 'CRITICAL':
            self._send_line(f"⚫ 緊急警報：{alert.message}")
            self._send_telegram(f"⚫ 緊急警報：{alert.message}")
            self._send_email(alert)
            # 可選：撥打電話通知
    
    def send_daily_summary(self, summary: DailySummary):
        """發送每日摘要"""
        message = f"""
📊 每日摘要 ({summary.date})

【績效】
總權益: ${summary.total_value:,.0f}
今日損益: {summary.daily_pnl:+.2%}
累積報酬: {summary.total_return:+.2%}

【持倉】
持股數量: {summary.num_holdings}
總曝險: {summary.total_exposure:.1%}
現金水位: {summary.cash_ratio:.1%}

【交易】
今日成交: {summary.num_trades} 筆
交易金額: ${summary.trade_value:,.0f}

【風險】
最大持股: {summary.largest_position} ({summary.largest_position_pct:.1%})
最大虧損: {summary.worst_holding} ({summary.worst_holding_pnl:+.2%})
"""
        self._send_line(message)
        
        # 生成圖表並透過 Telegram 發送
        chart_path = self._generate_daily_chart(summary)
        self._send_telegram_photo(chart_path, message)
    
    def send_weekly_report(self, report: WeeklyReport):
        """發送每週報告"""
        # PDF 報告透過 Email 發送
        pdf_path = self._generate_weekly_pdf(report)
        self._send_email_with_attachment(
            subject=f"每週報告 ({report.week_start} ~ {report.week_end})",
            body=self._format_weekly_summary(report),
            attachment=pdf_path
        )
    
    def _send_line(self, message: str):
        """Line Notify"""
        if not self.line_token:
            return
        
        headers = {'Authorization': f'Bearer {self.line_token}'}
        data = {'message': message}
        requests.post('https://notify-api.line.me/api/notify', 
                     headers=headers, data=data)
    
    def _send_telegram(self, message: str):
        """Telegram Bot"""
        if not self.telegram_bot_token:
            return
        
        url = f'https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage'
        data = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        requests.post(url, data=data)
    
    def _send_email(self, alert: Alert):
        """Email 通知"""
        # 使用 Gmail SMTP
        pass
```

---

### 模組 4: 績效分析模組 (PerformanceTracker)

**檔案位置**: `src/trading/performance_tracker.py`

#### 核心功能

1. **即時績效計算**
   - 未實現損益（Mark-to-Market）
   - 已實現損益（Closed P&L）
   - 總報酬率、夏普比率

2. **歷史績效追蹤**
   - 每日淨值曲線
   - 每月報酬統計
   - 回撤分析

3. **歸因分析**
   - 因子貢獻度（動能/價值/質量）
   - 個股貢獻度（Top 5 盈虧）
   - 產業貢獻度

4. **對比基準**
   - vs 台灣加權指數
   - vs 0050 ETF
   - vs 優化回測結果

#### 類別設計

```python
class PerformanceTracker:
    """績效分析模組"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db['trading_performance']
    
    def update_daily_performance(self, portfolio: Portfolio, date: datetime):
        """更新每日績效"""
        # 計算績效指標
        metrics = {
            'date': date,
            'total_value': portfolio.total_value,
            'cash': portfolio.cash,
            'holdings_value': portfolio.holdings_value,
            'unrealized_pnl': portfolio.unrealized_pnl,
            'realized_pnl': portfolio.realized_pnl,
            'total_return': portfolio.total_return,
            'daily_return': self._calculate_daily_return(date),
            'sharpe_ratio': self._calculate_sharpe(date),
            'max_drawdown': self._calculate_max_drawdown(date),
            'win_rate': self._calculate_win_rate(date)
        }
        
        # 持倉明細
        holdings = [
            {
                'stock_id': h.stock_id,
                'quantity': h.quantity,
                'avg_cost': h.avg_cost,
                'current_price': h.current_price,
                'market_value': h.market_value,
                'unrealized_pnl': h.unrealized_pnl,
                'unrealized_pnl_pct': h.unrealized_pnl_pct,
                'weight': h.market_value / portfolio.total_value
            }
            for h in portfolio.holdings
        ]
        
        # 保存至資料庫
        self.collection.insert_one({
            'date': date,
            'metrics': metrics,
            'holdings': holdings
        })
    
    def get_performance_summary(self, start_date: datetime, 
                                end_date: datetime) -> PerformanceSummary:
        """獲取績效摘要"""
        records = list(self.collection.find({
            'date': {'$gte': start_date, '$lte': end_date}
        }).sort('date', 1))
        
        if not records:
            return None
        
        # 計算累積報酬
        total_returns = [r['metrics']['total_return'] for r in records]
        cumulative_return = (1 + total_returns[-1]) - 1
        
        # 計算年化報酬
        days = (end_date - start_date).days
        annual_return = (1 + cumulative_return) ** (365 / days) - 1
        
        # 計算最大回撤
        equity_curve = [r['metrics']['total_value'] for r in records]
        max_drawdown = self._calculate_max_drawdown_from_curve(equity_curve)
        
        # 計算夏普比率
        daily_returns = [r['metrics']['daily_return'] for r in records]
        sharpe_ratio = self._calculate_sharpe_from_returns(daily_returns)
        
        return PerformanceSummary(
            start_date=start_date,
            end_date=end_date,
            total_return=cumulative_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            num_trades=self._count_trades(start_date, end_date),
            win_rate=self._calculate_win_rate_period(start_date, end_date)
        )
    
    def generate_attribution_report(self, date: datetime) -> AttributionReport:
        """生成歸因報告"""
        # 獲取當日持倉
        record = self.collection.find_one({'date': date})
        if not record:
            return None
        
        # 計算因子貢獻
        factor_contributions = self._calculate_factor_contributions(
            record['holdings']
        )
        
        # 計算個股貢獻
        stock_contributions = sorted(
            record['holdings'],
            key=lambda x: x['unrealized_pnl'],
            reverse=True
        )
        
        # 計算產業貢獻
        sector_contributions = self._calculate_sector_contributions(
            record['holdings']
        )
        
        return AttributionReport(
            date=date,
            factor_contributions=factor_contributions,
            top_contributors=stock_contributions[:5],
            worst_contributors=stock_contributions[-5:],
            sector_contributions=sector_contributions
        )
```

---

## 🗓️ 實施時間表

### 第 1 週（2026-02-24 ~ 2026-03-02）：基礎架構開發

**任務**:
- [ ] 創建 `src/trading/` 目錄結構
- [ ] 實作 RiskManager 核心功能（倉位管理、止損）
- [ ] 實作 OrderExecutor 基礎介面（模擬模式）
- [ ] 撰寫單元測試（>80% 覆蓋率）

**交付物**:
- `src/trading/risk_manager.py` (300 行)
- `src/trading/order_executor.py` (400 行)
- `tests/trading/test_risk_manager.py` (200 行)
- `tests/trading/test_order_executor.py` (200 行)

**負責人**: 開發者團隊  
**檢查點**: 2026-03-02（週日）程式碼審查

---

### 第 2 週（2026-03-03 ~ 2026-03-09）：監控與分析模組

**任務**:
- [ ] 實作 AlertManager（Line Notify + Telegram Bot）
- [ ] 實作 PerformanceTracker（即時績效追蹤）
- [ ] 整合 MongoDB 績效資料庫
- [ ] 創建 Streamlit 監控儀表板

**交付物**:
- `src/trading/alert_manager.py` (350 行)
- `src/trading/performance_tracker.py` (400 行)
- `dashboard/live_trading.py` (300 行)
- Line/Telegram 通知測試成功

**負責人**: 開發者團隊  
**檢查點**: 2026-03-09（週日）系統整合測試

---

### 第 3 週（2026-03-10 ~ 2026-03-16）：券商 API 整合

**任務**:
- [ ] 研究富邦證券 API 文件
- [ ] 實作富邦 API 連線與認證
- [ ] 實作下單、查詢、撤單功能
- [ ] 測試環境下單測試（紙上交易）

**交付物**:
- `src/brokers/fubon_api.py` (500 行)
- `config/broker_config.yaml`（券商配置）
- API 測試報告（成功率 >95%）

**負責人**: 技術負責人  
**檢查點**: 2026-03-16（週日）API 整合驗收

---

### 第 4 週（2026-03-17 ~ 2026-03-23）：系統整合與紙上測試

**任務**:
- [ ] 整合所有模組（策略 → 風控 → 交易 → 監控）
- [ ] 創建模擬交易環境（使用歷史數據）
- [ ] 執行 10 天紙上交易測試
- [ ] 修正測試中發現的 Bug

**交付物**:
- `scripts/paper_trading.py`（紙上交易主程式）
- 紙上交易報告（10 天，勝率 >60%）
- Bug 修正清單

**負責人**: 全員  
**檢查點**: 2026-03-23（週日）紙上測試總結

---

### 第 5 週（2026-03-24 ~ 2026-03-31）：文檔與部署準備

**任務**:
- [ ] 撰寫操作手冊（SOP）
- [ ] 撰寫風險管理手冊
- [ ] 準備實盤部署環境（雲端伺服器/本地主機）
- [ ] 執行壓力測試與容錯測試

**交付物**:
- `docs/LIVE_TRADING_SOP.md`（操作手冊）
- `docs/RISK_MANAGEMENT_MANUAL.md`（風險手冊）
- 壓力測試報告
- 部署檢查清單

**負責人**: 技術負責人  
**檢查點**: 2026-03-31（週一）正式上線前檢查

---

## 💰 資金配置計劃

### 階段 1: 小資金測試（2026-04-01 ~ 2026-06-30，3 個月）

**配置**:
- 總資金：10-30 萬
- 策略配置：30% v2 策略（3-9 萬）
- 現金水位：70%（保留流動性）
- 持股數量：3-5 支（vs 目標 10 支）

**目標**:
- 年化報酬：>20%（保守目標）
- 最大回撤：<-15%
- 勝率：>55%
- 追蹤誤差（vs 回測）：<10%

**風險預算**:
- 單股最大虧損：-5%（1,500-4,500 元）
- 組合最大虧損：-10%（3,000-9,000 元）
- 每月交易成本：<1%（300-900 元）

---

### 階段 2: 中等資金擴展（2026-07-01 ~ 2026-12-31，6 個月）

**條件**（需同時滿足）:
1. ✅ 階段 1 年化報酬 >20%
2. ✅ 階段 1 最大回撤 <-15%
3. ✅ 階段 1 勝率 >55%
4. ✅ 無重大風控事件

**配置**:
- 總資金：50-100 萬
- 策略配置：50% v2 策略（25-50 萬）
- 現金水位：50%
- 持股數量：5-8 支

**目標**:
- 年化報酬：>25%
- 最大回撤：<-12%
- 勝率：>60%

---

### 階段 3: 滿倉運行（2027-01-01 起）

**條件**（需同時滿足）:
1. ✅ 階段 2 年化報酬 >25%
2. ✅ 階段 2 最大回撤 <-12%
3. ✅ 階段 2 勝率 >60%
4. ✅ 累積測試期 ≥9 個月

**配置**:
- 總資金：100-500 萬
- 策略配置：80-100% v2 策略
- 現金水位：0-20%
- 持股數量：10 支（完整策略）

**目標**:
- 年化報酬：>30%（接近回測 39.32%）
- 最大回撤：<-15%
- 勝率：>60%

---

## 🛡️ 風險管理

### 風險分級

**Level 1 - 低風險（可接受）**:
- 單股虧損：0% ~ -3%
- 組合虧損：0% ~ -3%
- 處理：持續觀察

**Level 2 - 中風險（需注意）**:
- 單股虧損：-3% ~ -5%
- 組合虧損：-3% ~ -5%
- 處理：增加監控頻率、準備減倉

**Level 3 - 高風險（需行動）**:
- 單股虧損：-5% ~ -8%
- 組合虧損：-5% ~ -8%
- 處理：觸發單股止損、組合減倉

**Level 4 - 緊急（立即行動）**:
- 單股虧損：< -8%
- 組合虧損：< -8%
- 處理：強制平倉、暫停交易、檢討策略

---

### 緊急應變計劃

**情境 1: 單股閃崩（-10% 以上）**

**應變措施**:
1. 立即停止該股所有委託
2. 市價單全部賣出（不考慮滑價）
3. 通知開發團隊檢查數據異常
4. 記錄事件並寫入風控日誌
5. 檢討：是否因子數據錯誤？是否黑天鵝事件？

**預防措施**:
- 每日盤前檢查因子數據品質
- 設置漲跌停鎖定機制（不買入/賣出漲跌停股）
- 產業分散（避免單一產業集中）

---

**情境 2: 系統性風險（大盤暴跌 -5% 以上）**

**應變措施**:
1. 立即暫停所有買入委託
2. 保留現金水位 >30%
3. 評估是否需要全面減倉
4. 如大盤跌幅 >-8%，組合減倉 50%
5. 如大盤跌幅 >-10%，組合全部平倉

**預防措施**:
- 每日監控大盤技術指標（MACD、RSI）
- 每月評估總體經濟風險（升息、戰爭）
- 考慮搭配期貨避險（台指期空單）

---

**情境 3: 券商 API 故障**

**應變措施**:
1. 立即切換至備用券商 API
2. 如無法下單，致電券商人工下單
3. 記錄所有手動操作
4. 事後檢討 API 穩定性

**預防措施**:
- 準備至少 2 家券商 API
- 每週測試 API 連線
- 保留券商營業員聯絡方式

---

**情境 4: 策略失效（連續 3 個月負報酬）**

**應變措施**:
1. 立即暫停自動交易
2. 召開策略檢討會議
3. 回測最近 3 個月數據，分析失效原因
4. 調整參數或暫停策略
5. 如無法改善，停用策略並返回現金

**預防措施**:
- 每月回測策略績效（滾動 1 年）
- 監控市場環境變化（牛市/熊市/震盪）
- 準備 Plan B 策略（如轉為防禦型選股）

---

## 📊 監控指標

### 每日監控（自動化）

| 指標 | 頻率 | 正常範圍 | 警戒範圍 | 緊急範圍 |
|------|------|---------|---------|---------|
| 組合損益 | 即時 | -2% ~ +5% | -3% ~ -5% | < -5% |
| 單股損益 | 即時 | -2% ~ +5% | -3% ~ -5% | < -5% |
| 持股數量 | 每日 | 8-10 支 | 6-7 支 | <6 支 |
| 現金水位 | 每日 | 5-15% | 15-30% | >30% |
| 換手率 | 每月 | 100-200% | 200-300% | >300% |

### 每週監控（手動）

| 指標 | 正常範圍 | 需注意 |
|------|---------|--------|
| 週報酬率 | -2% ~ +3% | < -3% or > +5% |
| 勝率 | >55% | <50% |
| 交易次數 | 8-12 筆 | <5 筆 or >15 筆 |
| 產業集中度 | <40% | >40% |

### 每月監控（檢討會議）

| 指標 | 正常範圍 | 需注意 |
|------|---------|--------|
| 月報酬率 | -5% ~ +10% | < -8% |
| 追蹤誤差（vs 回測） | <5% | >10% |
| 最大回撤 | < -10% | > -12% |
| 夏普比率 | >1.5 | <1.2 |

---

## 🧪 測試計劃

### 單元測試（開發階段）

**覆蓋範圍**: >80%

**重點測試項目**:
- [x] RiskManager.validate_order() - 各種風控規則
- [x] RiskManager.check_stop_loss() - 止損邏輯
- [x] OrderExecutor.submit_order() - 訂單提交流程
- [x] AlertManager.send_alert() - 通知發送
- [x] PerformanceTracker.update_daily_performance() - 績效計算

**測試工具**: pytest, pytest-cov

---

### 整合測試（系統整合階段）

**場景 1: 正常調倉流程**
1. 策略生成信號（10 支股票）
2. 風控驗證通過
3. 自動下單（賣出舊持股、買入新持股）
4. 成交回報接收
5. 績效更新
6. Line 通知發送

**預期結果**: 全流程順利，無錯誤

---

**場景 2: 觸發單股止損**
1. 持股 2330 虧損 -5.5%
2. RiskManager 偵測到止損觸發
3. 自動生成賣出訂單
4. 緊急通知（Line + Telegram + Email）
5. 訂單成交後更新持倉

**預期結果**: 止損機制正常運作，通知及時

---

**場景 3: 組合回撤過大**
1. 組合虧損達 -10.5%
2. 觸發組合止損（減倉 50%）
3. 賣出 5 支股票（保留 5 支）
4. 發送緊急通知
5. 暫停自動交易

**預期結果**: 風控措施生效，損失控制

---

### 壓力測試（部署前階段）

**測試 1: API 延遲測試**
- 模擬券商 API 回應時間 5-10 秒
- 預期：系統能正常處理，不會重複下單

**測試 2: 斷線重連測試**
- 模擬網路斷線 30 秒後重連
- 預期：系統能自動重連，未成交訂單能繼續追蹤

**測試 3: 極端行情測試**
- 模擬大盤暴跌 -8%、單股跌停
- 預期：止損機制正常觸發，緊急通知發送

**測試 4: 資料庫故障測試**
- 模擬 MongoDB 連線失敗
- 預期：系統能降級運行（僅保留核心交易功能），告警通知

---

## 📚 文檔清單

### 技術文檔

1. **系統架構文檔** (`docs/SYSTEM_ARCHITECTURE.md`)
   - 模組設計圖
   - 資料流程圖
   - API 介面規格

2. **API 文檔** (`docs/API_REFERENCE.md`)
   - RiskManager API
   - OrderExecutor API
   - AlertManager API
   - PerformanceTracker API

3. **資料庫設計文檔** (`docs/DATABASE_SCHEMA.md`)
   - trading_orders 集合
   - trading_executions 集合
   - trading_performance 集合

---

### 操作文檔

1. **操作手冊 (SOP)** (`docs/LIVE_TRADING_SOP.md`)
   - 每日操作流程
   - 調倉作業流程
   - 異常處理流程
   - 停機維護流程

2. **風險管理手冊** (`docs/RISK_MANAGEMENT_MANUAL.md`)
   - 風險分級標準
   - 緊急應變計劃
   - 風控檢查清單

3. **部署手冊** (`docs/DEPLOYMENT_GUIDE.md`)
   - 環境配置
   - 券商 API 設定
   - 監控系統設定
   - 備份與災難恢復

---

### 使用者文檔

1. **快速開始指南** (`docs/QUICK_START.md`)
   - 環境安裝
   - 基本配置
   - 第一次執行

2. **FAQ** (`docs/FAQ.md`)
   - 常見問題
   - 故障排除
   - 最佳實踐

---

## ✅ 檢查清單

### 開發完成檢查

**模組開發**:
- [ ] RiskManager 完成（300 行，>80% 測試覆蓋）
- [ ] OrderExecutor 完成（400 行，>80% 測試覆蓋）
- [ ] AlertManager 完成（350 行，Line + Telegram 測試通過）
- [ ] PerformanceTracker 完成（400 行，績效計算驗證）
- [ ] Streamlit Dashboard 完成（即時監控視圖）

**整合測試**:
- [ ] 正常調倉流程測試通過
- [ ] 單股止損測試通過
- [ ] 組合止損測試通過
- [ ] API 整合測試通過（成功率 >95%）
- [ ] 壓力測試通過（4 種場景）

**文檔完成**:
- [ ] 系統架構文檔
- [ ] API 參考文檔
- [ ] 資料庫設計文檔
- [ ] 操作手冊 (SOP)
- [ ] 風險管理手冊
- [ ] 部署手冊

---

### 上線前檢查

**環境檢查**:
- [ ] MongoDB 穩定運行（資料庫備份確認）
- [ ] 券商 API 連線正常（測試帳戶下單成功）
- [ ] Line Notify 設定完成（測試通知成功）
- [ ] Telegram Bot 設定完成（測試互動成功）
- [ ] Email 設定完成（測試郵件成功）

**安全檢查**:
- [ ] API Token 加密存儲
- [ ] 敏感配置不在 Git 版本控制中
- [ ] 防火牆規則設定（僅允許必要連線）
- [ ] SSL 憑證配置（HTTPS 連線）
- [ ] 帳戶權限最小化

**資金檢查**:
- [ ] 券商帳戶資金確認（10-30 萬）
- [ ] 風險預算確認（可接受最大虧損）
- [ ] 止損設定確認（單股 -5%、組合 -10%）
- [ ] 緊急聯絡人資訊更新

**備援檢查**:
- [ ] 備用券商 API 準備完成
- [ ] 手動下單流程演練
- [ ] 資料庫自動備份設定（每日一次）
- [ ] 系統日誌保留設定（保留 90 天）

---

### 紙上交易檢查

**測試前**:
- [ ] 測試環境隔離（不影響正式環境）
- [ ] 模擬交易數據準備（最近 3 個月）
- [ ] 測試計劃制定（測試 10 天，至少 2 次調倉）

**測試中**:
- [ ] 每日記錄測試結果
- [ ] 每日檢查風控機制
- [ ] 每日檢查通知系統
- [ ] 發現問題立即記錄

**測試後**:
- [ ] 測試報告生成（勝率、報酬、Bug 清單）
- [ ] Bug 修正完成（100% 修正率）
- [ ] 性能評估（vs 目標指標）
- [ ] 團隊檢討會議

---

## 📈 成功指標（KPI）

### 短期目標（3 個月，2026-04 ~ 2026-06）

| KPI | 目標 | 實際 | 達成率 |
|-----|------|------|--------|
| 年化報酬 | >20% | ___ | ___ |
| 夏普比率 | >1.5 | ___ | ___ |
| 最大回撤 | <-15% | ___ | ___ |
| 勝率 | >55% | ___ | ___ |
| 系統穩定性 | >99% | ___ | ___ |
| 風控事件 | 0 次 | ___ | ___ |

---

### 中期目標（6 個月，2026-07 ~ 2026-12）

| KPI | 目標 | 實際 | 達成率 |
|-----|------|------|--------|
| 年化報酬 | >25% | ___ | ___ |
| 夏普比率 | >1.8 | ___ | ___ |
| 最大回撤 | <-12% | ___ | ___ |
| 勝率 | >60% | ___ | ___ |
| 追蹤誤差 | <5% | ___ | ___ |
| 客戶滿意度 | >90% | ___ | ___ |

---

### 長期目標（1 年，2027-01 起）

| KPI | 目標 | 實際 | 達成率 |
|-----|------|------|--------|
| 年化報酬 | >30% | ___ | ___ |
| 夏普比率 | >2.0 | ___ | ___ |
| 最大回撤 | <-15% | ___ | ___ |
| 勝率 | >62% | ___ | ___ |
| 資產管理規模 | >500 萬 | ___ | ___ |
| 系統自動化率 | >95% | ___ | ___ |

---

## 🚨 風險聲明

1. **市場風險**: 策略基於 2022-2024 歷史數據優化，未來市場環境可能改變，導致策略失效。

2. **技術風險**: 系統故障、API 斷線、數據錯誤等可能導致交易異常或損失。

3. **流動性風險**: 小型股可能面臨流動性不足，導致無法及時平倉或滑價嚴重。

4. **黑天鵝風險**: 極端事件（如戰爭、金融危機、疫情）可能導致策略大幅虧損。

5. **法律風險**: 注意遵守證券交易法規，避免內線交易、操縱市場等違法行為。

**免責聲明**: 本計劃僅供參考，實際投資應根據個人風險承受能力調整。過去績效不代表未來表現。

---

## 📞 聯絡資訊

**技術負責人**: [待填寫]  
**Email**: [待填寫]  
**緊急聯絡**: [待填寫]  

**券商客服**:
- 富邦證券: 0800-073-588
- 元大證券: 0800-333-338

**系統監控**:
- Streamlit Dashboard: http://localhost:8501
- MongoDB: mongodb://localhost:27017

---

## 📝 附錄

### A. 參考文檔
- [v2 優化報告](results/optimization_results_v2.json)
- [歷史回測報告](reports/historical_backtest_v2.md)
- [v1 vs v2 對比](reports/v1_vs_v2_comparison.txt)

### B. 相關腳本
- [參數驗證](scripts/validate_best_params_v2.py)
- [對比分析](scripts/compare_v1_v2_params.py)
- [歷史回測](scripts/backtest_historical.py)

### C. 技術棧
- Python 3.14
- MongoDB 7.0+
- Streamlit 1.30+
- Line Notify API
- Telegram Bot API

---

**文檔結束** | 最後更新: 2026-02-23
