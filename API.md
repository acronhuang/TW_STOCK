# REST API 文件

Base URL: `http://localhost:8888`
Swagger UI: `http://localhost:8888/docs`

## 端點列表

### 市場總覽
| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/health` | 系統健康檢查 |
| GET | `/api/macro` | 總經環境+市場訊號 |
| GET | `/api/ranking?limit=20` | 綜合選股排行 |
| GET | `/api/scan?limit=20` | 全市場掃描+風險 |
| GET | `/api/stocks?limit=50` | 列出所有股票 |

### 個股分析
| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/price/{symbol}?days=20` | 股價 OHLCV |
| GET | `/api/factors/{symbol}` | PE/PB/殖利率/RSI |
| GET | `/api/financial/{symbol}` | 6維財報健康分析 |
| GET | `/api/valuation/{symbol}` | DCF+DDM+PE Band |
| GET | `/api/risk/{symbol}` | VaR/Sharpe/MDD |
| GET | `/api/peer/{symbol}` | 同業比較 |
| GET | `/api/score/{symbol}` | 單股綜合評分 |

### 籌碼/營收/股利
| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/institutional/{symbol}?days=10` | 法人買賣超 |
| GET | `/api/revenue/{symbol}?months=6` | 月營收 |
| GET | `/api/dividend/{symbol}` | 股利明細 |

### 情緒/預測/異常
| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/sentiment/{symbol}` | 新聞情緒 |
| GET | `/api/predict/{symbol}` | ML 5日預測 |
| GET | `/api/anomaly/{symbol}?days=30` | 異常偵測 |

### 策略
| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/advisor?capital=5000000` | 交易建議 |

### 回應格式
所有端點回傳 JSON。數值型欄位已轉為 float（原 Decimal128）。

## 使用範例

### 查詢個股完整分析
```bash
curl -s http://localhost:8888/api/financial/2330 | python3 -m json.tool
```
回傳：
```json
{
  "symbol": "2330",
  "total_score": 78.8,
  "grade": "A 良好",
  "scores": {"profitability": 100, "growth": 73.6, "safety": 98.9, ...},
  "ttm": {"eps": 113.01, "revenue": 2766800000000, "net_margin": 44.1},
  "dupont": {"roe_pct": 24.1, "net_margin_pct": 43.8, "asset_turnover": 0.38}
}
```

### 全市場掃描（Top 10 + 風險）
```bash
curl -s "http://localhost:8888/api/scan?limit=10" | python3 -m json.tool
```

### 總經快速判斷
```bash
curl -s http://localhost:8888/api/macro | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f\"評分: {d['signal']['score']:+.0f} {d['signal']['verdict']}\")
"
```

## 錯誤處理

| HTTP | 意義 | 範例 |
|------|------|------|
| 200 | 成功（含 `{"error": "..."}` 也是 200） | 正常回傳 |
| 404 | 端點不存在 | `/api/unknown` |
| 500 | 伺服器錯誤 | MongoDB 斷線 |
