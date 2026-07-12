#!/usr/bin/env python3
"""
数据库改善任务执行器

根据专业财经系统审计报告，执行以下改善任务:
1. ✅ 补充股利数据 (P0) - 已在后台运行
2. 📊 添加 PE/PB 比率 (P1)
3. 🧹 清理字段冗余 (P2)
4. ✓ 数据验证扫描 (P2)

作者: Professional Financial Systems Architect
日期: 2026-02-21
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, List
import logging

from pymongo import MongoClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class ImprovementTaskManager:
    """改善任务管理器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.scripts_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.tasks = [
            {
                'id': 1,
                'name': '补充股利数据',
                'priority': 'P0',
                'status': 'completed',
                'script': None,
                'description': '下载 2015-2025 历史股利数据 (已在后台运行)'
            },
            {
                'id': 2,
                'name': '添加 PE/PB 比率',
                'priority': 'P1',
                'status': 'pending',
                'script': 'calculate_pe_pb_ratios.py',
                'description': '计算本益比和股价净值比'
            },
            {
                'id': 3,
                'name': '清理字段冗余',
                'priority': 'P2',
                'status': 'pending',
                'script': 'cleanup_field_redundancy.py',
                'description': '删除 tickers 中的 close 和 volume 字段'
            },
            {
                'id': 4,
                'name': '数据验证扫描',
                'priority': 'P2',
                'status': 'pending',
                'script': 'add_data_validation.py',
                'description': '扫描并标记异常数据'
            }
        ]
    
    def print_header(self):
        """打印标题"""
        logger.info('\n' + '=' * 70)
        logger.info('  数据库改善任务执行器')
        logger.info('  Database Improvement Task Executor')
        logger.info('=' * 70)
    
    def check_database_status(self):
        """检查数据库当前状态"""
        logger.info('\n【当前数据库状态】')
        logger.info('-' * 70)
        
        # 股利数据
        dividend_count = self.db.dividend_results.count_documents({})
        ticker_count = self.db.tickers.count_documents({})
        dividend_coverage = (dividend_count / ticker_count * 100) if ticker_count > 0 else 0
        
        logger.info(f'股利数据: {dividend_count:,} 笔 ({dividend_coverage:.1f}% 覆盖)')
        
        # PE/PB 字段
        has_pe = self.db.tickers.count_documents({'peRatio': {'$exists': True}})
        has_pb = self.db.tickers.count_documents({'pbRatio': {'$exists': True}})
        
        logger.info(f'PE 字段: {has_pe:,}/{ticker_count:,} ({has_pe/ticker_count*100:.1f}%)')
        logger.info(f'PB 字段: {has_pb:,}/{ticker_count:,} ({has_pb/ticker_count*100:.1f}%)')
        
        # 字段冗余
        sample = self.db.tickers.find_one({})
        has_close = 'close' in sample if sample else False
        has_volume = 'volume' in sample if sample else False
        
        logger.info(f'字段冗余: close={has_close}, volume={has_volume}')
        
        # ROE/ROA
        financial_count = self.db.financial_reports.count_documents({})
        has_roe = self.db.financial_reports.count_documents({'ratios.roe': {'$exists': True}})
        
        logger.info(f'ROE 字段: {has_roe:,}/{financial_count:,} ({has_roe/financial_count*100:.1f}%)')
        
        logger.info('-' * 70)
    
    def print_task_list(self):
        """打印任务列表"""
        logger.info('\n【待执行任务】')
        logger.info('-' * 70)
        
        for task in self.tasks:
            status_icon = {
                'completed': '✅',
                'running': '🔄',
                'pending': '⏳',
                'failed': '❌'
            }.get(task['status'], '❓')
            
            logger.info(f'{status_icon} [{task["priority"]}] {task["name"]}')
            logger.info(f'   {task["description"]}')
            if task['script']:
                logger.info(f'   脚本: {task["script"]}')
        
        logger.info('-' * 70)
    
    def run_script(self, script_name: str) -> bool:
        """执行脚本"""
        script_path = os.path.join(self.scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            logger.error(f'脚本不存在: {script_path}')
            return False
        
        logger.info(f'\n执行脚本: {script_name}')
        logger.info('=' * 70)
        
        try:
            # 执行脚本
            start_time = time.time()
            
            result = subprocess.run(
                ['python3', script_path],
                cwd=self.scripts_dir,
                capture_output=False,  # 显示实时输出
                text=True
            )
            
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                logger.info(f'✅ 脚本执行成功 (耗时: {elapsed:.1f}秒)')
                return True
            else:
                logger.error(f'❌ 脚本执行失败 (返回码: {result.returncode})')
                return False
        
        except Exception as e:
            logger.error(f'❌ 脚本执行异常: {e}')
            return False
    
    def execute_tasks(self, task_ids: List[int] = None):
        """执行任务"""
        if task_ids is None:
            # 执行所有待处理任务
            tasks_to_run = [t for t in self.tasks if t['status'] == 'pending']
        else:
            # 执行指定任务
            tasks_to_run = [t for t in self.tasks if t['id'] in task_ids]
        
        if not tasks_to_run:
            logger.info('\n✅ 无待执行任务')
            return True
        
        logger.info(f'\n准备执行 {len(tasks_to_run)} 个任务...')
        
        results = []
        
        for task in tasks_to_run:
            if not task['script']:
                logger.info(f'\n⏭️  跳过任务: {task["name"]} (无脚本)')
                continue
            
            logger.info(f'\n▶️  开始任务 {task["id"]}: {task["name"]}')
            
            task['status'] = 'running'
            success = self.run_script(task['script'])
            
            if success:
                task['status'] = 'completed'
                results.append((task['name'], True))
            else:
                task['status'] = 'failed'
                results.append((task['name'], False))
            
            # 等待一下
            time.sleep(1)
        
        # 打印执行摘要
        logger.info('\n' + '=' * 70)
        logger.info('执行摘要')
        logger.info('=' * 70)
        
        for task_name, success in results:
            status = '✅ 成功' if success else '❌ 失败'
            logger.info(f'{status}: {task_name}')
        
        success_count = sum(1 for _, s in results if s)
        total_count = len(results)
        
        logger.info('-' * 70)
        logger.info(f'完成: {success_count}/{total_count} 个任务')
        
        return success_count == total_count
    
    def run_all(self):
        """执行所有任务"""
        self.print_header()
        self.check_database_status()
        self.print_task_list()
        
        # 询问用户确认
        logger.info('\n准备执行所有待处理任务...')
        
        # 自动执行（无需用户输入）
        success = self.execute_tasks()
        
        # 再次检查状态
        logger.info('\n')
        self.check_database_status()
        
        if success:
            logger.info('\n✅ 所有改善任务执行完成!')
        else:
            logger.warning('\n⚠️  部分任务执行失败，请查看日志')
        
        return success
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()


def main():
    """主函数"""
    try:
        manager = ImprovementTaskManager()
        success = manager.run_all()
        manager.close()
        
        return 0 if success else 1
    
    except KeyboardInterrupt:
        logger.info('\n\n用户中断')
        return 130
    
    except Exception as e:
        logger.error(f'执行失败: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
