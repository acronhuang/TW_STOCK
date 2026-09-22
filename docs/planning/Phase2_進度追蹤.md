# Phase 2（資料層收斂）進度追蹤

> 目標：單一 DB 入口、連線由設定驅動、集合名單一真相源。
> 前置：Phase 1 已建 `src/config.py` + `get_db()`。
> 原則：預設值 = 遷移前（不改行為）、分批 + 每批 import/測試驗證、不碰無關既有變更。

## 完成度總覽

| 子項 | 狀態 | 說明 |
|---|:--:|---|
| 集合名常數化 `src/domain/collections.py` | ✅ | **61 個** `COLL_*` 單一真相源 + `all_collections()` 稽核 helper |
| 常數模組測試 | ✅ | 無重複/命名合規/核心存在/數量，4 測試綠 |
| `MongoStockRepository` 接 config | ✅ | 預設走 `config.get_db()`；顯式 `mongo_uri` 仍相容 |
| 模組採用 `COLL_*`（示範批） | 🟡 4 模組 | repository、lots、team_store、news_evidence |
| `config.get_db()` 採用 | 🟡 8 檔 | Phase 1+2 累計 |
| 參數驅動 `MongoClient` 全面收斂 | ⏸️ 37 處 | 逐批遷移中 |
| 65 集合全樹採用常數 | ⏸️ | 高頻集合待續批 |

## Commit 紀錄
| Commit | 內容 |
|---|---|
| `e92fa55` | collections.py（61 常數）+ repository 接 config + 4 測試 |
| `d16781b` | 3 模組（lots/team_store/news_evidence）採用 `COLL_*` + config |
| `4b72198` | (併行) 修 pre-existing bug：integrated_strategy_v21 裸 import |

## 已達成的量化成果
- **集合名常數**：0 → **61**（`src/domain/collections.py`）。
- **採用 `COLL_*` 的模組**：4（repository、lots、team_store、news_evidence）。
- **走 `config.get_db()`**：8 檔（含 Phase 1 的 literal 遷移）。
- 回歸：4 個新測試綠、既有測試無新增失敗、CI-select ruff 乾淨。

## 已建立的遷移模式（供續批複製）
```python
# 之前
from pymongo import MongoClient
db = MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
rows = db.stock_price.find({...})

# 之後
from src.config import get_db
from src.domain.collections import COLL_STOCK_PRICE
db = get_db()                          # URI/DB 由 config（env 可覆寫）
rows = db[COLL_STOCK_PRICE].find({...})
```
- 保留顯式 `mongo_uri` 參數者相容（repository 示範）。
- 高頻集合替換：`db.stock_price`(339)、`db.stock_factors`(120)、`db.financial_reports`(103) 等，逐檔加 import + 改用常數。

## 尚未完成（後續批次）

### 參數驅動 `MongoClient(...)`（37 處）
多數為 `self.client = MongoClient(mongo_uri)`，`mongo_uri` 建構子參數且預設讀 `MONGODB_URI`
（已 env 驅動、非硬編碼債）。收斂方向：改用 `config.get_db()` 或注入 repository，
分佈於 analysis / downloaders / strategy / calculators / migrations 等，需逐檔 import 驗證。

### 65 集合全樹採用常數
目前 4 模組採用；其餘散落各處的裸集合名（`db.stock_price` 等）待逐批替換。
建議依「高頻集合優先」推進，每批以 import + 相關測試回歸。

### `MongoStockRepository` 升為唯一入口（Phase 2 終局）
理想終態：各模組不直接開連線，改注入 repository；含連線單例/池。
此為較大重構，須在完整相依 + 有測試護欄下分批進行。

## 風險與注意事項
- **本機驗證侷限**：需完整相依（scipy/sklearn/xgboost/finmind/streamlit）才能 import 多數模組；
  已在本階段安裝並完成 import 驗證，但**無本機 MongoDB**，DB 行為須在部署環境或 mongomock 驗證。
- **行為保持**：所有預設值 = 遷移前，env 未設時連線目標不變。
- **命名一致**：新集合請先在 `collections.py` 註冊常數，再於模組引用。

## 建議下一步
1. 續批採用 `COLL_*`：優先 `stock_price`/`stock_factors`/`financial_reports` 高頻集合所在模組。
2. 參數驅動 `MongoClient` → `config.get_db()` 逐批遷移（37 處）。
3. 評估 `MongoStockRepository` 唯一入口 + 連線池的終局重構範圍。
