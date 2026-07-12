"""
下載進度管理器
實現斷點續傳、智能跳過、API 配額管理
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Optional


class ProgressManager:
    """管理下載進度，實現續傳功能"""
    
    def __init__(self, progress_file: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        """
        初始化進度管理器
        
        Args:
            progress_file: 進度檔案路徑
            logger: 日誌記錄器
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # 預設進度檔案路徑
        if progress_file is None:
            project_root = Path(__file__).parent.parent.parent
            progress_file = project_root / "logs" / "download_progress.json"
        
        self.progress_file = progress_file
        self.progress = self._load_progress()
    
    def _load_progress(self) -> Dict:
        """載入進度檔案"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.logger.info(f"✅ 載入進度檔案: {self.progress_file}")
                    return data
            except Exception as e:
                self.logger.warning(f"⚠️  進度檔案載入失敗: {e}")
        
        # 預設結構
        return {
            "last_update": None,
            "completed_tables": [],  # 已完成的表
            "current_table": None,  # 當前處理的表
            "processed_stocks": {},  # {table_name: [stock_ids]}
            "failed_stocks": {},  # {table_name: {stock_id: reason}}
            "blacklist": [],  # 已知無數據的股票（如 ETF）
            "api_usage": {
                "count": 0,
                "quota": 600,
                "reset_time": None
            }
        }
    
    def save_progress(self):
        """保存進度到檔案"""
        try:
            self.progress["last_update"] = datetime.now().isoformat()
            self.progress_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress, indent=2, ensure_ascii=False, fp=f)
            
            self.logger.debug(f"💾 進度已保存")
        except Exception as e:
            self.logger.error(f"❌ 進度保存失敗: {e}")
    
    def is_table_completed(self, table_name: str) -> bool:
        """檢查資料表是否已完成"""
        return table_name in self.progress["completed_tables"]
    
    def mark_table_completed(self, table_name: str):
        """標記資料表已完成"""
        if table_name not in self.progress["completed_tables"]:
            self.progress["completed_tables"].append(table_name)
            self.logger.info(f"✅ 標記完成: {table_name}")
        self.save_progress()
    
    def set_current_table(self, table_name: str):
        """設定當前處理的表"""
        self.progress["current_table"] = table_name
        if table_name not in self.progress["processed_stocks"]:
            self.progress["processed_stocks"][table_name] = []
        if table_name not in self.progress["failed_stocks"]:
            self.progress["failed_stocks"][table_name] = {}
        self.save_progress()
    
    def is_stock_processed(self, table_name: str, stock_id: str) -> bool:
        """檢查股票是否已處理"""
        if table_name not in self.progress["processed_stocks"]:
            return False
        return stock_id in self.progress["processed_stocks"][table_name]
    
    def mark_stock_processed(self, table_name: str, stock_id: str):
        """標記股票已處理"""
        if table_name not in self.progress["processed_stocks"]:
            self.progress["processed_stocks"][table_name] = []
        
        if stock_id not in self.progress["processed_stocks"][table_name]:
            self.progress["processed_stocks"][table_name].append(stock_id)
    
    def mark_stock_failed(self, table_name: str, stock_id: str, reason: str):
        """標記股票處理失敗"""
        if table_name not in self.progress["failed_stocks"]:
            self.progress["failed_stocks"][table_name] = {}
        
        self.progress["failed_stocks"][table_name][stock_id] = {
            "reason": reason,
            "time": datetime.now().isoformat()
        }
    
    def add_to_blacklist(self, stock_id: str, reason: str = "無財報數據"):
        """加入黑名單（ETF、無數據股票等）"""
        if stock_id not in self.progress["blacklist"]:
            self.progress["blacklist"].append(stock_id)
            self.logger.debug(f"🚫 加入黑名單: {stock_id} ({reason})")
    
    def is_blacklisted(self, stock_id: str) -> bool:
        """檢查是否在黑名單中"""
        return stock_id in self.progress["blacklist"]
    
    def should_skip_stock(self, stock_id: str) -> bool:
        """判斷是否應該跳過該股票"""
        # ETF 判斷（00XX 開頭，後面可能有 L/R/K 等）
        if stock_id.startswith('00') and len(stock_id) >= 6:
            base = stock_id[:5]  # 取前 5 碼
            if base.isdigit():
                return True
        
        # 檢查黑名單
        if self.is_blacklisted(stock_id):
            return True
        
        return False
    
    def get_processed_count(self, table_name: str) -> int:
        """取得已處理的股票數"""
        if table_name not in self.progress["processed_stocks"]:
            return 0
        return len(self.progress["processed_stocks"][table_name])
    
    def get_resume_info(self) -> Dict:
        """取得續傳資訊"""
        current = self.progress.get("current_table")
        if not current:
            return {"can_resume": False}
        
        return {
            "can_resume": True,
            "current_table": current,
            "processed_count": self.get_processed_count(current),
            "completed_tables": len(self.progress["completed_tables"]),
            "blacklist_count": len(self.progress["blacklist"])
        }
    
    def reset_progress(self, keep_blacklist: bool = True):
        """重置進度（可選保留黑名單）"""
        blacklist = self.progress["blacklist"] if keep_blacklist else []
        
        self.progress = {
            "last_update": None,
            "completed_tables": [],
            "current_table": None,
            "processed_stocks": {},
            "failed_stocks": {},
            "blacklist": blacklist,
            "api_usage": {
                "count": 0,
                "quota": 600,
                "reset_time": None
            }
        }
        self.save_progress()
        self.logger.info(f"🔄 進度已重置{'（保留黑名單）' if keep_blacklist else ''}")
    
    def update_api_usage(self, count: int, quota: int = 600):
        """更新 API 使用量"""
        self.progress["api_usage"]["count"] = count
        self.progress["api_usage"]["quota"] = quota
        self.progress["api_usage"]["reset_time"] = (
            datetime.now().replace(minute=0, second=0, microsecond=0)
            .replace(hour=datetime.now().hour + 1)
            .isoformat()
        )
    
    def print_summary(self):
        """列印進度摘要"""
        resume_info = self.get_resume_info()
        
        print("\n" + "="*80)
        print("📊 下載進度摘要")
        print("="*80)
        
        if resume_info["can_resume"]:
            print(f"▶️  當前表: {resume_info['current_table']}")
            print(f"✅ 已完成表: {resume_info['completed_tables']} 個")
            print(f"📝 已處理股票: {resume_info['processed_count']} 支")
            print(f"🚫 黑名單: {resume_info['blacklist_count']} 支（ETF/無數據）")
        else:
            print("尚未開始下載")
        
        if self.progress["last_update"]:
            print(f"⏰ 最後更新: {self.progress['last_update']}")
        
        print("="*80 + "\n")
