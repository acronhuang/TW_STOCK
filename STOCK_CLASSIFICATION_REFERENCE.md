# 股票分类快速参考

## 🔍 识别规则速查

```
代码格式              → 类型            → 示例
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[1-9]XXX            → Stock         → 2330, 1101, 2317
00XX / 00XXXX       → ETF           → 0050, 006208
00XXX[A-Z]          → ETF           → 00633L, 00634R
XXXXX + T           → Warrant       → 01004T, 01007T
XXXX[A-Z]           → PreferredStock→ 1101B, 1312A
含 "-KY"            → KY-Stock      → 1256-KY
含 "DR"             → DR            → (罕见)
其他                → Unknown       → 
```

## 📊 数据需求速查

```
                 价格 财报 股利 股数 本益 法人 融资
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stock             ✅   ✅   ✅   ✅   ✅   ✅   ✅
ETF               ✅   ❌   ✅   ❌   ❌   ❌   ❌
KY-Stock          ✅   ✅   ✅   ✅   ✅   ❌   ❌
PreferredStock    ✅   ✅   ✅   ✅   ❌   ❌   ❌
Warrant           ❌   ❌   ❌   ❌   ❌   ❌   ❌
DR                ✅   ❌   ✅   ❌   ❌   ❌   ❌
Unknown           ❌   ❌   ❌   ❌   ❌   ❌   ❌
```

## 📈 当前数据库分布

```
证券类型          数量        占比
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stock           1,864 支   79.7%
ETF               308 支   13.2%
KY-Stock          117 支    5.0%
PreferredStock     50 支    2.1%
Warrant             2 支    0.1%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计            2,341 支  100.0%
```

## 🚀 快速使用

### Python 代码

```python
from utils.stock_classifier import StockClassifier, SecurityType

# 1. 快速分类
classifier = StockClassifier()
stock_type = classifier.classify_by_code('2330', '台积电')
# → SecurityType.STOCK

# 2. 判断需求
needs_financial = StockClassifier.should_download_financials(SecurityType.ETF)
# → False

# 3. 获取完整需求
requirements = StockClassifier.get_data_requirements(SecurityType.STOCK)
# → {'price': True, 'financials': True, ...}
```

### 命令行

```bash
# 生成分类报告
python3 scripts/classified_downloader.py

# 查看报告
cat logs/stock_classification_report.txt

# MongoDB 分析
mongosh tw_stock_analysis < scripts/analyze_stock_classification.js
```

## 💾 相关文件

```
股票分类系统
├── src/utils/stock_classifier.py          # 核心模块
├── scripts/classified_downloader.py       # 分析工具
├── scripts/analyze_stock_classification.js# MongoDB 脚本
├── logs/stock_classification_report.txt   # 输出报告
├── STOCK_CLASSIFICATION_GUIDE.md          # 完整文档 ⭐
└── STOCK_CLASSIFICATION_REFERENCE.md      # 本文件
```

## 🎯 效益总结

- **财报**: 减少 310 支 (13.2%) → 节省 ~4,650 次 API 调用
- **本益比**: 减少 360 支 (15.4%)
- **法人/融资**: 减少 477 支 (20.4%)

---

**详细文档**: [STOCK_CLASSIFICATION_GUIDE.md](STOCK_CLASSIFICATION_GUIDE.md)
