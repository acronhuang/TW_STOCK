# FinMind 数据迁移字段映射文档

## 📋 概览

本文档定义了从 TWSE OpenAPI 格式到 FinMind 格式的字段映射规则。

**迁移目标**: 统一所有历史数据到 FinMind 标准格式。

**迁移日期**: 2026-02-24

---

## 🔄 字段映射规则

### 1. 必需字段（Required Fields）

| 字段名 | 旧格式 (TWSE OpenAPI) | 新格式 (FinMind) | 映射规则 |
|--------|----------------------|-----------------|---------|
| `stock_id` | ❌ `null` | ✅ `'2330'` | **从 `symbol` 复制** |
| `symbol` | ✅ `'2330'` | ✅ `'2330'` | 保持不变 |
| `date` | ✅ `ISODate()` | ✅ `ISODate()` | 保持不变 |
| `open` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |
| `high` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |
| `low` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |
| `close` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |
| `volume` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |
| `updated_at` | ❌ `updateTime` | ✅ `ISODate()` | **字段重命名** |

### 2. 扩展字段（Extended Fields）

| 字段名 | 旧格式 | 新格式 | 映射规则 |
|--------|--------|--------|---------|
| `max` | ❌ 无 | ✅ `Decimal128()` | **从 `high` 复制** |
| `min` | ❌ 无 | ✅ `Decimal128()` | **从 `low` 复制** |
| `spread` | ❌ 无 | ✅ `float` | **计算**: `close - open` |
| `turnover` | ❌ 无 | ✅ `int` | 默认值: `0` |
| `Trading_Volume` | ❌ 无 | ✅ `Decimal128()` | **从 `volume` 复制** |
| `Trading_money` | ❌ 无 | ✅ `int` | **计算**: `volume × close` |
| `Trading_turnover` | ❌ 无 | ✅ `int` | 默认值: `0` |
| `adjustment_factor` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |
| `adj_close` | ✅ `Decimal128()` | ✅ `Decimal128()` | 保持不变 |

### 3. 删除字段（Deprecated Fields）

| 字段名 | 旧格式 | 新格式 | 操作 |
|--------|--------|--------|------|
| `source` | ✅ `'twse_openapi'` | ❌ 删除 | **移除该字段** |
| `updateTime` | ✅ `ISODate()` | ❌ 删除 | **重命名为 `updated_at`** |

---

## 📊 数据转换示例

### 旧格式示例 (TWSE OpenAPI)

```javascript
{
  "_id": ObjectId("6991d589aa3f27714c6218fd"),
  "symbol": "2330",
  "date": ISODate("2026-02-15T00:00:00.000Z"),
  "high": Decimal128("650.0"),
  "low": Decimal128("640.0"),
  "open": Decimal128("645.0"),
  "close": Decimal128("648.0"),
  "volume": Decimal128("50000000"),
  "source": "twse_openapi",              // ❌ 待删除
  "updateTime": ISODate("2026-02-15T16:00:00.000Z"),  // ❌ 待重命名
  "adjustment_factor": Decimal128("1.0"),
  "adj_close": Decimal128("648.0"),
  "stock_id": null                        // ❌ 待填充
}
```

### 新格式示例 (FinMind)

```javascript
{
  "_id": ObjectId("6991d589aa3f27714c6218fd"),
  "stock_id": "2330",                     // ✅ 从 symbol 填充
  "symbol": "2330",
  "date": ISODate("2026-02-15T00:00:00.000Z"),
  "open": Decimal128("645.0"),
  "high": Decimal128("650.0"),
  "low": Decimal128("640.0"),
  "close": Decimal128("648.0"),
  "max": Decimal128("650.0"),             // ✅ 新增，从 high 复制
  "min": Decimal128("640.0"),             // ✅ 新增，从 low 复制
  "volume": Decimal128("50000000"),
  "Trading_Volume": Decimal128("50000000"), // ✅ 新增，从 volume 复制
  "Trading_money": 32400000000,           // ✅ 新增，计算 50000000 × 648
  "Trading_turnover": 0,                  // ✅ 新增，默认值
  "turnover": 0,                          // ✅ 新增，默认值
  "spread": 3.0,                          // ✅ 新增，计算 648 - 645
  "updated_at": ISODate("2026-02-15T16:00:00.000Z"), // ✅ 重命名自 updateTime
  "adjustment_factor": Decimal128("1.0"),
  "adj_close": Decimal128("648.0")
  // source 字段已删除
  // updateTime 字段已删除
}
```

---

## 🔧 计算规则详解

### 1. `spread` (涨跌幅)

```javascript
spread = close - open
```

**示例**:
- `close = 648.0`, `open = 645.0`
- `spread = 648.0 - 645.0 = 3.0`

### 2. `Trading_money` (成交金额)

```javascript
Trading_money = volume × close
```

**注意**: 结果转换为 `int` 类型（四舍五入）

**示例**:
- `volume = 50000000`, `close = 648.0`
- `Trading_money = 50000000 × 648 = 32,400,000,000`

### 3. 默认值

| 字段 | 默认值 | 原因 |
|------|--------|------|
| `turnover` | `0` | 旧数据无此信息 |
| `Trading_turnover` | `0` | 旧数据无此信息 |

---

## ✅ 验证规则

### 1. 必需字段检查

所有记录必须包含以下字段（非 `null`）:
- `stock_id`
- `symbol`
- `date`
- `open`, `high`, `low`, `close`, `volume`
- `updated_at`

### 2. 禁止字段检查

以下字段不应存在：
- `source`
- `updateTime`

### 3. 数据一致性检查

- ✅ `stock_id` == `symbol`
- ✅ `max` == `high`
- ✅ `min` == `low`
- ✅ `Trading_Volume` == `volume` (数值相同)
- ✅ `spread` ≈ `close - open` (允许小数点精度差异)

### 4. 数据类型检查

| 字段 | 期望类型 |
|------|---------|
| `stock_id` | `string` |
| `symbol` | `string` |
| `date` | `ISODate` |
| `open`, `high`, `low`, `close` | `Decimal128`, `float`, 或 `int` |
| `volume` | `Decimal128`, `float`, 或 `int` |
| `Trading_money` | `int` |
| `turnover`, `Trading_turnover` | `int` |
| `spread` | `float` |
| `updated_at` | `ISODate` |

---

## 🚀 迁移流程

### 步骤 1: 演练模式

```bash
cd tw-stock-analysis
python scripts/migrate_to_finmind_format.py --dry-run
```

**功能**:
- 分析当前数据状态
- 显示迁移计划
- 显示前 5 条迁移示例
- **不实际修改数据**

### 步骤 2: 执行迁移

```bash
python scripts/migrate_to_finmind_format.py --execute
```

**功能**:
- 批量迁移所有 `stock_id: null` 的记录
- 应用字段映射规则
- 计算新增字段
- 删除旧字段

**执行前确认**:
- 显示待迁移记录数
- 显示涉及股票数
- 要求用户输入 `yes` 确认

### 步骤 3: 验证迁移

```bash
python scripts/verify_finmind_migration.py
```

**验证项目**:
1. ✅ 基础统计（记录数、股票数）
2. ✅ 必需字段检查
3. ✅ 禁止字段检查
4. ✅ `stock_id` 完整性检查
5. ✅ 数据类型检查
6. ✅ 数据抽样检查

---

## ⚠️ 注意事项

### 1. 数据备份

**强烈建议在迁移前备份数据库**:

```bash
# 备份数据库
mongodump --db tw_stock_analysis --out backup_before_migration

# 仅备份 stock_price 集合
mongodump --db tw_stock_analysis --collection stock_price --out backup_stock_price
```

### 2. 迁移时间

- 数据量：~5,000,000 条记录
- 预计时间：5-10 分钟（取决于硬件性能）
- 批处理大小：1000 条/批（可调整）

### 3. 数据完整性

迁移过程中：
- ✅ 不会删除任何原始数据（只修改字段）
- ✅ 所有原始价格数据保持不变
- ✅ 仅添加新字段和重命名字段
- ⚠️ 删除 `source` 字段（不再需要）

### 4. 回滚方案

如果迁移失败，可以从备份恢复：

```bash
# 恢复数据库
mongorestore --db tw_stock_analysis backup_before_migration/tw_stock_analysis

# 仅恢复 stock_price 集合
mongorestore --db tw_stock_analysis --collection stock_price backup_stock_price/tw_stock_analysis/stock_price.bson
```

---

## 📈 迁移前后对比

### 迁移前

```
tw_stock_analysis.stock_price:
├─ 总记录数: 5,124,613
├─ stock_id: null → 5,067,328 条 (98.9%)
│  ├─ 数据源: TWSE OpenAPI
│  └─ 字段: symbol, updateTime, high, low, source
└─ stock_id: '0050' 等 → 57,285 条 (1.1%)
   ├─ 数据源: FinMind
   └─ 字段: stock_id, updated_at, max, min, turnover
```

### 迁移后

```
tw_stock_analysis.stock_price:
└─ 总记录数: 5,124,613
   ├─ 所有记录都有 stock_id ✅
   ├─ 统一使用 updated_at ✅
   ├─ 统一使用 max, min ✅
   ├─ 所有记录都有 FinMind 扩展字段 ✅
   └─ 移除 source, updateTime 字段 ✅
```

---

## 🎯 成功标准

迁移成功的标志：
1. ✅ 所有记录 `stock_id != null`
2. ✅ 总记录数保持不变
3. ✅ 所有必需字段存在
4. ✅ 无禁止字段（`source`, `updateTime`）
5. ✅ 验证脚本通过所有检查

---

## 📞 故障排除

### 问题 1: 迁移超时

**症状**: 迁移执行时间过长

**解决方案**:
```bash
# 增加批处理大小
python scripts/migrate_to_finmind_format.py --execute --batch-size 5000
```

### 问题 2: 内存不足

**症状**: MongoDB 内存溢出

**解决方案**:
```bash
# 减小批处理大小
python scripts/migrate_to_finmind_format.py --execute --batch-size 500
```

### 问题 3: 验证失败

**症状**: 验证脚本报告检查失败

**解决方案**:
1. 查看具体失败的检查项
2. 检查数据库索引是否正常
3. 重新执行迁移

```bash
# 重新迁移
python scripts/migrate_to_finmind_format.py --execute

# 重新验证
python scripts/verify_finmind_migration.py
```

---

## 📚 参考资料

- [FinMind API 文档](https://api.finmindtrade.com/docs)
- [FinMind GitHub](https://github.com/FinMind/FinMind)
- [MongoDB 数据迁移最佳实践](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/)

---

**最后更新**: 2026-02-24  
**维护者**: GitHub Copilot
