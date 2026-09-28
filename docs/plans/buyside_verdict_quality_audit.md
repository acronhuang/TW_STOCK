# 買方 verdict 流程品質稽核(2026-09-28)

> 起因:拆解 2471 資通買進推理時發現三個內部矛盾,遂全樣本量化 →
> 證實為**系統級品質缺陷**,與「買進有無 alpha」為兩件獨立的事。
> 純讀取稽核,未改 live。樣本:近 600 檔買進 verdict。

## 發現(全樣本比例)
| 破綻 | 比例 | 性質 |
|---|--:|---|
| ① 追高(advisor 進場價 > 現價)| 13.7% | 模型行為(追高偏誤,已知)|
| ② 評級買進但張數 0 張 | 7.0% | 內部矛盾(advisor vs risk)|
| ③ **風報比 < 1 仍買進** | **49.0%** | **半數買進以技術自己的數字不划算** |
| ④ **合議含壞票(空模板/無理由)** | **44.3%** | **壞票占總票 16.9%** |

## ④ 合議壞票 — 根因定位(按投票模型)
| 模型 | 壞票率 | 節點 |
|---|--:|---|
| **llama3.1:8b** | **35.8%** | .27 |
| gemma2:9b | 15.0% | .28 |
| qwen2.5-14b:latest | **0.0%** | .27 |

**根因**:小模型(llama3.1:8b / gemma2:9b)常輸出開場白模板
「我是投資決策委員會的成員…投下了以下票數:」而**無實際理由**;consensus parser
仍將其計為有效票 → tally 以部分垃圾輸入計算。qwen2.5-14b 完全乾淨。

## 重要區分:這是「流程正確性」缺陷,不是「alpha」缺陷
- 修好壞票/矛盾**不會**變出 alpha —— 因為連乾淨的買進 verdict OOS 超額也 ≈ 0(已證)。
- 但這些缺陷讓 verdict **在過程上不可信/自我矛盾**,值得修(正確性 + 可稽核性)。
- 兩者分開看:**alpha 問題無解(非平穩);流程品質問題可修。**

## 建議修法(皆需先影子驗證 + 具名簽核,因觸及 live consensus)
1. **合議壞票守門**(P1):投票理由為空模板/< N 字 → 重試該模型 or 排除該票不計 tally。
   預期直接降低 ④,且可能改變部分 final(→ 必須影子跑 A/B 量測 verdict 變動率再簽核)。
2. **verdict 一致性 lint**(P2,shadow 欄位,不改 live):對每檔標記
   ②(買進×0張)、③(風報比<1×買進)→ 寫 shadow 欄 / 儀表板,純觀測。
3. **小模型輸出格式硬約束**(P3):consensus prompt 強制先出理由再出票,
   或改用 qwen2.5-14b(壞票 0%)當合議票源之一。

## 現況
- 稽核為讀取;live consensus/final_verdict **未動**。
- 任何修法走既有治理:shadow A/B → verdict 變動率 + OOS 中性檢查 → signoff → 灰度。

## 狀態更新 — P2 已落地(2026-09-28)

**P2(shadow 一致性 lint)已完成並上線,全程純附加影子欄,live 未動。**

| 元件 | 檔案 | commit |
|---|---|---|
| 純函式 lint(TDD 3 綠)| `src/analysis/buyside/verdict_lint.py` | 6c92ffd |
| CLI + 影子寫入器 | `scripts/buyside_verdict_lint.py` | 6c92ffd |
| 測試 | `tests/test_verdict_lint.py` | 6c92ffd |
| 儀表板顯示(表格紅旗欄 + 單檔 flags)| `dashboard/pages/team.py` | f5b91cc |
| Nightly 自動 lint(evening_pipeline 8d)| `scripts/evening_pipeline.sh` | f5b91cc |

**寫入結果(全庫 3608 檔買進)**:只有 **29.5% 零紅旗**;① 追高 14.9%、② 買進0張 6.6%、
③ 風報比<1 31.1%、④ 含合議壞票 49.1%。→ 七成買進 verdict 帶至少一個內部矛盾,
現已逐檔寫入 `team_analysis.shadow_lint`。

**驗證**:寫入前後 2471 的 live 指紋(final_verdict+advisor+consensus)`fd1955e21b1e`
**完全相同** → 只新增 `shadow_lint`,未動任何 live 判斷。儀表板/nightly 皆只讀/只寫影子。

**尚未做(需簽核,觸及 live consensus)**:P1 合議壞票守門、P3 小模型格式硬約束/換 qwen2.5-14b 票源。
這兩項會改變 live final,須走 shadow A/B → verdict 變動率量測 → signoff。
