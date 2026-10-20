"""
角色 → 模型 路由器

7 分析角色 → 本地模型（實際映射以下方 ROLE_TO_MODEL 為準；env 可覆寫）：
  🎩 investment-advisor      → MAIN (qwen3.5:35b-a3b @ .28)   最強整合
  🤝 stock-team-orchestrator → MAIN (qwen3.5:35b-a3b @ .28)   團隊協調
  📈 technical-analyst       → MAIN (@ .28)                    指標 + 型態
  💰 fundamental-analyst     → MAIN (@ .28)                    財報數字
  🎯 macro-analyst           → MAIN (@ .28)                    大局
  💎 value-analyst           → VIEW (= MAIN @ .28)             估值
  🏦 chip-analyst            → VIEW (= MAIN @ .28)             法人趨勢（團隊分析流程已改規則模板，見 rule_roles.py）
  🛡️ risk-manager            → qwen3.8:27b @ .27               財經風控（團隊分析流程已改規則模板）

  合議委員(consensus.COMMITTEE) → qwen3.8:27b(.27) / gemma4:12b(.27) / granite4.2:8b(.28)
  facilitator                   → qwen3.5:35b-a3b (@ .28)
  型態/看圖 → SenVision 蔡森演算法(非 LLM，精準型態/頸線)，結果餵 technical-analyst
  工具型   → （已移除：embed、tw-polish 沒有呼叫端）
  env 覆寫 → TWSTOCK_MAIN_LLM / TWSTOCK_VIEW_LLM / CONSENSUS_MODELS / CONSENSUS_FACILITATOR
"""

from __future__ import annotations

import logging
import os
import sys
import time

import requests

from src.moe import model_nodes

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  角色 → 模型 映射
# ─────────────────────────────────────────────────────────
# 主力模型:env TWSTOCK_MAIN_LLM 可覆寫（2026-10-19 起預設 qwen3.5:35b-a3b；舊的 qwen3-14b/qwen2.5-14b 已從節點刪除，回退要先重新 pull）。
MAIN_14B = os.getenv('TWSTOCK_MAIN_LLM', model_nodes.DEFAULT_MAIN)
# 換視角模型(value/chip 角色):env TWSTOCK_VIEW_LLM 可覆寫;預設同主力（gemma2:9b 已停用並刪除）。
VIEW_MODEL = os.getenv('TWSTOCK_VIEW_LLM', model_nodes.DEFAULT_VIEW)

ROLE_TO_MODEL = {
    # 推理 / 整合（主力 14b @ .28）
    'investment-advisor':       MAIN_14B,
    'stock-team-orchestrator':  MAIN_14B,

    # 需推理（主力 14b @ .28）
    # 技術角色 2026-08-15 由 MAIN_14B(@.28) 改走 llama3.1:8b(@.27) —— 負載分流，非模型偏好。
    # 實測(nvidia-smi 連續取樣 12 次 / 60 秒):
    #   .28 使用率 99%(逐次 99 99 99 99 100 …) 溫度 82°C ← 已飽和且逼近 V100 降頻點
    #   .27 使用率  0%(逐次 0 0 0 0 0 …)      溫度 55°C ← 完全閒置
    # 技術角色佔 LLM 時間 38.9%(六角色中最重),全塞在飽和的 .28 上。
    # A/B(6 檔、同一份 production 提示詞、temp0 固定 seed、只換模型+節點):
    #   .28 qwen3-14b  成功 2/6(四檔破 300s 逾時) 平均 237.9s 引用幻覺 0
    #   .27 llama3.1   成功 6/6                  平均   4.4s 引用幻覺 0  長度 273 vs 300
    # 逾時的報告內容會變成「分析失敗: …」字串,卻仍被顧問整合與合議採用 ——
    # 也就是正式週跑裡技術角色有 2/3 機率在靜默降級。分流後 .28 負載降約 39%。
    # ⚠️ 這組數字混淆了「模型能力」與「節點負載」:.28 的 237.9s 多數是排隊。
    #    引用正確性只是最低門檻,真正的品質答案要看 verdict_detail 的事後超額報酬,
    #    換前/換後各累積一段再比。（歷史紀錄：qwen3-14b、llama3.1 已於 2026-10-19 從節點刪除，TECH_MODEL 不能再指向它們。）
    # 2026-10-19 技術角色走主力 MoE(.28)：同提示詞 MoE 約 6 秒、密集 27B 約 41 秒。
    'technical-analyst':        os.getenv('TECH_MODEL', model_nodes.DEFAULT_TECH),
    'fundamental-analyst':      MAIN_14B,

    # 換視角（預設同主力 MoE @ .28）
    'value-analyst':            VIEW_MODEL,
    'chip-analyst':             VIEW_MODEL,

    # 風控 2026-08-20 由 qwen2.5:7b(@.27) 改走 qwen2.5-14b(@.28)。
    # qwen2.5-14b 同家族升級(3b→7b→14b),財經推理更強。
    'risk-manager':             os.getenv('RISK_MODEL', model_nodes.DEFAULT_RISK),
    'macro-analyst':            MAIN_14B,  # 2026-08-01 3b→14b:3b會捏造指標(把VIX chg%貼成券資報酬率)+讀反大盤

    # 工具型（按需）
    # 註：原 'vision'(看圖 LLM) 已移除——「看圖/型態」改用 SenVision 蔡森演算法(精準、不幻覺)，
    #     型態結果直接餵 technical-analyst（見 team_daily_verified.senvision_text）。
    # embed、tw-polish 角色已移除：沒有任何呼叫端，嵌入改走 model_nodes.embed_url()
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


# 確定性:低 temperature + 固定 seed → 同輸入可重現 verdict。env 可覆寫。
LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0'))  # 0=greedy 完全可重現;env 可調高求多樣性
LLM_SEED = int(os.getenv('LLM_SEED', '42'))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://172.16.9.28:11434')       # 主力 .28
OLLAMA_URL_27 = os.getenv('OLLAMA_CONSENSUS_URL', 'http://172.16.9.27:11434')  # 合議 .27

# 模型 → 主機：唯一來源是 src/moe/model_nodes.py（env MODEL_NODES 可擴充）；換模型時改那裡。
MODEL_TO_URL = dict(model_nodes.MODEL_NODES)


def _env_flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


# 2026-10-18 起預設關閉思考並限制輸出長度：
#   qwen3 預設會先寫一大段思考（同一份提示生成量 4.2 倍、生成時間 72 秒對 19 秒），且過去 7 天有 4 次失控生成
#   （7,500 個 token 以上、撞 10 分鐘逾時回 500）。已存角色報告最長 708 字，1536 個 token 有餘裕。
#   ROLE_THINK=true、ROLE_NUM_PREDICT=N 可還原或調整。
def ask_role(role: str,
             question: str,
             include_role_prompt: bool = True,
             timeout: int = 300) -> dict:
    """以指定角色（自動選用對應模型）回答問題。"""
    if role not in ROLE_TO_MODEL:
        return {'error': f'未知角色: {role}', 'available': list(ROLE_TO_MODEL.keys())}

    model = ROLE_TO_MODEL[role]
    prompt = question
    if include_role_prompt and role in ROLE_PROMPTS:
        prompt = f"{ROLE_PROMPTS[role]}\n\n用戶問題：\n{question}"

    url = MODEL_TO_URL.get(model, OLLAMA_URL)
    # 重試：失敗的角色會讓 reports[role] 變成「分析失敗: …」字串，而顧問整合與合議
    # 照樣拿它去整合、投票 —— 流程全綠、log 正常，只是那份意見其實是錯誤訊息。
    # 這是靜默降級，不重試等於把它當常態。實測（2026-08-15）：
    #   角色並行前失敗率 0.1%（50,965 次）→ 並行後最高 18.8%（負載重時）
    # 重試之間退避，讓瞬時壅塞有時間消化。
    attempts = max(1, int(os.getenv('ROLE_RETRY', '3')))
    last_err = None
    for i in range(attempts):
        t0 = time.time()
        try:
            r = requests.post(
                f'{url}/api/generate',
                json={
                    'model': model,
                    'prompt': prompt,
                    'stream': False,
                    'think': _env_flag('ROLE_THINK', False),
                    'options': {'num_gpu': 99, 'temperature': LLM_TEMPERATURE, 'seed': LLM_SEED,
                               'num_ctx': int(os.getenv('ROLE_NUM_CTX', '8192')),
                               'num_predict': int(os.getenv('ROLE_NUM_PREDICT', '1536'))},
                },
                timeout=timeout,
            )
            r.raise_for_status()
            elapsed = time.time() - t0
            body = r.json()
            out = {
                'role': role,
                'model': model,
                'response': body.get('response', ''),
                'elapsed_sec': round(elapsed, 1),
            }
            if body.get('done_reason') == 'length':
                out['truncated'] = True      # 撞到輸出上限：文字保留，但要看得見，不能靜默當完整報告
            if i:
                out['retries'] = i          # 留痕：這份報告是重試後才拿到的
            return out
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                # 佇列滿(503 server busy)不是瞬時抖動,是持續數小時的飽和狀態,
                # 5s/10s 退避等於沒退,三次很快用完就變成「分析失敗」字串。
                # 2026-08-19 實測 .28 直接回 503:{"error":"server busy,
                # please try again.  maximum pending requests exceeded"}
                busy = (isinstance(e, requests.HTTPError)
                        and getattr(e.response, 'status_code', None) == 503)
                time.sleep((30, 120, 300)[min(i, 2)] if busy else 5 * (i + 1))
    return {'role': role, 'model': model, 'error': str(last_err),
            'attempts': attempts}


def list_roles() -> dict[str, str]:
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
