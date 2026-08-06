# 台股量化選股系統（tw-stock-analysis）

台股上市櫃資料收集 → 因子/技術/籌碼/財報分析 → **MoE 7 委員 LLM 合議選股** → 核心池漏斗（品質∩AI∩外資）→ 持倉風控。
技術棧：MongoDB + Python + 自架 Ollama（qwen2.5 3b/8b/14b）+ cron 排程 + Streamlit 儀表板。

---

## 命名規範（摘要）

> **核心原則：同一業務概念、跨層同一詞根。** 新程式一律照本規範；既有違反列為「凍結特例」走漸進修正。

- **識別碼一律 `stock_id`**：新程式與對外 API **禁用** `symbol`／`code`／`ticker`／`stock_code`。既有 `symbol`（stock_price 等）與 `code`（margin）為**凍結特例**，走讀取層映射，對外一律吐 `stock_id`。
- **資料庫（MongoDB）**：collection `snake_case` 複數；欄位 `snake_case`，**固定字尾對應型態**——`_id`=str、`_at`=datetime（時間戳）、`_on`／`_date`=日期、`_net`／金額=`Decimal128`、`_ratio`／`_pct`=float、`is_`／`has_`=bool（**禁否定式**如 `no_stop_loss`）。**禁** camelCase（`updatedAt`）、中文欄名、字串 `date`、魔術數字狀態（`status==2`）。
- **Python（PEP 8）**：類別 `PascalCase`、函式/變數 `snake_case`、常數 `UPPER_SNAKE`；檔名 `snake_case`（**禁中文檔名**）。**動詞分工**：`get`（必拿到）/`find`（可空）/`build`（產出）/`calculate`（只算不寫）/`sync`（每日增量）/`backfill`（歷史回填）/`validate`（只檢查）。
- **API**：REST 名詞複數、`/api/v1/…`、JSON `snake_case`（後端全 Python/Mongo，免雙向轉換）、**對外一律 `stock_id`**、錯誤碼 `UPPER_SNAKE`（`STOCK_NOT_FOUND`）。
- **文件編號**：`FR-<模組>-NNN`／`NFR-<領域>-NNN`／`TC-<模組>-NNN`／`ADR-NNN`；DFD 處理 `1.0`/`3.1`、儲存檔 `D1`。
- **落地檢查**：flake8 naming + `$jsonSchema` validator（`scripts/apply_schema_validation.py`）+ 每日契約稽核（`scripts/schema_contract_audit.py`）+ Code Review 檢查表；既有違反走「**讀取層映射 + 寫入層 validator**」漸進修正，**不物理大改**高引用表。

> 完整規範（核心詞彙表、跨層對應表、禁用清單、每條 ✅/❌ 專案範例、落地方式）見開發規劃文件 `專案需求説明/命名規範_執行版.md`。
