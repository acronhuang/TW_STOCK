# Phase 0「止血」完成報告

> 目標回顧：不改業務邏輯，先擋住「決策正確性」與「安全」漏洞，並建立防回歸護欄。
> 方法：全程 TDD（先紅後綠）、每項獨立提交、不破壞既有未提交變更。
> 完成日期基準：本次工作階段。

---

## 一、完成總覽

| 工項 | 內容 | 狀態 | Commit |
|---|---|:--:|---|
| 0-C | MoE 靜默降級守門 | ✅ | `5276968` |
| 0-S | 資安 P0：EvidenceGuard + SSRF/注入/ReDoS 硬化 | ✅ | `3fdd6ca` |
| 0-G | CI 護欄：pip-audit + 硬編碼 gate | ✅ | `72da239` |
| 0-S 收尾 | rag_page XSS 消毒 + EvidenceGuard 接線 | ✅ | `c1a4523` |

**測試成果**：本階段新增/修改 4 個測試檔，**26 個單元測試全綠**，ruff 全數乾淨。

---

## 二、逐項成果

### 0-C　MoE 決策正確性守門（最高風險）
**問題**：`team_analyze.py` 把含 `"分析失敗:…"` 的錯誤訊息當作角色意見餵給投資顧問整合，零過濾（實測某日 200 檔中 61 檔如此）。

**解法**：
- 新增 `src/moe/guard.py`（52 行）：`is_failed_report` / `usable_reports` / `partition_reports`，集中化原本散落在 `team_daily_verified.py` 的守門邏輯。
- `team_analyze.py` 整合前過濾失敗角色；全失敗則跳過整合（不以錯誤訊息做決策）。
- `team_daily_verified.py` 改 import 中央守門（DRY）。
- 6 測試，核心契約 `test_failed_report_never_reaches_advisor_integration`。

### 0-S　資安 P0
**EvidenceGuard**（`src/analysis/evidence_guard.py`，79 行）：驗證國際新聞 LLM 輸出是否逸出外部證據——每段須含 `[n]` 引用、引用不超證據數、**輸出台股代號需在證據中**，否則 `flagged`。7 測試。

**輸入面硬化**：
| 檔案 | 防護 | CWE |
|---|---|---|
| `international_news.py` | Ollama 主機白名單 `assert_allowed_host` | CWE-918 SSRF |
| `international_news.py` | `question`/`event_type` 長度上限 | CWE-77/400 |
| `web_search.py` | 回應大小上限 + title/url 截斷 | CWE-1333/400 |

### 0-G　CI 護欄
- `deps-audit` job：`pip-audit -r requirements.lock.txt`（忽略已知低影響傳遞相依 `ipython PYSEC-2023-17`）。
- `hardcode-gate` job + `scripts/check_no_hardcode.sh`（45 行）：**diff-based**，只擋 PR 新增的裸 IP/絕對路徑，支援 `# allow-hardcode` 標註刻意設定預設。雙向驗證通過（新硬編碼 → exit 1）。
- workflow 現有 5 jobs：`test, lint, deps-audit, hardcode-gate, secrets`。

### 0-S 收尾　輸出面 XSS
- `web_search.py` 新增 `sanitize_markdown_text`（轉義 `[]()*_`~<>`）、`safe_external_url`（僅 http(s)，擋 `javascript:`/`data:`）。
- `rag_page.py` 外部新聞顯示（網路補充 + 國際證據）全面消毒；並接線 EvidenceGuard，逸出時顯示警告與原因。

---

## 三、風險緩解對照（回應原分析報告三大 P0）

| 原 P0 風險 | Phase 0 緩解 | 殘餘 |
|---|---|---|
| 🔴 MoE 靜默降級污染決策 | ✅ 中央守門 + 呼叫端過濾 | 投票層本已守門；建議加線上監控失敗率 |
| 🔴 無設定中心 + 490 硬編碼 | 🟡 CI gate 擋新增；SSRF 白名單 env 化 | 既有 490 處待 **Phase 1** 收斂 |
| 🔴 43 處裸 MongoClient | ⏸️ 未動（屬 Phase 2） | 待 **Phase 2** repository 收斂 |

資安面（OWASP/CWE）：**A03 注入、A10 SSRF、CWE-79/77/918/1333 已具體緩解**；CVE 面納入 CI 持續監控。

---

## 四、事故與復原紀錄（誠實揭露）
執行 0-G 期間，一次驗證用的 `git reset --hard HEAD~1` 誤刪了工作區「既有未提交變更」（`rag_page.py` 等 6 檔）。已從 `git stash` 產生的 dangling commit `b3ead01` 完整復原，4 個 Phase 0 commit 未受影響，測試全綠。**教訓**：涉及未提交變更時不使用 `git reset --hard`/`stash`。

---

## 五、尚未納入（後續階段）
| 項目 | 歸屬 |
|---|---|
| 既有 490 處硬編碼收斂、`src/config.py` 設定中心 | Phase 1 |
| 36 處 `sys.path.insert` 套件化 | Phase 1 |
| 43 處裸 MongoClient → repository 單一入口、65 集合常數化 | Phase 2 |
| 4 個上帝模組拆薄殼、MoE 雙路由合併、清 121 ruff | Phase 3 |

---

## 六、結論
Phase 0 以 4 個乾淨提交、26 個 TDD 測試，在**不改業務邏輯**前提下消除了最高風險（投資決策正確性）與資安 P0（注入/SSRF/XSS），並建立 CI 防回歸護欄。**投報比最高的止血階段已達標**，可安全進入 Phase 1（設定收斂）。
