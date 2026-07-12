# deploy · 部署與災難復原（config-as-code）

本目錄把**系統級設定**納入版控——過去這些只存在 `.166` 的 crontab / systemd，機器一掛就得憑記憶重蓋。現在 `git clone` 即可重建。

## 內容

| 檔案 | 是什麼 | 對應線上位置 |
|---|---|---|
| `crontab.txt` | 30 條排程（資料更新／完整度自癒／看門狗／備份…）| `crontab -l`（使用者 mdsadmin，`TZ=Asia/Taipei`）|
| `systemd/twstock-api.service` | FastAPI :8888 常駐 | `/etc/systemd/system/twstock-api.service` |
| `systemd/twstock-dashboard.service` | Streamlit :8501 常駐 | `/etc/systemd/system/twstock-dashboard.service` |

> 這些是**匯出快照**。若線上有變更，重新 `crontab -l > deploy/crontab.txt`、`systemctl cat … > deploy/systemd/…` 後 commit，保持一致。

## 環境基線（重建時需要）

- 主機：Ubuntu（`172.16.9.166`），使用者 `mdsadmin`
- 專案：`/home/mdsadmin/Stock/tw-stock-analysis`
- venv：`/home/mdsadmin/Stock/.venv`（**在專案外**，故未入版控）
- DB：本機 MongoDB，database `tw_stock_analysis`
- 模型節點：`.28`（qwen2.5）、`.27`（合議 hermes3+qwen2.5）
- 備份：`~/Stock/mongodb_backups/*.tar.gz`（週日 01:00 cron），還原性每週驗（`verify_backup.py`）

## 從零重建（.166 全毀時）

```bash
# 1) 系統套件
sudo apt update && sudo apt install -y python3-venv mongodb-org cron git

# 2) 取回程式
git clone <REMOTE_URL> /home/mdsadmin/Stock/tw-stock-analysis
cd /home/mdsadmin/Stock/tw-stock-analysis

# 3) 建 venv 裝套件
python3 -m venv /home/mdsadmin/Stock/.venv
/home/mdsadmin/Stock/.venv/bin/pip install -r requirements.txt

# 4) 還原機密（不在版控）
cp .env.example .env && vim .env      # 填 MONGODB_PASSWORD / FINMIND_API_TOKEN / LINE_*

# 5) 還原資料（取最新備份）
tar -xzf ~/Stock/mongodb_backups/<最新>.tar.gz -C /tmp/restore
mongorestore --db tw_stock_analysis /tmp/restore/<dump_dir>

# 6) 掛回常駐服務
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now twstock-api twstock-dashboard

# 7) 掛回排程（先確認時區！）
sudo timedatectl set-timezone Asia/Taipei
crontab deploy/crontab.txt

# 8) 驗證
/home/mdsadmin/Stock/.venv/bin/python3 scripts/twse_openapi_sync.py --check-only   # 應全綠
/home/mdsadmin/Stock/.venv/bin/python3 scripts/watchdog.py --status
curl -s localhost:8888/health && curl -sI localhost:8501
```

## 日常：改了設定要同步回版控

```bash
crontab -l > deploy/crontab.txt
systemctl cat twstock-api > deploy/systemd/twstock-api.service
systemctl cat twstock-dashboard > deploy/systemd/twstock-dashboard.service
git add deploy && git commit -m "chore(deploy): 同步線上 cron/systemd 變更"
```

> ⚠️ 時區是最危險的坑：cron 依系統時區判時。務必 `Asia/Taipei`，否則每日更新會跑錯時間、少抓一天（見運維手冊）。
