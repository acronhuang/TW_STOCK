# Phase 1（設定收斂）進度追蹤

> 目標：解除單機綁定、可多環境部署。建立 `src/config.py` 單一真相源，
> 收斂散落全樹的硬編碼 IP/路徑、`sys.path.insert`、`MongoClient`。
> 原則：預設值 = 遷移前（不改行為）、分批 + 每批驗證、不碰無關的既有未提交變更。

## 完成度總覽

| 子項 | 狀態 | 說明 |
|---|:--:|---|
| `src/config.py` 設定中心 | ✅ | MongoDB/Ollama/路徑/token 單一真相源 + `get_db()` helper |
| 路徑可攜化 | ✅ | `PROJECT_ROOT` 由檔案位置推導，去除 `/home/mdsadmin` 綁定 |
| 首批遷移（非 env 驅動硬編碼） | ✅ | `router.py`(×2)、`tech_lines.py` |
| `sys.path.insert` 清理 | 🟡 29/37 | 29 冗餘移除；8 待完整環境驗證 |
| `MongoClient` 硬編碼-literal → `get_db()` | ✅ 5/5 | 全數清零 |
| `MongoClient(mongo_uri)` 參數驅動 → repository | ⏸️ | 屬 Phase 2（~81 處，已 env 驅動，非急迫） |
| scripts/dashboard 層硬編碼 | ⏸️ | 待後續批次 |

## Commit 紀錄
| Commit | 內容 |
|---|---|
| `8e26ace` | config.py + router.py/tech_lines.py 首批 + 5 測試 |
| `26d6802` | 29 `sys.path.insert` 移除 + 5 literal `MongoClient`→`get_db()` |

## 已達成的量化成果
- **`src/config.py`**：5 個 TDD 測試（預設值/env 覆寫/路徑可攜/`get_db`）全綠。
- **`sys.path.insert`**：src 內由 37 → 8（移除 29，皆 fresh-process import 驗證通過）。
- **硬編碼-literal `MongoClient`**：5 → 0。
- **Ollama/路徑硬編碼**：`router.py`/`tech_lines.py` 已收斂至 config（env 可覆寫）。
- 回歸：33 模組 re-import OK、31 單元測試綠、CI-select ruff 乾淨。

## 尚未完成（後續批次 / 移交 Phase 2）

### 仍保留的 8 個 `sys.path.insert`（需完整相依環境逐一驗證）
```
src/analysis/risk_manager.py          （scipy 缺，本機無法驗證）
src/senvision/pattern_bridge.py       （條件式 insert）
src/senvision/pattern_detector.py     （__main__ 內）
src/senvision/scanner.py              （insert 'src' 子路徑）
src/strategy/hsieh_analysis.py        （__main__ CLI）
src/strategy/hsieh_dividend.py        （__main__ CLI）
src/strategy/hsieh_watchlist.py       （__main__ CLI）
src/strategy/integrated_strategy_v21.py（缺相依）
```
> 這些多為 `if __name__=='__main__'` 的 CLI 或條件式；移除後須改以 `python -m src.x`
> 執行並在含完整相依（scipy/sklearn/xgboost/finmind）的環境回歸，故本階段保守保留。

### 參數驅動 `MongoClient(mongo_uri)`（~81 處）→ Phase 2
這些已透過建構子參數 + env 驅動（`MongoClient(mongo_uri)`，`mongo_uri` 預設讀 `MONGODB_URI`），
**非硬編碼債**。正式收斂為 `MongoStockRepository` 單一入口 + 連線池屬 **Phase 2** 範疇，
需搭配 65 集合名常數化，分批遷移並以測試回歸。

## 風險與注意事項
- **標準 CLI 呼叫方式**：移除 `sys.path.insert` 的模組，如需獨立執行請用 `python -m src.<module>`（套件語境），而非 `python src/<module>.py`。
- **本機驗證侷限**：scipy/sklearn/xgboost/finmind/streamlit 未安裝，部分模組與測試僅能靠 AST + fresh-process import 驗證；完整回歸須在部署環境執行 CI（已含 `pip install -e ".[dev]"`）。
- **設定外部化下一步**：可將 `MONGODB_URI`/`OLLAMA_*`/`FINMIND_API_TOKEN` 寫入 `.env`，config 已支援覆寫。

## 建議下一步
1. 在完整相依環境跑 CI，驗證第 2 批 29 檔的標準 CLI（`python -m`）與整合流程。
2. 處理剩餘 8 個 `sys.path.insert`（逐一 + 真環境）。
3. 進入 **Phase 2**：`MongoStockRepository` 單一入口 + 65 集合常數化 + 參數驅動 MongoClient 收斂。
