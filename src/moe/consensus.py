"""
合議投票層 —— 委員會多模型對顧問草案投票定案
======================================================
架構(依實機分工)：
  .28 主力 qwen3-14b 出初稿+主持人整合 → 顧問草案(買/持/賣)
  委員會 gemma2:9b(.27) + qwen2.5-14b(.28) + llama3.1:8b(.27) 獨立投票

委員跨兩節點：gemma2/llama3.1 在 .27，qwen2.5-14b 在 .28（與主力共存）。
資安模型(foundation-sec/whiterabbitneo)對股票判斷較弱,不納入。
可用 env CONSENSUS_MODELS 覆寫。完全不改動 Ollama 本身。
"""
import os
import re
import time

import requests

CONSENSUS_URL = os.getenv('OLLAMA_CONSENSUS_URL', 'http://172.16.9.27:11434')  # .27
OLLAMA_URL_28 = os.getenv('OLLAMA_URL', 'http://172.16.9.28:11434')           # .28
# 委員會(3 位,跨兩節點)。可用 env CONSENSUS_MODELS 覆寫。
# 資安模型(foundation-sec/whiterabbitneo)對股票判斷弱，不納入。
#
# 2026-08-20 換委員：deepseek-coder-v2:16b → qwen2.5-14b:latest
#   原因：deepseek-coder-v2 是程式開發模型,股票判斷非其長項;
#   qwen2.5-14b 是 14B 中文通才,財經推理能力更強。
#   ⚠️ qwen2.5 與主力 qwen3 同家族,同票率可能偏高——上線後跑實測確認。
#
# 歷史：
#   2026-08-14 qwen2.5-3b → llama3.1:8b(同家族冗餘 87.1%)
#   2026-08-15 llama3.1 實測確認帶來獨立意見(56.7%/+0.41)
#   2026-08-20 qwen2.5:7b → deepseek-coder-v2:16b → qwen2.5-14b:latest
#   ⚠️ llama3.1:8b 偏多(70% 買進),若 > 75% 應告警。hermes3:8b 前例 84.7%。
COMMITTEE = [m.strip() for m in
             os.getenv('CONSENSUS_MODELS', 'gemma2:9b,qwen2.5-14b:latest,llama3.1:8b').split(',')
             if m.strip()]
VOTES = ('買進', '持有', '賣出')
# 主持人（③）：讀完討論逐字稿做綜合定案，取代純多數決。走 .28 主力節點的 14B 通才。
FACILITATOR_URL = os.getenv('OLLAMA_FACILITATOR_URL', OLLAMA_URL_28)
FACILITATOR_MODEL = os.getenv('CONSENSUS_FACILITATOR', 'qwen3-14b:latest')
# 空方委員(devil's advocate):env CONSENSUS_DEVIL=1 啟用(default off)。
DEVIL_ENABLED = os.getenv('CONSENSUS_DEVIL', '0') == '1'
DEVIL_MODEL = os.getenv('CONSENSUS_DEVIL_MODEL', 'qwen2.5-14b:latest')
# 委員 → 節點：gemma2/llama3.1 在 .27，qwen2.5-14b 在 .28。未列者走 CONSENSUS_URL(.27)。
COMMITTEE_MODEL_URL = {
    'qwen2.5-14b:latest': OLLAMA_URL_28,
}


def _ask(model: str, prompt: str, timeout: int = 120, url: str = None) -> str:
    """向委員模型提問。失敗會重試 —— 一次連線抖動不該直接記成棄權。

    2026-08-16 實測:08~15 時 .27 出現連線失敗,llama3.1 與 qwen2.5:7b 的棄權率
    衝到 100%（gemma2 同節點、同提示詞卻全程 0%，故非節點整台掛掉），
    投票紀錄裡留下的是 `ERR:HTTPConnectionPool(host='172.16.9.27'...)`。
    棄權的委員那一輪等於沒投 —— 三人合議實際上只有兩人，而且完全靜默。

    角色層(role_router.ask_role)昨日已加重試,失敗率因此由 18.8% 降到 0.5%,
    但合議層漏了 —— 同一類問題只修了一半。CONSENSUS_RETRY=1 可停用重試。
    """
    attempts = max(1, int(os.getenv('CONSENSUS_RETRY', '3')))
    last = None
    for i in range(attempts):
        try:
            r = requests.post(f'{url or CONSENSUS_URL}/api/generate',
                              json={'model': model, 'prompt': prompt, 'stream': False,
                                    'options': {'temperature': float(os.getenv('LLM_TEMPERATURE', '0')), 'num_gpu': 99, 'seed': int(os.getenv('LLM_SEED', '42')),
                                               'num_ctx': int(os.getenv('CONSENSUS_NUM_CTX', '8192'))},
                                    'keep_alive': '10m'},  # ④ 委員跨輪常駐，避免多輪討論每輪重載
                              timeout=timeout)
            r.raise_for_status()
            return r.json().get('response', '')
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(5 * (i + 1))     # 退避,讓瞬時壅塞有時間消化
    return f'ERR:{last}'


_SYNONYM = [
    ('賣出', ('賣出', '賣', '減碼', '出場', 'sell', '看空')),
    ('買進', ('買進', '買', '加碼', '進場', 'buy', '看多')),
    ('持有', ('持有', '觀望', '中立', '不動', 'hold', '續抱')),
]


def _extract_vote(txt: str):
    """從回覆抽票；含同義詞對應(觀望→持有、減碼→賣出等)，先看首行再看全文。"""
    for scope in (txt.strip().split('\n', 1)[0], txt):
        for canon, kws in _SYNONYM:      # 賣>買>持 順序避免『不建議買進』誤判
            if any(k in scope for k in kws):
                return canon
    return None


def _advisor_rating(draft: str):
    """從顧問草案抽評級 → 買進/持有/賣出（觀望/中立→持有）。
    優先讀『評級：X』標籤，否則掃首段。供平手時定案回退，避免合議無視草案。"""
    if not draft:
        return None
    m = re.search(r'評級[:：]\s*(強力買進|買進|加碼|持有|觀望|中立|減碼|賣出)', draft)
    seg = m.group(1) if m else draft.strip().split('\n', 1)[0]
    for canon, kws in _SYNONYM:          # 賣>買>持
        if any(k in seg for k in kws):
            return canon
    return None


_committee_verified = False


def verify_committee(force: bool = False) -> dict:
    """確認 COMMITTEE 每位委員在合議節點上真的存在。首次 deliberate() 時自動跑一次。

    為什麼需要：委員名單只是一個字串常數，模型被 ollama rm 掉、或名稱有出入時，
    _ask() 會拿到 ERR:／格式外的回覆，_extract_vote 回 None，該委員就**安靜地棄權**——
    流程照跑、日誌照綠，只是三人會變兩人。本專案已有同類前例（hermes3:8b 出席
    8913 次、84.7% 都投買進而長期無人察覺）。

    不中止流程（中止會讓 14 小時的週跑整個白跑），但會大聲印出並寫 schedule_alerts，
    讓它在網頁上看得見。真正的把關由 scripts/committee_live_check.py 每天做。
    """
    global _committee_verified
    if _committee_verified and not force:
        return {}
    _committee_verified = True
    urls_to_check = {CONSENSUS_URL}
    urls_to_check.update(COMMITTEE_MODEL_URL.values())
    have = set()
    for u in urls_to_check:
        try:
            r = requests.get(f'{u}/api/tags', timeout=10)
            r.raise_for_status()
            have.update(m.get('name') for m in r.json().get('models', []))
        except Exception as e:
            print(f"⚠️ [committee] 無法查詢 {u} 的模型清單：{e}")
    missing = [m for m in COMMITTEE if m not in have]
    print(f"🗳️ [committee] 本次合議委員 = {COMMITTEE}"
          + (f"  🔴 節點上不存在：{missing}" if missing else "  ✅ 節點上皆存在"))
    if missing:
        try:
            from pymongo import MongoClient
            import datetime as _dt
            db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
            db.schedule_alerts.insert_one({
                'ts': _dt.datetime.now(), 'level': 'warning', 'source': 'consensus_committee',
                'message': f"🔴 合議委員在 {CONSENSUS_URL} 上不存在：{missing}"
                           f"（該委員會靜默棄權，三人會實際變 {len(COMMITTEE)-len(missing)} 人）",
                'detail': {'committee': COMMITTEE, 'missing': missing}, 'resolved': False})
        except Exception:
            pass
    return {'committee': list(COMMITTEE), 'missing': missing}


def deliberate(symbol: str, name: str, advisor_draft: str, data_summary: str,
               timeout: int = 120) -> dict:
    """委員會對顧問草案投票。回 {votes, tally, final, dissent}。"""
    verify_committee()
    prompt = (f"你是投資決策委員會成員。以下是主分析師對 {symbol} {name} 的整合建議草案與關鍵數據，"
              f"請獨立判斷後投一票。\n\n"
              f"【主分析師草案】\n{advisor_draft}\n\n"
              f"【關鍵數據】\n{data_summary}\n\n"
              f"規則：第一行只寫「買進」或「持有」或「賣出」三選一，第二行用一句話說明理由。")
    votes = []
    for m in COMMITTEE:
        resp = _ask(m, prompt, timeout, url=COMMITTEE_MODEL_URL.get(m))
        vote = _extract_vote(resp) if not resp.startswith('ERR:') else None
        reason = ''
        if vote and not resp.startswith('ERR:'):
            # 取第一句實質理由：跳過純票別行與純標題行（如【我的判斷】）
            for l in (x.strip() for x in resp.strip().split('\n') if x.strip()):
                if l in VOTES or re.fullmatch(r'[【\[（(].{0,12}[】\]）)]', l):
                    continue
                reason = l
                break
        votes.append({'model': m, 'vote': vote,
                      'reason': reason[:60] if reason else (resp[:40] if resp.startswith('ERR:') else '')})
    tally = {v: sum(1 for x in votes if x['vote'] == v) for v in VOTES}
    valid = [x for x in votes if x['vote']]
    draft_r = _advisor_rating(advisor_draft)
    if not valid:
        final = draft_r or '持有'
    else:
        top = max(tally.values())
        leaders = [v for v in VOTES if tally[v] == top]
        if len(leaders) == 1:
            final = leaders[0]
        elif draft_r in leaders:
            final = draft_r          # 平手 → 尊重顧問草案評級
        else:
            final = '持有'            # 平手且草案未落在平手選項 → 保守持有(不放大為激進)
    dissent = [x for x in valid if x['vote'] != final]
    return {'votes': votes, 'tally': tally, 'final': final,
            'n': len(valid), 'dissent': dissent}


# ── 序列討論(多輪合議) ────────────────────────────────────────────────
# deliberate() 是「並行盲投」:委員互相看不到彼此發言、只投一輪。
# discuss() 把它升級為「序列討論」:每輪把上一輪『所有委員的判斷+理由』餵回給每位委員，
# 讓他們讀完別人的看法後重新表態(可被說服改票)，迭代到「全體一致」或跑滿 rounds。
# 這是「投票 → 討論」的分水嶺。主持人收斂(facilitator)為第二步;此處先用末輪多數決定案。

def _parse_vote_reason(resp: str):
    """從委員回覆抽 (票, 理由)。ERR/無票回 (None, 短訊)。"""
    if resp.startswith('ERR:'):
        return None, resp[:40]
    vote = _extract_vote(resp)
    reason = ''
    if vote:
        for l in (x.strip() for x in resp.strip().split('\n') if x.strip()):
            if l in VOTES or re.fullmatch(r'[【\[（(].{0,12}[】\]）)]', l):
                continue
            reason = l
            break
    return vote, reason[:220]   # 較長：逐字稿要餵回完整論點供他人回應（非僅顯示用）


def _finalize(votes: list, advisor_draft: str):
    """末輪投票 → (final, tally, n_valid)。平手回退顧問草案評級，再退保守持有。"""
    tally = {v: sum(1 for x in votes if x['vote'] == v) for v in VOTES}
    valid = [x for x in votes if x['vote']]
    draft_r = _advisor_rating(advisor_draft)
    if not valid:
        return draft_r or '持有', tally, 0
    top = max(tally.values())
    leaders = [v for v in VOTES if tally[v] == top]
    if len(leaders) == 1:
        final = leaders[0]
    elif draft_r in leaders:
        final = draft_r
    else:
        final = '持有'
    return final, tally, len(valid)


def _fmt_transcript(votes: list) -> str:
    """把一輪委員發言組成逐字稿，供下一輪餵回。"""
    lines = [f"- {x['model']}：投「{x['vote']}」，理由：{x['reason'] or '（未述）'}"
             for x in votes if x['vote']]
    return '\n'.join(lines) if lines else '（上一輪無有效發言）'


def _round1_prompt(symbol, name, draft, data):
    return (f"你是投資決策委員會成員。以下是主分析師對 {symbol} {name} 的整合建議草案與關鍵數據，"
            f"請獨立判斷後投一票。\n\n"
            f"【主分析師草案】\n{draft}\n\n【關鍵數據】\n{data}\n\n"
            f"規則：第一行只寫「買進」或「持有」或「賣出」三選一，第二行用一句話說明理由。")


def _roundN_prompt(symbol, name, draft, data, transcript, prev_vote):
    return (f"你是投資決策委員會成員，正對 {symbol} {name} 進行下一輪討論。\n\n"
            f"【主分析師草案】\n{draft}\n\n【關鍵數據】\n{data}\n\n"
            f"【其他委員上一輪的判斷與理由】\n{transcript}\n\n"
            f"你上一輪投「{prev_vote or '未表態'}」。看完其他委員的意見後，你要維持還是修正？"
            f"可被有理據的看法說服而改票，也可堅持己見並反駁。\n"
            f"規則：第一行只寫「買進」或「持有」或「賣出」三選一，第二行一句理由"
            f"（若改票，說明被什麼說服）。")


def _facilitate(symbol, name, advisor_draft, data_summary, transcript, tally, rounds_run, timeout=120):
    """③ 主持人：讀完討論逐字稿 → 綜合定案（不盲從多數，少數有理據可採納）。
    走 .28 的 14B 通才。回 (vote, synthesis)；失敗回 (None, '')。"""
    prompt = (f"你是投資決策委員會的主持人。委員們已就 {symbol} {name} 討論了 {rounds_run} 輪。\n\n"
              f"【主分析師草案】\n{advisor_draft}\n\n【關鍵數據】\n{data_summary}\n\n"
              f"【委員最終討論逐字稿】\n{transcript}\n\n"
              f"【最終票數】買進 {tally['買進']} / 持有 {tally['持有']} / 賣出 {tally['賣出']}\n\n"
              f"請綜合委員的論點與分歧做最終定案（不必盲從多數，若少數意見更有理據可採納）。\n"
              f"第一行只寫「買進」或「持有」或「賣出」；接著 2-3 句說明定案理由，"
              f"點出主要分歧與你如何權衡。")
    resp = _ask(FACILITATOR_MODEL, prompt, timeout, url=FACILITATOR_URL)
    if resp.startswith('ERR:'):
        return None, ''
    vote = _extract_vote(resp)
    lines = [x.strip() for x in resp.strip().split('\n') if x.strip()]
    synthesis = ' '.join(l for l in lines if l not in VOTES)[:400]
    return vote, synthesis


def _devil_brief(symbol, name, advisor_draft, data_summary, timeout=120):
    """空方委員/魔鬼代言人:只找『買進』的最大風險與反方論點(不給買賣結論)。回文字,失敗回''。"""
    prompt = (f"你是投資決策委員會的『空方委員/魔鬼代言人』。針對 {symbol} {name},"
              f"你的唯一任務是找出『買進』的最大風險與反方論點,越具體越好。\n\n"
              f"【主分析師草案】\n{advisor_draft}\n\n【關鍵數據】\n{data_summary}\n\n"
              f"列 2-3 點最強的反方/風險論點(技術破位、籌碼鬆動、基本面惡化、估值過高、事件風險等),"
              f"每點一句具體理由。不要下買/賣/持結論,只提出風險。")
    resp = _ask(DEVIL_MODEL, prompt, timeout, url=COMMITTEE_MODEL_URL.get(DEVIL_MODEL))
    return '' if resp.startswith('ERR:') else resp.strip()[:500]


def discuss(symbol: str, name: str, advisor_draft: str, data_summary: str,
            rounds: int = 2, timeout: int = 120, facilitate: bool = True) -> dict:
    """多輪序列討論 + 主持人綜合定案。回 {votes, tally, final, final_source, facilitator,
    n, dissent, rounds_run, changed, round_tallies, transcript}（schema 相容 deliberate）。"""
    prev_votes, first_votes, votes, round_tallies, transcript = {}, {}, [], [], ''
    round0_votes = []          # round 0 = 委員各自獨立投票 = 盲投對照(免費，無額外呼叫)
    rounds_run = 0
    for r in range(max(1, rounds)):
        rounds_run = r + 1
        votes = []
        for m in COMMITTEE:
            prompt = (_round1_prompt(symbol, name, advisor_draft, data_summary) if r == 0
                      else _roundN_prompt(symbol, name, advisor_draft, data_summary,
                                          transcript, prev_votes.get(m)))
            vote, reason = _parse_vote_reason(_ask(m, prompt, timeout, url=COMMITTEE_MODEL_URL.get(m)))
            votes.append({'model': m, 'vote': vote, 'reason': reason})
        round_tallies.append({v: sum(1 for x in votes if x['vote'] == v) for v in VOTES})
        if r == 0:
            first_votes = {x['model']: x['vote'] for x in votes}
            round0_votes = votes
        prev_votes = {x['model']: x['vote'] for x in votes}
        transcript = _fmt_transcript(votes)
        # 早退：全員都投了且一致 → 共識達成，無需再討論
        vv = [x['vote'] for x in votes if x['vote']]
        if len(vv) == len(COMMITTEE) and len(set(vv)) == 1:
            break
    final, tally, n = _finalize(votes, advisor_draft)      # 多數決(fallback)
    blind_final = _finalize(round0_votes, advisor_draft)[0]  # 盲投對照定案(round0，A/B 用)
    final_source, fac_synth = 'majority', ''
    if DEVIL_ENABLED:                                      # 空方委員:風險論點併入逐字稿供主持人權衡(default off)
        _brief = _devil_brief(symbol, name, advisor_draft, data_summary, timeout)
        if _brief:
            transcript = transcript + "\n\n【空方委員(魔鬼代言人)風險提示】\n" + _brief
    if facilitate:                                         # ③ 主持人綜合定案(優先)
        fac_vote, fac_synth = _facilitate(symbol, name, advisor_draft, data_summary,
                                          transcript, tally, rounds_run, timeout)
        if fac_vote in VOTES:
            final, final_source = fac_vote, 'facilitator'
    dissent = [x for x in votes if x['vote'] and x['vote'] != final]
    changed = sum(1 for x in votes if x['vote'] and first_votes.get(x['model'])
                  and x['vote'] != first_votes[x['model']])
    return {'votes': votes, 'tally': tally, 'final': final, 'final_source': final_source,
            'blind_final': blind_final,   # A/B：盲投(round0)定案 vs final(討論+主持人)
            'facilitator': fac_synth, 'n': n, 'dissent': dissent,
            'rounds_run': rounds_run, 'changed': changed,
            'round_tallies': round_tallies, 'transcript': transcript}


def line(consensus: dict) -> str:
    """一行合議結果供報告用。"""
    if not consensus or not consensus.get('n'):
        return "🗳️合議: 無有效票"
    t = consensus['tally']
    tag = ''
    if consensus['dissent']:
        tag = f"（{len(consensus['dissent'])}票異議）"
    return (f"🗳️合議({consensus['n']}模型): 買{t['買進']}/持{t['持有']}/賣{t['賣出']} "
            f"→ 定案:{consensus['final']}{tag}")
