# 台股智能分析系統 — 安裝指南

## 系統需求

| 項目 | 最低需求 | 建議 |
|------|---------|------|
| OS | macOS 13+ / Ubuntu 22.04+ | macOS 14+ |
| Python | 3.11+ | 3.14 |
| MongoDB | 7.0+ | 7.0 (Homebrew) |
| Node.js | 20+ | 22 LTS (可選) |
| RAM | 8 GB | 16 GB+ |
| Disk | 10 GB | 50 GB（含資料庫）|
| Ollama | 0.3+（可選，本地 LLM）| qwen3.6:27b |

## 快速安裝（5 分鐘）

### 1. Clone & 建立環境

```bash
cd ~/Stock
git clone <repo-url> tw-stock-analysis
cd tw-stock-analysis

# Python 虛擬環境
python3.11 -m venv ../.venv
source ../.venv/bin/activate
pip install -e ".[dev]"
```

### 2. 安裝 MongoDB

```bash
# macOS
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community

# Ubuntu
sudo apt install -y mongodb-org
sudo systemctl start mongod
```

### 3. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env 填入：
#   FINMIND_API_TOKEN=<your token>
#   LINE_CHANNEL_ACCESS_TOKEN=<your token>
#   LINE_CHANNEL_SECRET=<your secret>
```

### 4. 初始化資料庫

```bash
# 首次下載全市場資料（約 30 分鐘）
python scripts/twse_daily_update.py

# 下載季報（約 1 小時）
python scripts/finmind_quarterly_backfill.py --resume --years 3

# 計算因子
python scripts/parallel_factor_calculation.py --workers 4
```

### 5. 安裝排程

```bash
# 複製所有 plist 到 LaunchAgents
cp com.twstock.*.plist ~/Library/LaunchAgents/

# 載入排程
for f in ~/Library/LaunchAgents/com.twstock.*.plist; do
    launchctl bootstrap gui/$(id -u) "$f"
done

# 確認
launchctl list | grep twstock
```

### 6. 啟動 API Server

```bash
python src/api/server.py &
# 開啟 http://localhost:8888/docs 確認
```

### 7. 驗證安裝

```bash
# 健康檢查
curl http://localhost:8888/api/health

# 跑測試
pytest tests/ -v

# 跑一次選股分析
python scripts/daily_recommendations.py
```

## 可選：Hermes Agent（本地 LLM 分析）

```bash
# 安裝 Hermes
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup

# 安裝 Ollama 模型
ollama pull qwen3.6:27b
ollama pull deepseek-r1:14b
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

# 測試
hermes-stock macro-analyst "大盤如何"
```

## 可選：LINE 通知

1. 到 [LINE Developers](https://developers.line.biz/) 建立 Messaging API Channel
2. 填入 `.env`：`LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_CHANNEL_SECRET`
3. 測試：`python -c "from src.alerts.line_notifier import LineNotifier; LineNotifier().send('test')"`

## 目錄結構

```
tw-stock-analysis/
├── src/                    # 核心程式碼
│   ├── analysis/           # 分析模組（估值/風險/同業/財報）
│   ├── alerts/             # LINE 通知
│   ├── api/                # FastAPI REST Server
│   ├── backtesting/        # 回測引擎
│   ├── cli/                # CLI 查詢工具
│   ├── downloaders/        # 資料下載
│   ├── factors/            # 因子計算
│   ├── indicators/         # 技術指標
│   ├── ml/                 # ML 預測
│   ├── moe/                # MoE 多模型路由
│   ├── morphology/         # 型態辨識
│   ├── portfolio/          # 投組追蹤
│   ├── sentiment/          # 情緒分析
│   ├── senvision/          # 多時間框架掃描
│   ├── strategy/           # 策略引擎 + 北大規則
│   └── utils/              # 工具
├── scripts/                # 排程腳本
├── tests/                  # pytest 測試
├── dashboard/              # Streamlit UI
├── results/                # 分析結果
├── logs/                   # 日誌
├── com.twstock.*.plist     # macOS 排程
├── .env                    # 環境設定
├── pyproject.toml          # Python 套件設定
├── requirements.txt        # 依賴清單
└── docker-compose.yml      # Docker 設定
```
