# 股票分类系统使用指南

## 📋 概述

股票分类系统根据证券类型自动决定需要下载的数据类型，避免对 ETF 下载财报、对权证下载历史数据等无意义操作。

**生成时间**: 2026-02-24  
**最后更新**: 2026-02-24

---

## 🏷️ 证券类型分类

### 1. 正常股票 (Stock)
- **识别规则**: 4位数字代码，1-9开头
- **示例**: 2330 (台积电)、2317 (鸿海)、1101 (台泥)
- **数量**: 1,864 支 (79.7%)

### 2. ETF (Exchange Traded Fund)
- **识别规则**: 00开头
  - 4位数: 0050、0051、0056
  - 6位数: 006208
  - 带字母: 00633L (杠杆)、00634R (反向)、00635U
- **示例**: 0050 (元大台湾50)、0056 (元大高股息)
- **数量**: 308 支 (100.0%)

### 3. KY股 (KY-Stock)
- **识别规则**: 股票名称包含 "-KY"
- **说明**: 海外注册、台湾上市的企业
- **示例**: 1256-KY、1258-KY
- **数量**: 117 支 (27.5%)

### 4. 特别股 (PreferredStock)
- **识别规则**: 4位数字 + 大写字母
- **示例**: 1101B (台泥特)、1312A (国泰特)
- **数量**: 50 支 (10.5%)

### 5. 权证 (Warrant)
- **识别规则**: 5位数字 + T
- **示例**: 01004T、01007T
- **数量**: 2 支 (0.1%)

### 6. 存托凭证 (DR)
- **识别规则**: 代码包含 "DR"
- **说明**: Depositary Receipt
- **数量**: 极少

### 7. 未知 (Unknown)
- **说明**: 无法识别的特殊代码
- **处理**: 默认不下载任何数据

---

## 📊 数据需求矩阵

| 数据类型 | Stock | ETF | KY-Stock | PreferredStock | Warrant | DR |
|---------|:-----:|:---:|:--------:|:--------------:|:-------:|:--:|
| **股价 (price)** | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **财报 (financials)** | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| **股利 (dividends)** | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **流通股数 (shares)** | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| **本益比 (per_pbr)** | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **三大法人** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **融资融券** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 数据下载统计

根据 2,341 支证券的分析：

| 数据类型 | 需要下载 | 比例 | 说明 |
|---------|---------|------|------|
| **股价数据** | 2,339 支 | 99.9% | 几乎所有证券（权证除外）|
| **股利数据** | 2,339 支 | 99.9% | Stock + ETF + KY + 特别股 |
| **财报数据** | 2,031 支 | 86.8% | Stock + KY + 特别股 |
| **流通股数** | 2,031 支 | 86.8% | Stock + KY + 特别股 |
| **本益比** | 1,981 支 | 84.6% | Stock + KY |
| **三大法人** | 1,864 支 | 79.6% | 仅 Stock |
| **融资融券** | 1,864 支 | 79.6% | 仅 Stock |

---

## 🔧 使用方式

### 1. 基本分类

```python
from utils.stock_classifier import StockClassifier, SecurityType

# 创建分类器（不连接数据库）
classifier = StockClassifier()

# 分类单支股票
stock_type = classifier.classify_by_code('2330', '台积电')
print(f"2330: {stock_type}")  # Output: 2330: SecurityType.STOCK

etf_type = classifier.classify_by_code('0050', '元大台湾50')
print(f"0050: {etf_type}")    # Output: 0050: SecurityType.ETF
```

### 2. 批量分类

```python
from utils.stock_classifier import StockClassifier

# 连接数据库
classifier = StockClassifier(db_connection)

# 批量分类
stock_list = ['2330', '0050', '1256', '01004T']
classified = classifier.classify_stock_list(stock_list)

# 结果
# {
#     SecurityType.STOCK: ['2330'],
#     SecurityType.ETF: ['0050'],
#     SecurityType.KY_STOCK: ['1256'],
#     SecurityType.WARRANT: ['01004T'],
#     ...
# }
```

### 3. 判断数据需求

```python
from utils.stock_classifier import StockClassifier, SecurityType

# 判断单个数据类型
needs_financial = StockClassifier.should_download_financials(SecurityType.ETF)
print(needs_financial)  # False (ETF 不需要财报)

needs_price = StockClassifier.should_download_price(SecurityType.STOCK)
print(needs_price)      # True (正常股票需要股价)

# 获取完整需求
requirements = StockClassifier.get_data_requirements(SecurityType.STOCK)
print(requirements)
# {
#     'price': True,
#     'financials': True,
#     'dividends': True,
#     'outstanding_shares': True,
#     'per_pbr': True,
#     'institutional_holdings': True,
#     'margin_trading': True
# }
```

### 4. 生成分类报告

```bash
# 运行分类分析器
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python3 scripts/classified_downloader.py > logs/classification_report.txt

# 查看报告
cat logs/classification_report.txt
```

### 5. 集成到下载流程

```python
from utils.stock_classifier import StockClassifier, SecurityType

# 在下载前判断
def download_financial_data(stock_id):
    classifier = StockClassifier(db)
    stock_type = classifier.get_type_from_db(stock_id)
    
    if not StockClassifier.should_download_financials(stock_type):
        print(f"⏭️  跳过 {stock_id}: {stock_type.value} 不需要财报数据")
        return
    
    # 执行下载
    print(f"📥 下载 {stock_id} 的财报数据...")
    # ... 下载逻辑 ...
```

---

## 📁 相关文件

### 核心模块
- **src/utils/stock_classifier.py**: 股票分类器核心实现
  - `SecurityType`: 证券类型枚举
  - `StockClassifier`: 分类器类

### 工具脚本
- **scripts/classified_downloader.py**: 分类分析和报告生成器
- **scripts/analyze_stock_classification.js**: MongoDB 分析脚本

### 输出报告
- **logs/stock_classification_report.txt**: 完整分类报告
- **logs/classification_report_final.log**: 执行日志

---

## 🔍 分类逻辑说明

### 优先级

1. **代码规则判断** (优先)
   - ETF: 00开头 → 立即识别
   - 权证: 5位数+T → 立即识别
   - 特别股: 4位数+字母 → 立即识别
   - 正常股票: 4位数，1-9开头 → 立即识别

2. **数据库查询** (fallback)
   - 查询 `taiwan_stock_info.security_type` 字段
   - 如果有 `stock_name`，根据名称判断 KY 股

3. **兜底处理**
   - 无法识别 → `SecurityType.UNKNOWN`
   - Unknown 类型默认不下载任何数据

### 特殊情况处理

**ETF 6位数识别**:
```python
# 006208 (富邦台50)
if re.match(r'^00\d{4}$', stock_id):
    return SecurityType.ETF
```

**KY 股识别**:
```python
# 需要 stock_name
if stock_name and '-KY' in stock_name:
    return SecurityType.KY_STOCK
```

**数据库缺失处理**:
```python
# 如果数据库中查不到，使用代码规则
if not info:
    return self.classify_by_code(stock_id)
```

---

## 📈 系统效益

### 下载效率提升

**财报数据**:
- 之前: 下载 2,341 支（100%）
- 现在: 下载 2,031 支（86.8%）
- **减少**: 310 支 (13.2%)，节省约 310 * 15年 = **4,650 次 API 调用**

**本益比数据**:
- 之前: 下载 2,341 支（100%）
- 现在: 下载 1,981 支（84.6%）
- **减少**: 360 支 (15.4%)

**三大法人/融资融券**:
- 之前: 下载 2,341 支（100%）
- 现在: 下载 1,864 支（79.6%）
- **减少**: 477 支 (20.4%)

### 数据质量提升

✅ **避免无效数据**:
- ETF 不再下载财报（财报为空）
- 权证不再下载历史数据（无意义）
- 特别股不再下载本益比（不适用）

✅ **减少错误**:
- 减少 API 调用失败
- 减少空数据存储
- 减少后续分析错误

---

## 🚀 后续改进建议

### 1. 集成到下载协调器

修改 `src/services/download_coordinator.py`:

```python
from utils.stock_classifier import StockClassifier, SecurityType

class DownloadCoordinator:
    def __init__(self, ...):
        self.classifier = StockClassifier(self.db)
    
    async def download_financial_statements(self, stock_id):
        stock_type = self.classifier.get_type_from_db(stock_id)
        
        if not StockClassifier.should_download_financials(stock_type):
            logger.info(f"⏭️  跳过 {stock_id}: {stock_type.value}")
            return
        
        # 执行下载...
```

### 2. 添加配置文件

创建 `config/data_requirements.json`:

```json
{
  "Stock": {
    "price": true,
    "financials": true,
    "dividends": true,
    "outstanding_shares": true,
    "per_pbr": true,
    "institutional_holdings": true,
    "margin_trading": true
  },
  "ETF": {
    "price": true,
    "financials": false,
    "dividends": true,
    "outstanding_shares": false,
    "per_pbr": false,
    "institutional_holdings": false,
    "margin_trading": false
  }
}
```

### 3. 添加监控和统计

- 记录每次下载的证券类型分布
- 统计跳过的下载次数
- 计算节省的 API 调用次数

---

## 📞 相关文档

- [PROJECT_GUIDE.md](PROJECT_GUIDE.md): 项目整体指南
- [QUICK_START.md](QUICK_START.md): 快速开始指南
- [DATABASE_SCHEMA_AUDIT.md](DATABASE_SCHEMA_AUDIT.md): 数据库架构文档

---

## ✅ 完成状态

- [x] SecurityType 枚举定义（7种类型）
- [x] StockClassifier 核心实现
- [x] 分类规则实现（ETF/权证/特别股/KY股）
- [x] 数据需求判断逻辑
- [x] ClassifiedDownloader 分析工具
- [x] 分类报告生成
- [x] 文档编写
- [ ] 集成到 download_coordinator （待实现）
- [ ] 添加单元测试
- [ ] 添加配置文件支持

---

**版本**: v1.0  
**作者**: Stock Analysis System  
**更新日期**: 2026-02-24
