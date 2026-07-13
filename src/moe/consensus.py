"""
.27 合議投票層 —— 委員會多模型對 .28 顧問草案投票定案
======================================================
架構(依實機分工)：
  .28 主力 qwen2.5-14b 出初稿+主持人整合 → 顧問草案(買/持/賣)
  .27 合議小組 多個 8B 模型獨立投票 → 匯總定案(多數決)

委員會預設用 .27 上的「通用」模型(hermes3:8b + qwen2.5-3b)；
.27 另有資安模型(foundation-sec/whiterabbitneo)對股票判斷較弱,不預設納入,
可用 env CONSENSUS_MODELS 覆寫。完全不改動 Ollama 本身。
"""
import os
import re
import requests

CONSENSUS_URL = os.getenv('OLLAMA_CONSENSUS_URL', 'http://172.16.9.27:11434')  # 合議節點 .27
COMMITTEE = [m.strip() for m in
             os.getenv('CONSENSUS_MODELS', 'hermes3:8b,qwen2.5-3b:latest').split(',')
             if m.strip()]
VOTES = ('買進', '持有', '賣出')
# 合議委員全走 .27 合議節點(hermes3 + qwen2.5-3b 皆 GPU；.27 qwen2.5-3b 已設 num_gpu 99 上 GPU)。


def _ask(model: str, prompt: str, timeout: int = 120) -> str:
    try:
        r = requests.post(f'{CONSENSUS_URL}/api/generate',
                          json={'model': model, 'prompt': prompt, 'stream': False,
                                'options': {'temperature': 0.3, 'num_gpu': 99},  # 強制全層GPU
                                'keep_alive': '10m'},  # ④ 委員跨輪常駐 .27，避免多輪討論每輪重載
                          timeout=timeout)
        r.raise_for_status()
        return r.json().get('response', '')
    except Exception as e:
        return f'ERR:{e}'


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


def deliberate(symbol: str, name: str, advisor_draft: str, data_summary: str,
               timeout: int = 120) -> dict:
    """委員會對顧問草案投票。回 {votes, tally, final, dissent}。"""
    prompt = (f"你是投資決策委員會成員。以下是主分析師對 {symbol} {name} 的整合建議草案與關鍵數據，"
              f"請獨立判斷後投一票。\n\n"
              f"【主分析師草案】\n{advisor_draft}\n\n"
              f"【關鍵數據】\n{data_summary}\n\n"
              f"規則：第一行只寫「買進」或「持有」或「賣出」三選一，第二行用一句話說明理由。")
    votes = []
    for m in COMMITTEE:
        resp = _ask(m, prompt, timeout)
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


def discuss(symbol: str, name: str, advisor_draft: str, data_summary: str,
            rounds: int = 2, timeout: int = 120) -> dict:
    """多輪序列討論。回 {votes, tally, final, n, dissent, rounds_run, changed,
    round_tallies, transcript}（schema 相容 deliberate，另加討論過程欄位）。"""
    prev_votes, first_votes, votes, round_tallies, transcript = {}, {}, [], [], ''
    rounds_run = 0
    for r in range(max(1, rounds)):
        rounds_run = r + 1
        votes = []
        for m in COMMITTEE:
            prompt = (_round1_prompt(symbol, name, advisor_draft, data_summary) if r == 0
                      else _roundN_prompt(symbol, name, advisor_draft, data_summary,
                                          transcript, prev_votes.get(m)))
            vote, reason = _parse_vote_reason(_ask(m, prompt, timeout))
            votes.append({'model': m, 'vote': vote, 'reason': reason})
        round_tallies.append({v: sum(1 for x in votes if x['vote'] == v) for v in VOTES})
        if r == 0:
            first_votes = {x['model']: x['vote'] for x in votes}
        prev_votes = {x['model']: x['vote'] for x in votes}
        transcript = _fmt_transcript(votes)
        # 早退：全員都投了且一致 → 共識達成，無需再討論
        vv = [x['vote'] for x in votes if x['vote']]
        if len(vv) == len(COMMITTEE) and len(set(vv)) == 1:
            break
    final, tally, n = _finalize(votes, advisor_draft)
    dissent = [x for x in votes if x['vote'] and x['vote'] != final]
    changed = sum(1 for x in votes if x['vote'] and first_votes.get(x['model'])
                  and x['vote'] != first_votes[x['model']])
    return {'votes': votes, 'tally': tally, 'final': final, 'n': n, 'dissent': dissent,
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
