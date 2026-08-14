#!/usr/bin/env python3
"""委員會上線檢查 —— 換模型後確認新委員真的在投票，而不是靜默缺席。

用法:
  committee_live_check.py                  檢查最近 1 個分析日，印報告
  committee_live_check.py --since-hours 6  只看最近 6 小時內寫入的分析
  committee_live_check.py --alert          有問題才寫 schedule_alerts（網頁看，不發 LINE）

為什麼需要這支:換委員只是改 CONSENSUS_MODELS 一行，但它可能靜默不生效 ——
env 覆寫、模型沒 pull 成功、回覆格式抽不到票，任一種都會讓委員會少一個人，
而整體流程照跑、日誌照綠。本專案已有前例:hermes3:8b 出席 8913 次、84.7% 都投
買進而長期無人察覺。故這裡直接拿**實際投票紀錄**對照設定，不信設定檔。

判準（任一不過就是 🔴）:
  1. 設定裡的每位委員都必須在最近這批分析中出現
  2. 每位委員的抽不到票（棄權）比例 ≤ NULL_MAX
  3. 每位委員的單一票種佔比 ≤ BIAS_MAX（恆說同一句話 = 沒貢獻資訊）
"""
import sys, argparse, datetime
from collections import Counter, defaultdict

from pymongo import MongoClient

sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')

DB = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
BIAS_MAX = 0.75
NULL_MAX = 0.05
MIN_VOTES = 20          # 票數太少不判偏態（剛開跑時樣本不足，避免誤報）


def configured():
    try:
        from src.moe.consensus import COMMITTEE
        return list(COMMITTEE)
    except Exception as e:
        print(f"⚠️ 讀不到 consensus.COMMITTEE：{e}")
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since-hours', type=float, default=None,
                    help='只看最近 N 小時內寫入的分析（預設:看最近一個分析日）')
    ap.add_argument('--alert', action='store_true')
    a = ap.parse_args()

    cfg = configured()
    print(f"設定的委員會 = {cfg}")

    if a.since_hours:
        # 用 _id 的內嵌時間戳判「最近寫入」,不能用 date 欄位 ——
        # team_analysis.date 是**分析日**(午夜時間戳),不是寫入時間,
        # 拿它跟 now-N 小時比會把當天整批排除掉,靜默回 0 筆。
        from bson import ObjectId
        cut = datetime.datetime.now() - datetime.timedelta(hours=a.since_hours)
        q = {'_id': {'$gte': ObjectId.from_datetime(cut)},
             'consensus.votes': {'$exists': True}}
        scope = f"最近 {a.since_hours} 小時內寫入"
    else:
        days = sorted({d['date'] for d in DB.team_analysis.find(
            {'consensus.votes': {'$exists': True}}, {'date': 1}) if d.get('date')})
        if not days:
            print("🔴 team_analysis 裡沒有任何帶 consensus.votes 的文件")
            return 1
        last = days[-1]
        q = {'date': last, 'consensus.votes': {'$exists': True}}
        scope = f"最近分析日 {last:%Y-%m-%d}"

    docs = list(DB.team_analysis.find(q, {'consensus.votes': 1}))
    print(f"檢查範圍 = {scope}，分析文件 {len(docs)} 筆\n")
    if not docs:
        print("🔴 該範圍內沒有分析文件 —— 週跑可能還沒開始或尚未寫入")
        return 1

    seat, vote = Counter(), defaultdict(Counter)
    for d in docs:
        for v in (d.get('consensus') or {}).get('votes') or []:
            m = v.get('model')
            if not m:
                continue
            seat[m] += 1
            vote[m][v.get('vote') or 'None'] += 1

    print("%-22s %7s %7s %7s %7s %8s" % ('模型', '出席', '買進%', '持有%', '賣出%', '棄權%'))
    problems = []
    for m in sorted(seat, key=lambda x: -seat[x]):
        t = seat[m]
        c = vote[m]
        pct = {k: c[k] * 100 / t for k in ('買進', '持有', '賣出', 'None')}
        print("%-22s %7d %6.1f%% %6.1f%% %6.1f%% %7.1f%%" % (
            m, t, pct['買進'], pct['持有'], pct['賣出'], pct['None']))
        if m not in cfg:
            continue                      # 不在設定裡的（舊委員殘留）不判
        if t < MIN_VOTES:
            continue
        top = max(pct['買進'], pct['持有'], pct['賣出']) / 100
        if top > BIAS_MAX:
            problems.append(f"{m} 單一票種佔比 {top*100:.1f}% > {BIAS_MAX*100:.0f}%")
        if pct['None'] / 100 > NULL_MAX:
            problems.append(f"{m} 棄權率 {pct['None']:.1f}% > {NULL_MAX*100:.0f}%")

    print()
    missing = [m for m in cfg if m not in seat]
    if missing:
        problems.insert(0, f"設定的委員未出現在投票紀錄: {missing}")
        print(f"🔴 缺席委員 {missing}")
        print("   可能原因:CONSENSUS_MODELS 被 env 覆寫 / 模型未 pull 成功 / 該節點連不上")
    else:
        print(f"✅ 設定的 {len(cfg)} 位委員全部有出席投票")

    extra = [m for m in seat if m not in cfg]
    if extra:
        print(f"ⓘ 有投票但不在設定中: {extra}（若剛改設定、這批是改之前跑的，屬正常）")

    for p in problems:
        print(f"🔴 {p}")
    if not problems:
        print("✅ 全部檢查通過")

    if a.alert and problems:
        DB.schedule_alerts.create_index([('ts', -1)])
        DB.schedule_alerts.insert_one({
            'ts': datetime.datetime.now(), 'level': 'warning',
            'source': 'committee_live_check',
            'message': f"⚠️ 委員會上線檢查未過（{scope}）: " + "; ".join(problems),
            'detail': {'configured': cfg, 'seats': dict(seat)}, 'resolved': False})
        print("[alert] 已寫 schedule_alerts")
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
