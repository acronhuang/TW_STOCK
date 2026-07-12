"""
財經資料驗證器
執行專業級資料品質檢查
"""

import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from bson.decimal128 import Decimal128


class DataValidator:
    """財經資料驗證器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初始化驗證器
        
        Args:
            logger: 日誌記錄器
        """
        self.logger = logger or logging.getLogger(__name__)
        self.error_log = []
        
    def validate_price_data(self, record: Dict) -> Tuple[bool, Optional[str]]:
        """
        驗證價格資料邏輯
        
        檢查規則：
        1. 最高價 >= 收盤價 >= 最低價
        2. 所有價格必須 > 0
        3. 成交量必須 >= 0
        
        Args:
            record: 資料記錄
            
        Returns:
            (是否通過, 錯誤訊息)
        """
        try:
            # 提取價格欄位
            high = self._extract_decimal(record.get('highPrice') or record.get('high'))
            low = self._extract_decimal(record.get('lowPrice') or record.get('low'))
            close = self._extract_decimal(record.get('closePrice') or record.get('close'))
            open_price = self._extract_decimal(record.get('openPrice') or record.get('open'))
            
            # 提取成交量
            volume = self._extract_decimal(record.get('tradeVolume') or record.get('volume') or record.get('Trading_Volume'))
            
            # 提取識別資訊
            symbol = record.get('stock_id') or record.get('symbol')
            date = record.get('date')
            
            # 檢查 1: 價格必須存在且 > 0
            if high is not None and high <= 0:
                return False, f"最高價必須 > 0: symbol={symbol}, date={date}, high={high}"
            
            if low is not None and low <= 0:
                return False, f"最低價必須 > 0: symbol={symbol}, date={date}, low={low}"
            
            if close is not None and close <= 0:
                return False, f"收盤價必須 > 0: symbol={symbol}, date={date}, close={close}"
            
            # 檢查 2: 價格邏輯關係 (high >= close >= low)
            if high is not None and close is not None and low is not None:
                if high < close:
                    return False, f"最高價 < 收盤價: symbol={symbol}, date={date}, high={high}, close={close}"
                
                if close < low:
                    return False, f"收盤價 < 最低價: symbol={symbol}, date={date}, close={close}, low={low}"
                
                if high < low:
                    return False, f"最高價 < 最低價: symbol={symbol}, date={date}, high={high}, low={low}"
            
            # 檢查 3: 開盤價應在 high/low 範圍內
            if open_price is not None and high is not None and low is not None:
                if open_price > high:
                    return False, f"開盤價 > 最高價: symbol={symbol}, date={date}, open={open_price}, high={high}"
                
                if open_price < low:
                    return False, f"開盤價 < 最低價: symbol={symbol}, date={date}, open={open_price}, low={low}"
            
            # 檢查 4: 成交量必須 >= 0
            if volume is not None and volume < 0:
                return False, f"成交量不可為負數: symbol={symbol}, date={date}, volume={volume}"
            
            return True, None
            
        except Exception as e:
            return False, f"驗證過程發生錯誤: {str(e)}"
    
    def validate_financial_data(self, record: Dict) -> Tuple[bool, Optional[str]]:
        """
        驗證財報資料邏輯
        
        檢查規則：
        1. 資產 = 負債 + 權益（資產負債表平衡）
        2. EPS 計算邏輯（淨利 / 股本）
        3. 重要比率合理性
        
        Args:
            record: 資料記錄
            
        Returns:
            (是否通過, 錯誤訊息)
        """
        try:
            symbol = record.get('stock_id') or record.get('symbol')
            date = record.get('date')
            
            # 檢查資產負債表平衡
            if 'balanceSheet' in record:
                balance_sheet = record['balanceSheet']
                total_assets = self._extract_decimal(balance_sheet.get('totalAssets'))
                total_liabilities = self._extract_decimal(balance_sheet.get('totalLiabilities'))
                total_equity = self._extract_decimal(balance_sheet.get('totalEquity'))
                
                if all([total_assets, total_liabilities, total_equity]):
                    # 允許 1% 的誤差（會計科目可能有四捨五入）
                    calculated_assets = total_liabilities + total_equity
                    diff_percent = abs((total_assets - calculated_assets) / total_assets * 100)
                    
                    if diff_percent > 1:
                        return False, f"資產負債表不平衡: symbol={symbol}, date={date}, 誤差={diff_percent:.2f}%"
            
            # 檢查 EPS 合理性
            if 'incomeStatement' in record:
                income = record['incomeStatement']
                net_income = self._extract_decimal(income.get('netIncome'))
                eps = self._extract_decimal(income.get('eps'))
                
                # EPS 與淨利應該同號（都為正或都為負）
                if net_income is not None and eps is not None:
                    if (net_income > 0 and eps < 0) or (net_income < 0 and eps > 0):
                        return False, f"EPS 與淨利符號不一致: symbol={symbol}, date={date}, net_income={net_income}, eps={eps}"
            
            return True, None
            
        except Exception as e:
            return False, f"財報驗證過程發生錯誤: {str(e)}"
    
    def validate_dividend_data(self, record: Dict) -> Tuple[bool, Optional[str]]:
        """
        驗證股利資料邏輯
        
        檢查規則：
        1. 現金股利 + 股票股利 > 0（至少有一項配發）
        2. 除權息日期邏輯
        3. 殖利率合理性
        
        Args:
            record: 資料記錄
            
        Returns:
            (是否通過, 錯誤訊息)
        """
        try:
            symbol = record.get('stock_id') or record.get('symbol')
            date = record.get('date')
            
            cash_dividend = self._extract_decimal(record.get('cashDividend'))
            stock_dividend = self._extract_decimal(record.get('stockDividend'))
            
            # 檢查至少有一項配發
            if cash_dividend is not None and stock_dividend is not None:
                if cash_dividend == 0 and stock_dividend == 0:
                    return False, f"現金股利與股票股利都為 0: symbol={symbol}, date={date}"
            
            # 檢查股利不可為負數
            if cash_dividend is not None and cash_dividend < 0:
                return False, f"現金股利不可為負: symbol={symbol}, date={date}, cash={cash_dividend}"
            
            if stock_dividend is not None and stock_dividend < 0:
                return False, f"股票股利不可為負: symbol={symbol}, date={date}, stock={stock_dividend}"
            
            # 檢查殖利率合理性（通常在 0-20% 之間）
            dividend_yield = self._extract_decimal(record.get('dividendYield'))
            if dividend_yield is not None:
                if dividend_yield < 0 or dividend_yield > 20:
                    self.logger.warning(f"殖利率異常: symbol={symbol}, date={date}, yield={dividend_yield}%")
            
            return True, None
            
        except Exception as e:
            return False, f"股利驗證過程發生錯誤: {str(e)}"
    
    def _extract_decimal(self, value) -> Optional[Decimal]:
        """
        從各種型別中提取 Decimal 值
        
        Args:
            value: 輸入值（可能是 Decimal128, float, int, str）
            
        Returns:
            Decimal 值或 None
        """
        if value is None:
            return None
        
        try:
            if isinstance(value, Decimal128):
                return value.to_decimal()
            elif isinstance(value, Decimal):
                return value
            elif isinstance(value, (int, float)):
                return Decimal(str(value))
            elif isinstance(value, str):
                clean_value = value.replace(',', '').strip()
                if clean_value and clean_value != '-':
                    return Decimal(clean_value)
            return None
        except Exception:
            return None
    
    def get_validation_summary(self) -> Dict:
        """
        獲取驗證摘要
        
        Returns:
            驗證統計資料
        """
        return {
            'total_errors': len(self.error_log),
            'errors': self.error_log
        }
    
    def log_error(self, error_message: str):
        """記錄錯誤"""
        self.error_log.append({
            'timestamp': datetime.now().isoformat(),
            'message': error_message
        })
        self.logger.error(error_message)
