# v5 草案 — advisor 整合判準修改(shadow prompt + 驗證計畫,不動 live)

> 診斷結論(verdict_buyside_v3.md §8-9):追高偏誤源自 **investment-advisor** 把
> technical『上升趨勢』天真當買進理由(現行 prompt 甚至要求「評級呼應技術型態方向」)。
> v5 只在**趨勢市**附加追高防制,盤整市維持(已達標)。**全程影子,回測 + OOS 過閘門才議 live。**

## 1. Prompt 修改(最小侵入,不改 live 檔)
現行 advisor prompt(`role_router.py` / `team_analyze.build_expert_prompt`)**不動**。
以包裝函式在趨勢市附加條款(`src/analysis/buyside/advisor_v5.build_advisor_prompt_v5`):

```
⚠️ 追高防制(趨勢市專用):近期上升趨勢/技術偏多『本身不構成』買進理由。
給『買進/強力買進』前須至少一項獨立佐證:
  (1) 估值未偏貴  (2) 品質佳(三率向上/高 ROE)  (3) 明確反轉後再起(非追末端)。
僅有動能/技術偏多而無佐證 → 評級最高只能『觀望』。(僅趨勢市;盤整不受影響。)
```

**證據**:LLM 概念驗證(qwen3-14b @ .28)—— v5 回覆明確引用「追高防制機制下,僅技術動能
不構成買進理由,需等待估值」→ 評級『觀望』。**條款被讀取且套用。**

## 2. 影子 runner 設計(不觸 live)
`scripts/buyside_shadow_advisor_v5.py`(待建):
1. 對歷史 team_analysis(含 6 份 reports)逐檔:`regime = classify_regime(db, date)`。
2. `base = build_expert_prompt('investment-advisor', {reports, ...})`;`v5 = build_advisor_prompt_v5(base, regime)`。
3. 呼叫 advisor 模型(qwen3-14b @ .28)→ 抽評級 → 寫 **shadow 欄** `advisor_v5_rating`(+regime)。
4. **絕不改** live `advisor` / `consensus` / `final_verdict`。可 `--dry-run` / `--limit`。
- 成本:每檔 **1 次** LLM 呼叫(僅重跑整合,不重跑 6 分析師)。

## 3. 驗證計畫(閘門)
1. **買進轉換率**:趨勢市中,live=買進 但 v5=觀望 的比例(預期顯著;盤整應 ~0)。
2. **前瞻超額**:以 verdict_detail 的 excess/hit,比較 live-買進集 vs v5-買進集的命中/均超額,**分市況**。
3. **out-of-sample walk-forward**(如 v4:前段調校、後段 held-out)—— **這是硬閘門**。
4. **Go/No-Go**:held-out 上 ①趨勢市 v5-買進超額 > live ②盤整不劣化 ③整體不退步。三者皆過。

## 4. 升級 live 的治理(永不繞過)
shadow 驗證 → OOS 過 → feature-flag(預設 off)→ 團隊審 + 灰度 → 全量。任何一關人簽核。

## 5. 交付狀態
- ✅ `advisor_v5.build_advisor_prompt_v5`(regime-aware 包裝)+ TDD 綠(趨勢注入/盤整不動)
- ✅ LLM 概念驗證:條款被讀取套用(觀望,要求估值佐證)
- ⏳ 待團隊執行:影子 runner 全量跑(LLM 成本)+ 分市況 compare + **OOS 閘門**
- ⚠️ 前車之鑑:v4 in-sample 好看但 OOS 崩;**v5 未過 OOS 前不得上 live**

## 6. 最沒把握的 3 件事(v5)
1. **prompt 改動的效果未必轉成前瞻超額** —— 讓模型「不追高」≠「選到更好的買進」;可能只是少買、覆蓋降,超額未必升。須影子量化。
2. **OOS 泛化**(同 v4 教訓):趨勢市樣本跨區間可能不穩;單窗好看不算數。
3. **LLM 非決定論**:同 prompt 多次評級可能飄;需固定 temperature + 多次取眾數,否則 shadow 訊號含噪。

---

## 7. 影子 runner 已建 + smoke 驗證(scripts/buyside_shadow_advisor_v5.py)
- TDD 綠(趨勢寫 shadow / 盤整略過 / live 不變);--limit/--dry-run。
- .166 smoke(limit=2,真 LLM):**3481 群創 live 買進 → shadow 觀望(多頭)**——真實 flip;
  live final_verdict 不變 ✓。2603 回 None(thinking 預算不足)→ 已修:num_predict 1500 + /no_think 重試。
- **全量跑 = 團隊執行**(數千檔 × 1 LLM,數小時);之後分市況 compare → OOS walk-forward 閘門 → flag。

---

## 8. 全量 OOS 驗證結果(n=1885)— 🔴 NO-GO(v5 也過擬合)
```
① 整體 v5>live: 命中 40.4%→41.3% · 超額 -0.30%→-0.37%(整體反變差)
② 前後段一致 : 前段 +0.42%→+0.63%(改善) | 後段 -1.05%→-1.54%(惡化)← OOS 崩
③ 樣本足夠   : n=1885 ✅   ⑤ 盤整未受影響 ✅   None率 0
>>> NO-GO
```
**v5 與 v4 同一死法:in-sample 改善、out-of-sample 惡化。** 先前樣本 82.6% 是早期 cherry-pick。

## 9. 最終結論(買方修補全線收束)
- **post-hoc 過濾**(v2/v3/v3.1/v4)❌ OOS 不泛化
- **生成端 prompt**(v5 advisor 追高防制)❌ OOS 惡化
- → **兩法皆證偽**:買方追高反轉非穩定可利用,可能是期間噪音。
- **唯一 robust edge = 賣出側**(60%/+0.73%,一致)。
- **建議**:停止買方修補,策略重心移向賣出/迴避(long-short);買方接受極限。
- **live 全程未動**;OOS 閘門兩度擋下過擬合部署(v4、v5)。
