# Phase 3 進度追蹤 — 收尾工程

> 承接 Phase 0（止血）/ Phase 1（設定收斂）/ Phase 2（資料層收斂）。
> Phase 3 聚焦：每日備份、上帝模組拆分、MoE 雙路由合併、（Dashboard SSO 暫緩）。
> 全程 TDD / 等價轉換 / 每步獨立可回滾；本機無 MongoDB，DB 行為以正式環境（172.16.9.166）驗證。

---

## ✅ 已完成

### 1. 每日備份（原每週 → 每日）
- `deploy/crontab.txt`：`weekly_mongodb_backup` → `daily_mongodb_backup`（每日 01:00、`--keep-days 14`）。
- 對齊既有 `backup_health.check_backup_freshness`（48h 新鮮度門檻）——原每週會誤報「備份過期」。
- 搭配既有 `data_health_check.py`（每日）＋ `verify_backup.py`（每週還原性驗證）形成閉環。
- `crontab_examples.txt` / `MONGODB_BACKUP_GUIDE.md` 同步更新。
- Commit：`ebad9d4`

### 2. Phase 2 續批 — 裸集合存取全樹歸零
- 全樹 `db.<coll>` / `db['<coll>']` 裸存取 → `db[COLL_*]`（pymongo 屬性↔getitem 語義等價）。
- 涵蓋 **51 檔**（analysis / alerts / api / strategy / factors / cli / senvision / calculators /
  downloaders / sentiment / ml / moe / monitoring / portfolio / backtesting / chip_analysis / utils）。
- 驗證：殘留處數 **0**；CI ruff 選定規則（E9/F82/F821/I001/…）All checks passed；py_compile 全通過；
  純邏輯模組 import 煙霧測試 OK；常數存在性驗證通過。
- Commit：`b3bb19d`（analysis 10 檔）、`786da24`（其餘 41 檔）
- **剩餘**：37 處參數驅動 `MongoClient` 收斂到 repository 唯一入口（獨立小任務，另行處理）。

### 3. 上帝模組拆分 — senvision/pattern_detector（843 → 111 行薄殼）⭐ 範式
- 拆為 `senvision/patterns/` 子套件（單一職責）：
  | 檔案 | 職責 |
  |---|---|
  | `types.py` | `PatternType` / `PatternStatus` / `Pattern` |
  | `base.py` | `PatternDetector`（信心度/風報比/量能確認共用邏輯） |
  | `w_bottom.py` | `WBottomDetector`（W 底） |
  | `m_top.py` | `MTopDetector`（M 頭） |
  | `triple_bottom.py` | `TripleBottomDetector`（三重底） |
  | `triple_top.py` | `TripleTopDetector`（三重頂） |
  | `__init__.py` | 一次匯出全部 |
- `pattern_detector.py` 縮為薄殼 re-export，**完全保留舊 import 介面** →
  analysis / scanner / chart_visualizer / pattern_bridge / `__init__` 呼叫端零改動。
- 驗證：舊/新 import 路徑全解析、繼承鏈與 `Pattern` 型別 identity 一致、demo 合成資料實跑、
  `test_senvision_simple` 與 HEAD 結果逐字一致（行為保留、零回歸）。
- Commit：`f4e548a`

---

## 🔜 剩餘（上帝模組續拆 — 建議搭配正式環境測試逐一進行）

> 以下模組多為 DB 依賴，拆分後除 import/ruff 驗證外，**應在 172.16.9.166 跑實機測試**確認行為零回歸，
> 故列為續辦（沿用 pattern_detector 的「子套件 + 薄殼 re-export」範式）。

| 模組 | 行數 | 拆分建議 |
|---|---|---|
| `senvision/scanner.py` | 668 | 掃描主流程 / 各形態掃描器 / 輸出格式化 分層 |
| `strategy/integrated_strategy_v21.py` | 627 | 訊號產生 / 權重計算 / 決策彙整 拆薄殼 |
| `strategy/hsieh_dividend.py` | 620 | 股利選股規則 / 評分 / 資料存取 分離 |
| `strategy/multi_factor_strategy.py` | 592 | 因子載入 / 打分 / 排序 分離 |
| `analysis/valuation_models.py` | 603 | DCF / 相對估值 / 河流圖 各估值法分檔 |
| `analysis/technical_analyzer.py` | 501 | 指標計算 / 訊號判讀 分離 |
| `downloaders/download_coordinator.py` | 540 | 排程協調 / 各來源 downloader 分離 |

### 其他 Phase 3 待辦
- **MoE 雙路由合併**：現有兩套路由邏輯收斂為單一入口。
- **`MongoClient` 收斂**：37 處參數驅動連線 → repository 唯一入口。
- **Dashboard SSO**：暫緩（目前個人單機使用，無對外曝險需求）。

---

## 🔖 Phase 3 commits
| Commit | 里程碑 |
|---|---|
| `20a3286` | Dashboard SSO 暫緩（個人使用） |
| `ebad9d4` | 週備份 → 每日備份 + 資料健康/還原驗證排程 |
| `b3bb19d` | Phase2 續批 — analysis/ 10 模組 COLL_* |
| `786da24` | Phase2 續批 — 其餘 41 檔 COLL_*（裸存取歸零） |
| `f4e548a` | 上帝模組拆分 — pattern_detector 843→111 薄殼 |
