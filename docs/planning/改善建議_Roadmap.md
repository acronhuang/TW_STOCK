# 改善建議 Roadmap（Phase 3 起步）

> 依「股票分析系統改善建議」實作的首批：資料品質監控、備份健康、AI 品質回饋。
> 全程 TDD、純函式核心（fake db 可測，無需 live Mongo），可漸進接入排程。

## 已實作模組（本批）

| 建議 | 模組 | 測試 | 狀態 |
|---|---|---|---|
| #1 資料品質監控 + 驗證層 | `src/monitoring/data_quality.py` | `tests/test_data_quality.py`（6） | ✅ |
| #2 備份健康（消除靜默失敗） | `src/monitoring/backup_health.py` | `tests/test_backup_health.py`（4） | ✅ |
| #3 AI verdict 品質回饋迴路 | `src/audit/verdict_tracker.py` | `tests/test_verdict_tracker.py`（6） | ✅ |
| 排程入口（#1+#2 整合） | `scripts/data_health_check.py` | — | ✅ |

**共 16 單元測試綠、ruff 乾淨。**

## #1 資料品質監控 — API
```python
from src.monitoring.data_quality import run_health_check
report = run_health_check(db, {
    "freshness": {"stock_price": {"date_field": "date", "max_age_days": 4}, ...},
    "coverage":  {"tickers": 1000, ...},
})
# report: {ok, stale_count, low_coverage_count, alerts[], freshness[], coverage[]}
```
- `check_freshness` — 各集合最新日期 vs 上限 → 落後即 flag。
- `check_coverage` — 文件數 vs 門檻。
- `validate_document(doc, {field: (min,max)})` — 入庫前範圍/schema 驗證（擋髒資料，如 EPS/PE 異常）。

## #2 備份健康 — API
```python
from src.monitoring.backup_health import check_backup_freshness
r = check_backup_freshness("~/Stock/mongodb_backups", max_age_hours=48)
# r: {ok, latest, age_hours, count} — 過期/缺失 → ok=False
```

### 部署動作（需你在 .166 執行）
1. **改每日備份**（原每週日）—— 編輯 crontab：
   ```cron
   # 原： 0 1 * * 0  ... backup_mongodb.sh
   0 1 * * *  cd /home/mdsadmin/Stock/tw-stock-analysis && /bin/bash backup_mongodb.sh --keep-days 14 >> logs/cron_daily_mongodb_backup.log 2>&1  # daily_mongodb_backup
   ```
2. **加資料健康檢查排程**（每時或每日）：
   ```cron
   0 8 * * *  cd /home/mdsadmin/Stock/tw-stock-analysis && /home/mdsadmin/Stock/.venv/bin/python3 scripts/data_health_check.py >> logs/cron_data_health.log 2>&1  # data_health_check
   ```
   → 寫入 `data_health_history` + 異常時 `schedule_alerts`（網頁可見）。

## #3 AI verdict 品質回饋 — API 與接線
```python
from src.audit.verdict_tracker import evaluate_verdict, compute_metrics
# 到期 verdict（如 20 交易日前）比對現價：
ev = [evaluate_verdict(rec, later_price=cur[rec["symbol"]]) for rec in matured]
metrics = compute_metrics([e for e in ev if e])
# metrics: {n, hit_rate, avg_return, by_verdict: {買進/賣出/持有: {n, hit_rate}}}
```
**接線待辦（下一步）**：
1. 在 `team_daily_verified` 寫 `team_analysis` 時，一併記 `entry_price`（當日收盤）與 `verdict`、`date`。
2. 新增 `scripts/verdict_attribution.py`：每日撈「N 交易日前」的 verdict，取現價算命中率，寫 `verdict_metrics` 集合。
3. Dashboard 加「AI 命中率 / 校準」面板 → 換模型/節點/prompt 的 A/B 才有客觀依據。

## 設計原則（延續 Phase 0-2）
- 純函式核心 + 注入 db → fake db 單元測試，CI 不依賴 live Mongo。
- 預設唯讀主資料；只寫 `data_health_history`/`schedule_alerts`（非業務集合）。
- 門檻可設定化（未來移入 `src/config.py` 或設定檔）。

## 後續（Phase 3 其餘）
- 高頻集合全樹採用 `COLL_*` + 37 處 MongoClient 收斂到 repository。
- MongoDB replica set（自動 failover）。
- GPU 動態負載平衡（真實 `nvidia-smi` 查詢取代假 GPUManager）。
- Dashboard 反向代理 + SSO。
- 上帝模組拆薄殼。
