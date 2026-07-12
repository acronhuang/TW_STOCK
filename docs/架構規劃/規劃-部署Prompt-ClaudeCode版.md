# 規劃 · 部署 Prompt（Claude Code 版）

> 可直接貼給 Claude Code（或同類 agent）的部署指令模板。人工手冊見 [部署Prompt手冊](規劃-部署Prompt手冊.md)。使用前替換 `<角括號>` 內佔位符。

---

## 使用方式

1. 在**目標主機**上開 Claude Code（或用 SSH 讓 agent 連上）。
2. 貼下方 Prompt，替換佔位符。
3. Agent 應逐步執行並在每個里程碑回報，遇破壞性操作先確認。

---

## Prompt A · 全新部署（貼給 Claude Code）

```
你要在這台 Ubuntu 主機部署「台股智能分析系統」。環境與架構參照專案內
docs/架構規劃/ 下的文件（環境基線、部署Prompt手冊、2節點試點瘦身版）。

前提資訊（我提供）：
- 專案來源：<stock_code.tgz 路徑 或 git repo>
- 資料庫 dump：<twstock.gz 路徑，或「無，從頭暖機」>
- 推理節點 Node-B IP：<IP>（已裝 Ollama，已 pull qwen2.5:14b / qwen2.5:3b / hermes3:8b）
- FinMind token：<token>；LINE token：<可留空>
- 部署模式：<全量 / 2節點瘦身試點>

請依序執行並在每步回報：
1. 安裝 MongoDB 8.0、Python 3.12 venv、相依套件。
2. 【關鍵】設定系統時區為 Asia/Taipei（勿留 UTC），並確認 cron 會用此時區。
3. 解開專案到 ~/Stock，建 venv 裝套件。
4. 若有 dump 則 mongorestore；否則跑 twse_daily_update + parallel_factor_calculation
   (近30天) + twse_quarterly_sync + macro_sync 暖機。
5. 寫 .env（MONGODB_URI、OLLAMA_URL 與 OLLAMA_CONSENSUS_URL 指向 Node-B、
   FINMIND_API_TOKEN、LINE_*）。全域取代任何硬編碼 /home/mdsadmin/Stock 路徑。
6. 建 systemd 服務 twstock-api(:8888,綁127.0.0.1) 與 twstock-dashboard(:8501,綁0.0.0.0)，
   enable --now。
7. 建 cron（TZ=Asia/Taipei）：hourly_data_update / daily_senvision / macro_sync /
   daily_recommendations / twse_openapi_sync / team_daily_50 / 21:00 完整度檢查。
8. 冒煙測試：/api/health 回 ok、twse_openapi_sync --check-only 全綠、
   daily_recommendations --no-line 有輸出、team_daily_verified --symbols 2330 --no-line
   能產出合議定案、dashboard :8501 回 200。

限制與注意：
- 破壞性操作（drop/覆寫/restart）先讓我確認。
- 勿用 nohup/setsid 手動跑 streamlit（會被 SIGHUP 殺）；一律 systemd。
- Ollama 須聽 0.0.0.0 本機才連得到；若連不到先確認 Node-B 的 OLLAMA_HOST。
- 財報一律用 quarterly_earnings，勿用 financial_reports。
- 完成後輸出：各服務狀態、cron 清單、冒煙測試結果、與 docs/架構規劃/環境基線.md 的差異。
```

---

## Prompt B · 健檢/巡檢（貼給 Claude Code）

```
請對這台台股分析主機做健檢，只讀不改，最後給報告：
1. systemctl 狀態：twstock-api、twstock-dashboard、mongod、cron 是否 active。
2. 時區：timedatectl 是否 Asia/Taipei。
3. 資料新鮮度：mongosh 查 stock_price / stock_factors / institutional_flow /
   quarterly_earnings 各自最新 date，與今日對照。
4. 完整度：跑 scripts/twse_openapi_sync.py --check-only。
5. 團隊分析：team_analysis 最新一日的 final_verdict 覆蓋數 + verify.status 分布。
6. 推理節點：curl Node-B:11434/api/tags 確認模型在線。
7. 磁碟/記憶體：df -h、free -h。
8. 對照 docs/架構規劃/規劃-紅線元件盤點與Backlog.md，標出仍未解的 P0/P1。
輸出一份 Markdown 健檢報告，紅黃綠標示。
```

---

## Prompt C · 資料補正（貼給 Claude Code，破壞性，需確認）

```
發現某交易日資料缺漏，請補正（每步先確認再寫入）：
1. 用 scripts/twse_daily_update.py 檢查該日 stock_price 筆數是否正常（~5500）。
2. 若缺，判斷是 TWSE 還是 TPEX 缺，用對應端點補（dry-run 先看再 --apply）。
3. 補完重算該窗口因子：parallel_factor_calculation --start-date X --end-date Y。
4. 若團隊分析已用過舊資料，用 reverify_team.py 找出 stale 清單，
   再對那些 symbol 重跑 team_daily_verified --symbols ...。
5. 完成後跑 reverify_team.py --finmind 30 複核，回報 fresh/stale 分布。
```

---

## 維護原則（給 agent 的長期守則）
- **以 .166 為權威**；任何本機 bundle 的差異以正式機為準。
- 動 DB schema 前先查下游（共享 DB 是隱性契約）。
- 每次架構級變更後，同步更新 docs/架構規劃/ 對應文件（四面向 + Backlog）。
- 密鑰在 .env，勿寫進程式碼或 commit。
