#!/usr/bin/env python3
"""
Portfolio 模組 - 投資組合管理

功能:
- 管理現金與持倉
- 記錄交易歷史
- 計算權益曲線
- 支持多標的投資組合
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
import logging


@dataclass
class Position:
    """持倉資訊"""
    symbol: str
    shares: int
    avg_price: float
    entry_date: datetime
    
    @property
    def cost(self) -> float:
        """成本"""
        return self.shares * self.avg_price
    
    def market_value(self, current_price: float) -> float:
        """市值"""
        return self.shares * current_price
    
    def profit_loss(self, current_price: float) -> float:
        """未實現損益"""
        return self.market_value(current_price) - self.cost
    
    def profit_loss_pct(self, current_price: float) -> float:
        """未實現報酬率 (%)"""
        if self.cost == 0:
            return 0.0
        return (self.profit_loss(current_price) / self.cost) * 100


@dataclass
class Trade:
    """交易記錄"""
    date: datetime
    symbol: str
    action: str  # 'BUY' or 'SELL'
    shares: int
    price: float
    commission: float = 0.0
    
    @property
    def total_cost(self) -> float:
        """總成本（含手續費）"""
        base = self.shares * self.price
        return base + self.commission if self.action == 'BUY' else base - self.commission


class Portfolio:
    """
    投資組合管理
    
    參數:
        initial_cash: 初始資金
        commission_rate: 手續費率（default: 0.001425，台股證交稅+手續費約 0.3%）
    """
    
    def __init__(self, initial_cash: float = 1_000_000, commission_rate: float = 0.003):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        
        # 持倉
        self.positions: Dict[str, Position] = {}
        
        # 交易歷史
        self.trades: List[Trade] = []
        
        # 權益曲線
        self.equity_curve: List[Dict] = []
        
        self.logger = logging.getLogger(__name__)
    
    def buy(self, date: datetime, symbol: str, shares: int, price: float) -> bool:
        """
        買入股票
        
        Returns:
            bool: 是否成功執行
        """
        cost = shares * price
        commission = cost * self.commission_rate
        total_cost = cost + commission
        
        # 檢查現金是否充足
        if self.cash < total_cost:
            self.logger.warning(f"{date} 現金不足: 需要 {total_cost:.2f}, 可用 {self.cash:.2f}")
            return False
        
        # 扣除現金
        self.cash -= total_cost
        
        # 更新持倉
        if symbol in self.positions:
            # 已有持倉，計算平均成本
            old_pos = self.positions[symbol]
            total_shares = old_pos.shares + shares
            total_cost_basis = old_pos.cost + cost
            avg_price = total_cost_basis / total_shares
            
            self.positions[symbol] = Position(
                symbol=symbol,
                shares=total_shares,
                avg_price=avg_price,
                entry_date=old_pos.entry_date
            )
        else:
            # 新建持倉
            self.positions[symbol] = Position(
                symbol=symbol,
                shares=shares,
                avg_price=price,
                entry_date=date
            )
        
        # 記錄交易
        trade = Trade(
            date=date,
            symbol=symbol,
            action='BUY',
            shares=shares,
            price=price,
            commission=commission
        )
        self.trades.append(trade)
        
        self.logger.info(f"{date} 買入 {symbol}: {shares}股 @ {price:.2f}, 成本 {total_cost:.2f}")
        return True
    
    def sell(self, date: datetime, symbol: str, shares: int, price: float) -> bool:
        """
        賣出股票
        
        Returns:
            bool: 是否成功執行
        """
        # 檢查持倉
        if symbol not in self.positions:
            self.logger.warning(f"{date} 無持倉: {symbol}")
            return False
        
        position = self.positions[symbol]
        if position.shares < shares:
            self.logger.warning(f"{date} 持股不足: {symbol} 持有 {position.shares}, 欲賣 {shares}")
            return False
        
        # 計算收入
        revenue = shares * price
        commission = revenue * self.commission_rate
        net_revenue = revenue - commission
        
        # 增加現金
        self.cash += net_revenue
        
        # 更新持倉
        if position.shares == shares:
            # 全部賣出
            del self.positions[symbol]
        else:
            # 部分賣出
            position.shares -= shares
        
        # 記錄交易
        trade = Trade(
            date=date,
            symbol=symbol,
            action='SELL',
            shares=shares,
            price=price,
            commission=commission
        )
        self.trades.append(trade)
        
        profit = (price - position.avg_price) * shares - commission
        self.logger.info(f"{date} 賣出 {symbol}: {shares}股 @ {price:.2f}, 收入 {net_revenue:.2f}, 損益 {profit:.2f}")
        return True
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """取得持倉資訊"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """是否持有該股票"""
        return symbol in self.positions
    
    def total_market_value(self, prices: Dict[str, float]) -> float:
        """
        計算持倉總市值
        
        Args:
            prices: {symbol: current_price} 字典
        """
        total = 0.0
        for symbol, position in self.positions.items():
            if symbol in prices:
                total += position.market_value(prices[symbol])
        return total
    
    def total_equity(self, prices: Dict[str, float]) -> float:
        """
        計算總權益（現金 + 持倉市值）
        
        Args:
            prices: {symbol: current_price} 字典
        """
        return self.cash + self.total_market_value(prices)
    
    def record_equity(self, date: datetime, prices: Dict[str, float]):
        """
        記錄權益曲線
        
        Args:
            date: 日期
            prices: {symbol: current_price} 字典
        """
        market_value = self.total_market_value(prices)
        equity = self.cash + market_value
        
        self.equity_curve.append({
            'date': date,
            'cash': self.cash,
            'market_value': market_value,
            'equity': equity,
            'positions': len(self.positions)
        })
    
    def get_returns(self) -> float:
        """
        計算總報酬率 (%)
        """
        if not self.equity_curve:
            return 0.0
        
        final_equity = self.equity_curve[-1]['equity']
        if self.initial_cash == 0:
            return 0.0
        
        return ((final_equity - self.initial_cash) / self.initial_cash) * 100
    
    def summary(self) -> Dict:
        """組合摘要"""
        return {
            'initial_cash': self.initial_cash,
            'current_cash': self.cash,
            'positions_count': len(self.positions),
            'trades_count': len(self.trades),
            'equity_records': len(self.equity_curve)
        }
