"""
角色 → 模型 路由器

7 角色精準分派到最適合的本地模型：
  🎯 macro-analyst         → qwen3:8b           （快速大局判斷）
  📈 technical-analyst     → deepseek-r1:14b   （指標計算 + 型態）
  💰 fundamental-analyst   → deepseek-r1:14b   （財報數字）
  💎 value-analyst         → deepseek-r1:14b   （DCF / DDM 計算）
  🛡️ risk-manager          → deepseek-r1:14b   （VaR / Sharpe 計算）
  🏦 chip-analyst          → qwen3:8b           （法人趨勢）
  🎩 investment-advisor    → qwen3.6:27b        （最強整合）
  🤝 stock-team-orchestrator → qwen3.6:27b      （團隊協調）

  📈 型態/看圖           → SenVision 蔡森演算法(非LLM，精準型態/頸線/目標價)，餵 technical-analyst
  ⚙️ SQL/程式生成        → qwen2.5-coder:7b
  📰 新聞情緒向量化      → nomic-embed-text
  🇹🇼 繁中口語潤稿      → llama-3-taiwan:8b
"""

from __future__ import annotations
import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Dict
import requests

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  角色 → 模型 映射
# ─────────────────────────────────────────────────────────
ROLE_TO_MODEL = {
    # 推理 / 整合（主力 14b @ .28）
    'investment-advisor':       'qwen2.5-14b:latest',
    'stock-team-orchestrator':  'qwen2.5-14b:latest',

    # 需推理（主力 14b @ .28）
    'technical-analyst':        'qwen2.5-14b:latest',
    'fundamental-analyst':      'qwen2.5-14b:latest',

    # 換視角（hermes3 8b @ .27 合議節點）
    'value-analyst':            'hermes3:8b',
    'chip-analyst':             'hermes3:8b',

    # 快速規則/趨勢（輕模型 3b @ .28）
    'risk-manager':             'qwen2.5-3b:latest',
    'macro-analyst':            'qwen2.5-3b:latest',

    # 工具型（按需）
    # 註：原 'vision'(看圖 LLM) 已移除——「看圖/型態」改用 SenVision 蔡森演算法(精準、不幻覺)，
    #     型態結果直接餵 technical-analyst（見 team_daily_verified.senvision_text）。
    'coder':                    'qwen2.5-coder:7b',
    'embed':                    'nomic-embed-text',
    'tw-polish':                'weitsung50110/llama-3-taiwan:8b-instruct-dpo-q4_k_m',
}


# 角色描述（用於提示詞前綴）
ROLE_PROMPTS = {
    'macro-analyst': """你是專業總經分析師，分析利率、匯率、CPI、外資動向、地緣政治對台股大盤的影響。
回答簡潔、給數字、判斷偏多偏空。""",

    'technical-analyst': """你是專業技術分析師，分析 K 線、型態（W底/M頭/頭肩）、均線、RSI/MACD/KD。
給出趨勢方向、進場價位、停損點。""",

    'fundamental-analyst': """你是專業基本面分析師，分析財報的獲利能力（毛利/營益/淨利率）、ROE、負債、成長性。
不做估值（那是估值師的事），只評估財務健康度。""",

    'value-analyst': """你是專業價值分析師，計算 DCF（現金流折現）、DDM（股利折現）、PE Band 推估合理價。
給出明確的「合理價 vs 現價」差異與低估高估判斷。""",

    'risk-manager': """你是專業風險管理師，計算 VaR、Sharpe、Beta、最大回撤、部位配置、停損價。
給具體數字（張數、停損價、最壞虧損金額），不講感覺。""",

    'chip-analyst': """你是專業籌碼分析師，追蹤三大法人（外資/投信/自營商）、大戶持股、融資融券。
判斷主力意圖：累積/出貨/觀望/攻擊。""",

    'investment-advisor': """你是專業投資顧問，整合各專家報告，給出最終買賣建議。
務必具體：張數、進場價、停損價、目標價、持有期。""",

    'stock-team-orchestrator': """你是股市分析團隊總指揮，協調 7 位專家完成完整分析，
最後整合輸出投資建議。""",
}


OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://172.16.9.28:11434')       # 主力 .28
OLLAMA_URL_27 = os.getenv('OLLAMA_CONSENSUS_URL', 'http://172.16.9.27:11434')  # 合議 .27

# 模型 → 主機：hermes3 只在 .27，qwen2.5-* 在 .28（主力）。未列者走 OLLAMA_URL。
MODEL_TO_URL = {
    'qwen2.5-14b:latest': OLLAMA_URL,
    'qwen2.5-3b:latest':  OLLAMA_URL,
    'hermes3:8b':         OLLAMA_URL_27,
}


def ask_role(role: str,
             question: str,
             include_role_prompt: bool = True,
             timeout: int = 300) -> Dict:
    """以指定角色（自動選用對應模型）回答問題。"""
    if role not in ROLE_TO_MODEL:
        return {'error': f'未知角色: {role}', 'available': list(ROLE_TO_MODEL.keys())}

    model = ROLE_TO_MODEL[role]
    prompt = question
    if include_role_prompt and role in ROLE_PROMPTS:
        prompt = f"{ROLE_PROMPTS[role]}\n\n用戶問題：\n{question}"

    url = MODEL_TO_URL.get(model, OLLAMA_URL)
    t0 = time.time()
    try:
        r = requests.post(
            f'{url}/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'keep_alive': '5m',
                'options': {'num_gpu': 99},   # 強制全層GPU(不讓 Ollama 自動落 CPU)
            },
            timeout=timeout,
        )
        r.raise_for_status()
        elapsed = time.time() - t0
        return {
            'role': role,
            'model': model,
            'response': r.json().get('response', ''),
            'elapsed_sec': round(elapsed, 1),
        }
    except Exception as e:
        return {'role': role, 'model': model, 'error': str(e)}


def list_roles() -> Dict[str, str]:
    """列出所有角色與其對應模型。"""
    return ROLE_TO_MODEL.copy()


# ─────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print('\nUsage:')
        print('  python -m src.moe.role_router list')
        print('  python -m src.moe.role_router <role> "<question>"')
        print('  python -m src.moe.role_router macro-analyst "現在大盤適合進場嗎？"')
        return

    cmd = sys.argv[1]
    if cmd == 'list':
        print('▏角色 → 模型 對應表')
        print(f"  {'角色':<30} {'模型':<28}")
        print(f"  {'-'*60}")
        for role, model in ROLE_TO_MODEL.items():
            print(f"  {role:<30} {model}")
        return

    role = cmd
    question = ' '.join(sys.argv[2:])
    if not question:
        print('需提供問題')
        return

    print(f'▏角色: {role}  →  模型: {ROLE_TO_MODEL.get(role, "未知")}')
    print(f'▏問題: {question}\n')
    r = ask_role(role, question)
    if 'error' in r:
        print(f'❌ {r["error"]}')
    else:
        print(f'▏耗時: {r["elapsed_sec"]}s\n')
        print(r['response'])


if __name__ == '__main__':
    main()
