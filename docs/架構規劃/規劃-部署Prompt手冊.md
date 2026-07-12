# 規劃 · 部署手冊

> 從零在新機重建本系統的人工操作手冊。對應 [環境基線](規劃-環境基線.md) 與 [2 節點試點瘦身版](規劃-2節點試點瘦身版.md)。Claude Code 自動化版見 [部署Prompt-ClaudeCode版](規劃-部署Prompt-ClaudeCode版.md)。

---

## 前置需求

| 項目 | 版本 |
|------|------|
| OS | Ubuntu 22.04+ |
| Python | 3.12（`python3.12-venv`） |
| MongoDB | 8.0（需 CPU 支援 AVX） |
| GPU 節點 | Ollama + ≥16GB VRAM |
| Token | FinMind API token、LINE channel token（可選） |

---

## 步驟 1 · 主機（Node-A）基礎

```bash
sudo apt update
sudo apt install -y python3.12-venv python3-pip build-essential gnupg curl
# MongoDB 8.0
curl -fsSL https://pgp.mongodb.com/server-8.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg] \
https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
sudo apt update && sudo apt install -y mongodb-org
sudo systemctl enable --now mongod
# 時區（關鍵！勿留 UTC）
sudo timedatectl set-timezone Asia/Taipei
```

## 步驟 2 · 專案與 venv

```bash
mkdir -p ~/Stock && cd ~/Stock
tar -xzf /path/to/stock_code.tgz          # 或 git clone
python3 -m venv .venv
.venv/bin/pip install -r tw-stock-analysis/requirements.txt fastapi uvicorn streamlit plotly pandas psutil pymongo paramiko python-dotenv
```

## 步驟 3 · 還原資料庫（若有 dump）

```bash
mongorestore --gzip --archive=/path/to/twstock.gz --drop
```
或不還原、從頭抓 30 天暖機（步驟 6）。

## 步驟 4 · 推理節點（Node-B）

```bash
# 於 GPU 機
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b        # 對映 role_router 的 qwen2.5-14b:latest
ollama pull qwen2.5:3b
ollama pull hermes3:8b
# 對外監聽（讓 Node-A 連得到）
sudo systemctl edit ollama     # 加 Environment=OLLAMA_HOST=0.0.0.0
sudo systemctl restart ollama
```

## 步驟 5 · 設定 `.env`

```
MONGODB_URI=mongodb://localhost:27017
OLLAMA_URL=http://<Node-B-IP>:11434
OLLAMA_CONSENSUS_URL=http://<Node-B-IP>:11434   # 瘦身版同一台；全量版指向 .27
FINMIND_API_TOKEN=<token>
LINE_CHANNEL_ACCESS_TOKEN=<...>
LINE_CHANNEL_SECRET=<...>
LINE_USER_ID=<...>
```
> ⚠️ 若程式含硬編碼 `/home/mdsadmin/Stock`，用編輯器全域取代為新家目錄。

## 步驟 6 · 首次暖機（不還原 DB 時）

```bash
cd ~/Stock/tw-stock-analysis
.venv/bin/python3 scripts/twse_daily_update.py       # 抓當日股價/法人/PE
.venv/bin/python3 scripts/parallel_factor_calculation.py --workers 4 \
    --start-date $(date -d '30 days ago' +%F) --end-date $(date +%F)
.venv/bin/python3 scripts/twse_quarterly_sync.py     # 季報
.venv/bin/python3 scripts/macro_sync.py              # TAIEX+總經
```

## 步驟 7 · systemd 服務

```bash
# /etc/systemd/system/twstock-api.service
[Unit]
Description=TW Stock API Server (FastAPI :8888)
After=network.target mongod.service
[Service]
Type=simple
User=<user>
WorkingDirectory=/home/<user>/Stock/tw-stock-analysis
Environment=PATH=/home/<user>/Stock/.venv/bin:/usr/bin:/bin
ExecStart=/home/<user>/Stock/.venv/bin/python3 src/api/server.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
Dashboard 服務同理，ExecStart 改：
```
ExecStart=/home/<user>/Stock/.venv/bin/streamlit run app.py \
  --server.port 8501 --server.address 0.0.0.0 --server.headless true
```
（WorkingDirectory 設 `dashboard/`）
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now twstock-api twstock-dashboard
```

## 步驟 8 · cron（TZ=Asia/Taipei）

```cron
TZ=Asia/Taipei
PATH=/home/<user>/Stock/.venv/bin:/usr/bin:/bin
5 * * * *     cd .../tw-stock-analysis && bash scripts/hourly_data_update.sh >> logs/cron_hourly_update.log 2>&1
0 17 * * 1-5  cd .../tw-stock-analysis && bash scripts/daily_senvision.sh >> logs/cron_daily_senvision.log 2>&1
10 17 * * 1-5 cd .../tw-stock-analysis && python3 scripts/macro_sync.py >> logs/cron_daily_macro_sync.log 2>&1
30 17 * * 1-5 cd .../tw-stock-analysis && python3 scripts/daily_recommendations.py >> logs/cron_daily_recommendations.log 2>&1
30 17 * * 1-5 cd .../tw-stock-analysis && python3 scripts/twse_openapi_sync.py >> logs/cron_daily_openapi_sync.log 2>&1
30 18 * * 1-5 cd .../tw-stock-analysis && bash scripts/team_daily_50.sh >> logs/cron_daily_team.log 2>&1
0 21 * * 1-5  cd .../tw-stock-analysis && python3 scripts/twse_openapi_sync.py --check-only >> logs/cron_integrity.log 2>&1
```

## 步驟 9 · 冒煙測試（Smoke Test）

```bash
curl -s http://localhost:8888/api/health                          # {status:ok}
.venv/bin/python3 scripts/twse_openapi_sync.py --check-only        # 完整度全綠
.venv/bin/python3 scripts/daily_recommendations.py --no-line       # 四法選股
.venv/bin/python3 scripts/team_daily_verified.py --symbols 2330 --no-line  # 團隊分析單檔
curl -s http://localhost:8501 -o /dev/null -w '%{http_code}\n'     # 200
```

---

## 常見陷阱（承本次移轉經驗）

| 陷阱 | 症狀 | 解 |
|------|------|-----|
| 時區留 UTC | cron 跑錯時間、少抓一天 | `timedatectl set-timezone Asia/Taipei` + restart cron |
| launchctl | 監控頁報錯 | 本版已改 cron/systemd |
| 硬編碼 Desktop 路徑 | 路徑不存在 | 全域取代 / 用 PROJECT_ROOT |
| Ollama 只聽 localhost | Node-A 連不到 | `OLLAMA_HOST=0.0.0.0` |
| streamlit 手動啟動被 SIGHUP | 服務一啟動就死 | 用 systemd（勿 nohup/setsid 手動跑） |
| 財報指向 financial_reports | 多數股票查無 | 用 quarterly_earnings |
