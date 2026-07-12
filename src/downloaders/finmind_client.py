"""
FinMind API 客戶端基類
處理 API 請求、速率限制、錯誤重試
"""

import requests
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
from bson.decimal128 import Decimal128
from decimal import Decimal


class FinMindClient:
    """FinMind API 客戶端"""
    
    def __init__(self, api_token: str, logger: Optional[logging.Logger] = None):
        """
        初始化 FinMind 客戶端
        
        Args:
            api_token: FinMind API Token
            logger: 日誌記錄器
        """
        self.api_token = api_token
        self.api_base_url = "https://api.finmindtrade.com/api/v4/data"
        self.api_call_count = 0
        self.api_quota_per_hour = 600  # 付費版配額
        self.logger = logger or logging.getLogger(__name__)
        
        # 重試設定
        self.max_retries = 3
        self.retry_delay = 2  # 秒
        self.backoff_factor = 2  # 指數退避係數
        
    def fetch_data(self, dataset: str, params: Dict, retry_count: int = 0) -> List[Dict]:
        """
        從 FinMind API 獲取資料（帶重試機制）
        
        Args:
            dataset: 資料集名稱
            params: 請求參數
            retry_count: 當前重試次數
            
        Returns:
            資料列表
        """
        if self.api_call_count >= self.api_quota_per_hour - 10:
            self.logger.warning(f"⚠️  API 配額接近上限 ({self.api_call_count}/{self.api_quota_per_hour})")
            return []
        
        try:
            all_params = {
                "dataset": dataset,
                "token": self.api_token,
                **params
            }
            
            self.logger.debug(f"API 請求: {dataset}, 參數: {params}")
            response = requests.get(self.api_base_url, params=all_params, timeout=30)
            self.api_call_count += 1
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 200:
                    raw_data = data.get('data', [])
                    # 轉換數值為 Decimal128
                    converted_data = self._convert_to_decimal128(raw_data)
                    self.logger.debug(f"✅ 成功獲取 {len(converted_data)} 筆資料")
                    return converted_data
                    
                elif data.get('status') == 429:  # Rate limit
                    self.logger.warning(f"⚠️  速率限制: {data.get('msg')}")
                    if retry_count < self.max_retries:
                        wait_time = self.retry_delay * (self.backoff_factor ** retry_count)
                        self.logger.info(f"等待 {wait_time} 秒後重試...")
                        time.sleep(wait_time)
                        return self.fetch_data(dataset, params, retry_count + 1)
                    return []
                    
                else:
                    self.logger.warning(f"API 回應異常: 狀態={data.get('status')}, 訊息={data.get('msg')}")
                    return []
                    
            elif response.status_code == 429:  # HTTP Rate limit
                if retry_count < self.max_retries:
                    wait_time = self.retry_delay * (self.backoff_factor ** retry_count)
                    self.logger.warning(f"HTTP 429: 等待 {wait_time} 秒後重試...")
                    time.sleep(wait_time)
                    return self.fetch_data(dataset, params, retry_count + 1)
                else:
                    self.logger.error(f"HTTP 429: 已達最大重試次數 ({self.max_retries})")
                    return []
            
            elif response.status_code == 400:  # HTTP Bad Request - 不需要重試
                self.logger.error(f"HTTP 400: 請求參數錯誤（可能不支持此股票代碼）")
                return []
                    
            else:
                self.logger.error(f"HTTP 錯誤: {response.status_code}")
                if retry_count < self.max_retries:
                    wait_time = self.retry_delay * (self.backoff_factor ** retry_count)
                    time.sleep(wait_time)
                    return self.fetch_data(dataset, params, retry_count + 1)
                return []
                
        except requests.exceptions.Timeout:
            self.logger.error(f"請求超時")
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (self.backoff_factor ** retry_count)
                self.logger.info(f"等待 {wait_time} 秒後重試...")
                time.sleep(wait_time)
                return self.fetch_data(dataset, params, retry_count + 1)
            return []
            
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"連線錯誤: {e}")
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (self.backoff_factor ** retry_count)
                time.sleep(wait_time)
                return self.fetch_data(dataset, params, retry_count + 1)
            return []
            
        except Exception as e:
            self.logger.error(f"未預期錯誤: {type(e).__name__}: {e}")
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self.fetch_data(dataset, params, retry_count + 1)
            return []
    
    def _convert_to_decimal128(self, data: List[Dict]) -> List[Dict]:
        """
        將數值欄位轉換為 Decimal128
        
        Args:
            data: 原始資料
            
        Returns:
            轉換後的資料
        """
        # 需要轉換的數值欄位（價格、金額、百分比等）
        numeric_fields = [
            'open', 'high', 'low', 'close', 'price',
            'closePrice', 'openPrice', 'highPrice', 'lowPrice',
            'amount', 'volume', 'tradeVolume', 'Trading_Volume',
            'Trading_money', 'spread', 'change', 'changePercent',
            'revenue', 'profit', 'eps', 'roe', 'roa',
            'dividend', 'yield', 'per', 'pbr', 'value'
        ]
        
        converted_data = []
        for record in data:
            converted_record = {}
            for key, value in record.items():
                if key in numeric_fields and value is not None and value != '':
                    try:
                        # 轉換為 Decimal128
                        if isinstance(value, (int, float)):
                            converted_record[key] = Decimal128(Decimal(str(value)))
                        elif isinstance(value, str):
                            # 移除逗號和空格
                            clean_value = value.replace(',', '').strip()
                            if clean_value and clean_value != '-':
                                converted_record[key] = Decimal128(Decimal(clean_value))
                            else:
                                converted_record[key] = None
                        else:
                            converted_record[key] = value
                    except Exception as e:
                        self.logger.warning(f"轉換失敗 {key}={value}: {e}")
                        converted_record[key] = value
                else:
                    converted_record[key] = value
            
            converted_data.append(converted_record)
        
        return converted_data
    
    def get_api_usage(self) -> Dict:
        """
        獲取 API 使用統計
        
        Returns:
            使用統計資料
        """
        return {
            'call_count': self.api_call_count,
            'quota': self.api_quota_per_hour,
            'remaining': self.api_quota_per_hour - self.api_call_count,
            'usage_percent': round(self.api_call_count / self.api_quota_per_hour * 100, 2)
        }
    
    def reset_call_count(self):
        """重置 API 調用計數"""
        self.api_call_count = 0
        self.logger.info("API 調用計數已重置")
