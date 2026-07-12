"""
MoE Router — 依問題類型路由到專家模型

4 個專家：
  qwen3.6:27b         主推理（Router + 兜底）
  deepseek-r1:14b     數字計算（DCF / VaR / 杜邦）
  qwen2.5-coder:7b    程式生成（SQL / Python）
  nomic-embed-text    向量化（情緒 / RAG）
  (看圖/型態 → SenVision 蔡森演算法，非 LLM)

使用：
    from src.moe.router import MoERouter
    r = MoERouter()
    answer = r.ask("計算 1108 幸福的 DCF 估值")
"""

from __future__ import annotations
import re
import time
import logging
from typing import Optional, Dict, List
import requests

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  專家定義
# ─────────────────────────────────────────────────────────
EXPERTS = {
    'reasoning': {
        'model': 'qwen3.6:27b',
        'vram_gb': 17,
        'description': '主推理引擎（複雜分析、投資決策）',
        'priority': 2,
    },
    'math': {
        'model': 'deepseek-r1:14b',
        'vram_gb': 12,
        'description': '數字計算（DCF / 杜邦 / Sharpe）',
        'priority': 4,
    },
    'code': {
        'model': 'qwen2.5-coder:7b',
        'vram_gb': 7,
        'description': '程式生成（SQL / Python）',
        'priority': 3,
    },
    # 'vision' 已移除：看圖/型態改用 SenVision 蔡森演算法(精準、不幻覺)，餵 technical-analyst
    'embed': {
        'model': 'nomic-embed-text',
        'vram_gb': 1,
        'description': '向量化（情緒 / RAG）',
        'priority': 1,
    },
}


# ─────────────────────────────────────────────────────────
#  路由規則（關鍵字 → 專家）
# ─────────────────────────────────────────────────────────
ROUTING_RULES = [
    # 註：圖/K線/型態 不再路由到 vision LLM；改由 SenVision 蔡森演算法處理(非本router)
    # 程式：SQL/Python 生成
    ('code',      r'SQL|查詢|寫.*程式|寫.*函數|code|腳本|script|pandas|MongoDB query'),
    # 計算：估值/數字推理
    ('math',      r'DCF|DDM|估值|Sharpe|VaR|CVaR|杜邦|計算|多少|現值|折現|計算ROE|預期報酬'),
    # 向量：情緒/相似度
    ('embed',     r'embed|向量|相似|RAG|語意|sentiment.*vector'),
]


# ─────────────────────────────────────────────────────────
#  GPU Manager（簡化版：用 ollama API 直接載入/卸載）
# ─────────────────────────────────────────────────────────
class GPUManager:
    """簡化版 GPU 管理 — 透過 ollama 內建管理機制"""

    OLLAMA_URL = 'http://172.16.9.27:11434'

    def __init__(self, max_vram_gb: float = 48):
        self.max_vram_gb = max_vram_gb
        self.loaded: Dict[str, float] = {}  # model → vram

    def request(self, model: str, vram_gb: float) -> bool:
        """請求載入模型"""
        if model in self.loaded:
            return True

        used = sum(self.loaded.values())
        if used + vram_gb <= self.max_vram_gb:
            self.loaded[model] = vram_gb
            return True

        # 不夠 → 踢低權重
        self._evict_low_priority(vram_gb)
        if sum(self.loaded.values()) + vram_gb <= self.max_vram_gb:
            self.loaded[model] = vram_gb
            return True
        return False

    def _evict_low_priority(self, need_gb: float):
        """踢出低優先級模型（保留 priority<=2 的常駐）"""
        # 找到所有非常駐模型
        evictable = []
        for loaded_model in list(self.loaded.keys()):
            for spec in EXPERTS.values():
                if spec['model'] == loaded_model and spec.get('priority', 5) > 2:
                    evictable.append((loaded_model, spec.get('priority', 5)))
                    break
        # 按優先級高的踢起（priority 數字大 = 低優先）
        evictable.sort(key=lambda x: -x[1])
        for model, _ in evictable:
            self.unload(model)
            if self.max_vram_gb - sum(self.loaded.values()) >= need_gb:
                break

    def unload(self, model: str):
        """卸載模型（透過 ollama 設 keep_alive=0）"""
        try:
            requests.post(f'{self.OLLAMA_URL}/api/generate',
                          json={'model': model, 'prompt': '', 'keep_alive': 0},
                          timeout=5)
        except Exception:
            pass
        self.loaded.pop(model, None)

    def status(self) -> Dict:
        return {
            'loaded': self.loaded,
            'used_gb': sum(self.loaded.values()),
            'max_gb': self.max_vram_gb,
            'free_gb': self.max_vram_gb - sum(self.loaded.values()),
        }


# ─────────────────────────────────────────────────────────
#  MoE Router
# ─────────────────────────────────────────────────────────
class MoERouter:
    """路由問題 → 專家模型 → 取得回答"""

    OLLAMA_URL = 'http://172.16.9.27:11434'

    def __init__(self, max_vram_gb: float = 48):
        self.gpu = GPUManager(max_vram_gb=max_vram_gb)

    def route(self, question: str) -> str:
        """根據問題決定用哪個專家"""
        for expert, pattern in ROUTING_RULES:
            if re.search(pattern, question, re.IGNORECASE):
                logger.info(f'路由 → {expert} ({EXPERTS[expert]["model"]})')
                return expert
        logger.info(f'路由 → reasoning (預設)')
        return 'reasoning'

    def ask(self,
            question: str,
            expert: Optional[str] = None,
            stream: bool = False) -> str:
        """送問題給專家。expert=None 時自動路由。"""
        if expert is None:
            expert = self.route(question)

        spec = EXPERTS[expert]
        model = spec['model']

        # GPU 資源請求
        if not self.gpu.request(model, spec['vram_gb']):
            logger.warning(f'GPU 不夠載入 {model}，降級用 reasoning')
            spec = EXPERTS['reasoning']
            model = spec['model']
            self.gpu.request(model, spec['vram_gb'])

        # 呼叫 Ollama
        t0 = time.time()
        try:
            r = requests.post(
                f'{self.OLLAMA_URL}/api/generate',
                json={
                    'model': model,
                    'prompt': question,
                    'stream': False,
                    'keep_alive': '5m',
                },
                timeout=300,
            )
            r.raise_for_status()
            response = r.json().get('response', '')
            elapsed = time.time() - t0
            logger.info(f'  完成 ({elapsed:.1f}s, {len(response)} 字)')
            return response
        except Exception as e:
            return f'❌ 錯誤: {e}'

    def status(self) -> Dict:
        return {
            'experts': {k: v['model'] for k, v in EXPERTS.items()},
            'gpu': self.gpu.status(),
        }


# ─────────────────────────────────────────────────────────
#  CLI 測試
# ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    r = MoERouter()
    if len(sys.argv) > 1:
        q = ' '.join(sys.argv[1:])
        print(r.ask(q))
    else:
        # 測試各專家
        tests = [
            ('reasoning', '幫我評估 1108 幸福值不值得買'),
            ('math',      '計算 1108 的 DCF 估值，假設 EPS 1.2、成長率 5%、折現率 8%'),
            ('code',      '寫 SQL 查 PE < 15 且殖利率 > 5 的台股'),
            ('embed',     '把這篇新聞做向量化'),
        ]
        for expected, q in tests:
            actual = r.route(q)
            mark = '✅' if actual == expected else '❌'
            print(f'{mark} 「{q[:30]}」 → {actual} (預期 {expected})')
