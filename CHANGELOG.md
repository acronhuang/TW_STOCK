# Changelog

## [2.2.0] - 2026-04-19

### Added
- `pyproject.toml` — Python 標準套件設定
- `Makefile` — 一鍵指令（test/api/scan/backup）
- `Dockerfile` + `.dockerignore` — 容器化部署
- `INSTALL.md` — 完整安裝教學
- `ARCHITECTURE.md` — 系統架構文件（DDD）
- `API.md` — REST API 端點文件
- `CHANGELOG.md` — 本文件
- `src/analysis/financial_filter.py` — 財報地雷篩檢（TTM 虧損/高負債）
- `src/analysis/financial_health.py` v2 — 6 維財報健康分析（杜邦/TTM）
- `src/strategy/trading_rules.py` — 北大四大法則（334倉位/5%止損/買入三問/週期）
- `src/moe/router.py` — MoE 多模型路由（5 專家）
- `src/moe/role_router.py` — 角色→模型自動派發
- `src/portfolio/tracker.py` — 投組追蹤（損益/股利/再平衡）
- `src/sentiment/analyzer.py` — 情緒分析（新聞/PTT/內部人）
- `src/ml/predictor.py` — XGBoost 5 日方向預測
- `src/ml/anomaly_detector.py` — 異常偵測（IQR/Z-Score/ML）
- `scripts/daily_recommendations.py` — 每日自動推薦 + LINE
- `scripts/daily_alert_check.py` — 每日警報 + 北大法則全檢
- `scripts/team_analyze.py` — 7 人團隊一鍵分析
- `scripts/weekly_team_verify.py` — 週六深度驗證
- Hermes Agent 整合（取代 OpenClaw）
- 8 個 Hermes skills（macro/fundamental/value/technical/chip/risk/advisor/orchestrator）
- LINE Messaging API 通知（停損/目標/爆量/每日摘要）

### Changed
- `src/analysis/stock_ranker.py` — 品質分改用 FinancialHealthAnalyzer
- `src/analysis/valuation_models.py` — 修正 EPS TTM 計算 Bug（Q4 累計值誤判）
- `src/analysis/valuation_models.py` — WACC 下限 8%、DDM 成長率上限 5%、PE Band 截尾
- `scripts/daily_senvision.sh` — 加入 MongoDB 連線檢查（斷線自動重連）

### Fixed
- TTM EPS 誤判 Q4 為累計值（2706 第一店 EPS 0.65 → 1.21）
- PE Band 歷史 PE 異常膨脹（排除 PE < 5 和 > 60）
- `momentum_factors.py` NoneType 減法錯誤
- `sync_dividend_detail.py` Decimal128 比較錯誤
- 路徑從 ~/Desktop/Stock 遷移至 ~/Stock（26 個檔案）

## [2.1.0] - 2026-02-25
- SenVision 多時間框架掃描系統
- 型態辨識（W底/M頭/頭肩）
- Decimal128 資料遷移（P0/P1/P2）

## [2.0.0] - 2025-12-01
- 從 NestJS 遷移至 Python
- MongoDB 統一 schema
- 因子計算系統
