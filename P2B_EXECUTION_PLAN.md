# P2-B 分批执行计划

**创建时间**: 2026-02-21 22:30  
**目标**: 完成所有股票流通股数下载（克服 API 配额限制）  
**策略**: 优先核心股票 + 分批下载

---

## 当前状态

### 已完成 ✅
- 已下载: **144 支股票** (4.17%)
- 主流股票覆盖: 4/9 (2303, 2412, 1301, 1326)
- 数据精度: Decimal128 ✅

### 缺失 ❌
- 核心股票: 2330 台积电、2317 鸿海、2454 联发科等
- 覆盖率: 仅 4.17%，不足以进行市值分析

---

## 执行时间表

### 📅 第 1 天 (2026-02-22)
**时间**: 次日 21:48+ (API 配额重置后)

**任务**: 优先下载核心 50 支股票

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 方式 1: 使用自动化脚本（推荐）
export FINMIND_API_TOKEN="your_token_here"
./scripts/download_priority_stocks.sh
```

```bash
# 方式 2: 手动执行
export FINMIND_API_TOKEN="your_token_here"

echo "YES" | python3 src/downloaders/outstanding_shares_downloader.py \
    --priority-list \
    --skip-existing \
    --execute \
    2>&1 | tee logs/priority_download_$(date +%Y%m%d_%H%M%S).log

# 验证
python3 scripts/verify_outstanding_shares.py
```

**预期结果**:
- 下载核心 50 支股票
- 覆盖 2330、2317、2454 等核心股票
- 主流股票覆盖率 > 80%

**API 消耗**: ~50 次请求

---

### 📅 第 2 天 (2026-02-23)
**时间**: 次日 21:48+ (API 配额重置后)

**任务**: 继续下载剩余股票（批次 1）

```bash
export FINMIND_API_TOKEN="your_token_here"

echo "YES" | python3 src/downloaders/outstanding_shares_downloader.py \
    --all \
    --skip-existing \
    --limit 500 \
    --execute \
    2>&1 | tee logs/batch1_download_$(date +%Y%m%d_%H%M%S).log
```

**预期结果**:
- 新增 ~300-400 支股票（扣除 ETF/债券）
- 累计覆盖率 ~20-25%

**API 消耗**: ~500 次请求（配额上限）

---

### 📅 第 3 天 (2026-02-24)
**任务**: 继续下载（批次 2）

```bash
echo "YES" | python3 src/downloaders/outstanding_shares_downloader.py \
    --all \
    --skip-existing \
    --limit 500 \
    --execute \
    2>&1 | tee logs/batch2_download_$(date +%Y%m%d_%H%M%S).log
```

**预期结果**:
- 累计覆盖率 ~40-50%

---

### 📅 第 4 天 (2026-02-25)
**任务**: 继续下载（批次 3）

```bash
echo "YES" | python3 src/downloaders/outstanding_shares_downloader.py \
    --all \
    --skip-existing \
    --execute \
    2>&1 | tee logs/batch_final_$(date +%Y%m%d_%H%M%S).log
```

**预期结果**:
- 完成所有股票下载
- 覆盖率 ~60-70% (排除 ETF/债券/认购证)

---

## 核心股票优先列表

已创建: [data/priority_stocks.txt](data/priority_stocks.txt)

**包含 50 支核心股票**:

### 权值股 Top 10
- 2330 台积电
- 2317 鸿海
- 2454 联发科
- 2308 台达电
- 2412 中华电
- 3711 日月光投控
- 2881 富邦金
- 2882 国泰金
- 2891 中信金
- 2886 兆丰金

### 电子股龙头
- 2303 联电
- 2379 瑞昱
- 2357 华硕
- 2382 广达
- 2395 研华
- 3008 大立光
- 2409 友达
- 3045 台湾大
- 4904 远传
- 6505 台塑化

### 传产龙头
- 1301 台塑
- 1303 南亚
- 1326 台化
- 2002 中钢
- 2801 彰银
- 2880 华南金
- 2884 玉山金
- 2885 元大金
- 2887 台新金
- 2890 永丰金

... 等 50 支股票（完整列表见 [data/priority_stocks.txt](data/priority_stocks.txt)）

---

## 改进功能

### 1. 断点续传 ✅
```bash
--skip-existing  # 跳过已下载的股票
```

**原理**: 查询 MongoDB，过滤已有 `outstanding_shares` 的股票

### 2. 优先列表 ✅
```bash
--priority-list  # 使用核心 50 支股票列表
```

**原理**: 从 `data/priority_stocks.txt` 读取股票代码

### 3. 批次限制 ✅
```bash
--limit 500  # 限制每次处理 500 支
```

**原理**: 避免单次消耗过多 API 配额

---

## 验证检查点

### 每日执行后验证

```bash
python3 scripts/verify_outstanding_shares.py
```

**检查项**:
1. ✅ 覆盖率是否增加
2. ✅ 核心股票是否下载成功
3. ✅ 数据类型是否为 Decimal128
4. ✅ 无异常数据（负值、零值）

---

## 完成标准

### 最低标准 (可进行市值计算)
- ✅ 核心 50 支股票全部下载
- ✅ 主流股票覆盖率 > 80%
- ✅ 总覆盖率 > 30%

### 理想标准
- ✅ 总覆盖率 > 60%
- ✅ 市值前 100 全覆盖
- ✅ 数据精度验证通过

---

## 下一步: P2-C 市值/周转率计算

### 前提条件
- ✅ outstanding_shares 覆盖率 > 30%
- ✅ 核心股票全部有数据

### 执行命令

```bash
# 1. 测试单一股票
python3 src/calculators/market_metrics_calculator.py \
    --stock-id 2330 \
    --dry-run

# 2. 批量计算（只计算有 outstanding_shares 的股票）
echo "YES" | python3 src/calculators/market_metrics_calculator.py \
    --all \
    --execute \
    2>&1 | tee logs/market_metrics_$(date +%Y%m%d_%H%M%S).log
```

### 计算公式

```python
# 市值 (单位: 元)
market_cap = close × outstanding_shares × 1000

# 周转率 (%)
turnover_rate = (volume / (outstanding_shares × 1000)) × 100
```

### 储存位置
```javascript
// stock_price collection
{
    stock_id: "2330",
    date: ISODate("2024-01-01"),
    close: Decimal128("580.0"),
    volume: Decimal128("45000000"),
    outstanding_shares: Decimal128("25930380"),  // 千股
    market_cap: Decimal128("15039420400000"),    // 元（15 兆）
    turnover_rate: Decimal128("0.17")            // %
}
```

---

## 监控 & 日志

### 日志位置
```
logs/priority_download_YYYYMMDD_HHMMSS.log  # 核心股票下载
logs/batch1_download_YYYYMMDD_HHMMSS.log    # 批次 1
logs/batch2_download_YYYYMMDD_HHMMSS.log    # 批次 2
logs/batch_final_YYYYMMDD_HHMMSS.log        # 最终批次
```

### 实时监控
```bash
# 监控下载进度
tail -f logs/priority_download_*.log

# 检查 API 错误
grep "402 Client Error" logs/*.log

# 统计成功数
grep "✅.*股本.*億" logs/*.log | wc -l
```

---

## 风险管理

### API 配额耗尽
**症状**: 连续出现 `402 Payment Required`

**处理**:
1. 停止下载（Ctrl+C）
2. 等待 24 小时配额重置
3. 使用 `--skip-existing` 继续

### 网络中断
**处理**:
1. 检查日志最后处理的股票
2. 使用 `--skip-existing` 继续
3. 断点续传自动跳过已下载

### 数据异常
**处理**:
1. 查看 logs 中的错误信息
2. 单独下载失败股票:
   ```bash
   python3 src/downloaders/outstanding_shares_downloader.py \
       --stock-id XXXX \
       --execute
   ```

---

## 预期时间线

```
第 1 天 (2/22): ✅ 核心 50 支股票 → 可开始市值计算
第 2 天 (2/23): 📥 批次 1 (500 支)
第 3 天 (2/24): 📥 批次 2 (500 支)
第 4 天 (2/25): 📥 批次 3 (剩余全部)
第 5 天 (2/26): ✅ P2-B 完成，开始 P2-C 市值计算
```

---

## 备用方案

### 如果 API 配额仍不足

**方案 A**: 升级 FinMind 付费版
- 成本: $19-49 USD/月
- 配额: 10,000+ 次/天
- 可立即完成全部下载

**方案 B**: 使用替代数据源
- 证交所网站（爬虫）
- TEJ 台湾经济新报 (付费)

**方案 C**: 仅核心股票
- 下载核心 50-100 支股票
- 市值分析聚焦主流股票
- 定期补充其余股票

---

## 联系支持

如遇问题，联系:
- FinMind API 支持: https://finmindtrade.com/
- 项目文档: [PROJECT_GUIDE.md](PROJECT_GUIDE.md)

---

**创建时间**: 2026-02-21 22:30:00  
**执行人**: 资深数据库架构师  
**状态**: 待执行（等待 API 配额重置）
