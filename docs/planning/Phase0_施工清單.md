# Phase 0 施工清單（止血）— 逐檔具體改動

> 目標：不改業務邏輯，先擋住「決策正確性」與「安全」漏洞。總估 ~20h。
> 原則：每項改動皆可獨立提交 + 測試回歸；集中化既有散落的守門邏輯。

---

## 工項 0-C：MoE 靜默降級守門（最高優先，本次實作）

### 問題定位（實測）
- `scripts/team_analyze.py:496` 失敗角色寫成 `reports[role] = f"分析失敗: {r['error']}"`，
  第 510 行 `data['reports'] = reports` 把**含錯誤訊息的全部報告**餵給 investment-advisor 整合 → **無任何過濾**。
- `scripts/team_daily_verified.py` **已有** `usable_reports()`(L744) 正確守門，但屬**腳本區域函式**，`team_analyze.py` 無法共用 → 邏輯重複且覆蓋不全。
- `src/moe/consensus.py` 投票層**已守門**（ERR→vote=None→不計入 tally/valid），無需改。

### 改動清單
| 檔案 | 動作 | 具體改動 |
|---|---|---|
| `src/moe/guard.py` | **新增** | 集中守門：`FAIL_PREFIX`、`is_failed_report()`、`usable_reports()`、`partition_reports()` |
| `tests/test_moe_guard.py` | **新增** | TDD：失敗報告被濾除、不進整合；全失敗回空 dict |
| `scripts/team_analyze.py` | 修改 | 匯入 `usable_reports`；整合前 `data['reports'] = usable_reports(reports)`；全失敗則跳過整合 |
| `scripts/team_daily_verified.py` | 重構 | `usable_reports`/`_FAIL_PREFIX` 改為 `from src.moe.guard import ...`（DRY，行為不變） |

### 驗收標準（DoD）
- AC1 `usable_reports({'a':'分析失敗: x','b':'正常'})` == `{'b':'正常'}`。
- AC2 全失敗 → 回 `{}`，呼叫端跳過整合（不以錯誤訊息決策）。
- AC3 `team_analyze` 整合輸入不含任何 `分析失敗:` 開頭字串。
- AC4 既有 139 測試回歸綠；`team_daily_verified` 行為不變（改為共用同一函式）。

---

## 工項 0-S：資安 P0（XSS + 提示注入 + SSRF）

### 改動清單
| 檔案 | 動作 | 具體改動 |
|---|---|---|
| `dashboard/pages/rag_page.py` | 修改 | 外部 RSS `title` 以純文字呈現（`st.write`/跳脫），連結僅允許 `http(s)://`；不用 markdown 內插外部字串 |
| `src/analysis/web_search.py` | 修改 | 回應大小上限（`max_bytes`）、`title`/`url` 長度截斷，降低 XSS/ReDoS 面 |
| `src/analysis/international_news.py` | 修改 | ① `OLLAMA` 主機白名單校驗（防 SSRF/CWE-918）；② prompt 對 `question`/`event_type` 加分隔標記與長度上限（防注入） |
| `src/analysis/evidence_guard.py` | **新增** | `EvidenceGuard`：驗證 LLM 輸出每段含 `[n]`、未列標的標記 `flagged=True`（緩解逸出證據） |
| `tests/test_evidence_guard.py` | **新增** | 未引用/逸出標的→flagged；合規→通過 |

### 驗收標準
- AC1 外部標題含 `<script>` 不會被當 HTML 執行（純文字）。
- AC2 `event_type` 非白名單值被拒；`region` 僅允許五地區碼。
- AC3 `OLLAMA` 指向非白名單主機時拒絕連線並記錄。
- AC4 `EvidenceGuard` 對缺 `[n]` 或未列標的回 `flagged=True` 附原因。

---

## 工項 0-G：CI 護欄

### 改動清單
| 檔案 | 動作 | 具體改動 |
|---|---|---|
| `.github/workflows/ci.yml` | 修改/新增 | 加 `ruff check`、`pytest -m unit`、`pip-audit -r requirements.lock.txt` 步驟 |
| `scripts/check_no_hardcode.sh` | **新增** | grep gate：新增裸 IP(`\d+\.\d+\.\d+\.\d+`)/絕對路徑(`/home/`) 即 fail（現況 490 處先設 baseline，只擋「新增」） |
| `pyproject.toml` | 修改 | `[tool.ruff.lint]` 逐步收斂：先把 F401/F841 列為 error 擋回歸 |

### 驗收標準
- AC1 PR 觸發 ruff + 單元測試 + pip-audit，任一紅則擋。
- AC2 新增硬編碼 IP/絕對路徑 → CI 失敗；既有 baseline 不誤擋。

---

## 執行順序與里程碑
```
Day 1     0-C MoE 守門(集中化+TDD+套用team_analyze)   ← 本次先做，消除決策正確性風險
Day 2-3   0-S 資安P0(XSS/注入/SSRF + EvidenceGuard)
Day 4     0-G CI 護欄(ruff+pytest+pip-audit+grep gate)
Day 5     整合回歸 + 文件更新
```

## 風險與回滾
- 每工項獨立 commit；MoE 守門為**純新增 + 呼叫端一行替換**，回滾僅需還原該行。
- `team_daily_verified` 重構為「同義替換」（改 import），可用既有 skip-done/audit 流程驗證行為不變。
