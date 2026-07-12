# 台股智能分析系統 Makefile
PYTHON = /Users/ming/Stock/.venv/bin/python3
PIP = /Users/ming/Stock/.venv/bin/pip
PROJECT = /Users/ming/Stock/tw-stock-analysis

.PHONY: help install test lint api scan recommend team backup clean

help:  ## 顯示所有指令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## 安裝依賴
	$(PIP) install -e ".[dev]"

test:  ## 跑 pytest
	cd $(PROJECT) && $(PYTHON) -m pytest tests/ -v --tb=short

lint:  ## 程式碼檢查
	cd $(PROJECT) && $(PYTHON) -m ruff check src/

api:  ## 啟動 API Server
	cd $(PROJECT) && $(PYTHON) src/api/server.py

scan:  ## 全市場掃描
	cd $(PROJECT) && $(PYTHON) scripts/daily_recommendations.py

recommend:  ## 今日推薦（含財報篩檢）
	cd $(PROJECT) && $(PYTHON) scripts/daily_recommendations.py

team:  ## 7人團隊分析（需指定代號）
	cd $(PROJECT) && $(PYTHON) scripts/team_analyze.py $(ARGS)

alert:  ## 執行警報檢查（含北大法則）
	cd $(PROJECT) && $(PYTHON) scripts/daily_alert_check.py

update:  ## 更新資料（daily_senvision）
	cd $(PROJECT) && bash scripts/daily_senvision.sh

backup:  ## 備份 MongoDB
	cd $(PROJECT) && bash backup_mongodb.sh

health:  ## 健康檢查
	@curl -s http://localhost:8888/api/health | python3 -m json.tool

status:  ## 資料更新狀態
	@$(PYTHON) -c "from dotenv import load_dotenv;load_dotenv('$(PROJECT)/.env');from pymongo import MongoClient;import os;db=MongoClient(os.getenv('MONGODB_URI'))['tw_stock_analysis'];sp=db.stock_price.find_one({},{'date':1},sort=[('date',-1)]);print(f'stock_price: {str(sp[\"date\"])[:10]}')"

schedules:  ## 列出所有排程
	@launchctl list | grep twstock

clean:  ## 清理日誌和快取
	find $(PROJECT)/logs -name "*.log" -mtime +30 -delete
	find $(PROJECT) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
