# 貢獻指南

## 開發環境

```bash
cd ~/Stock/tw-stock-analysis
source ../.venv/bin/activate
pip install -e ".[dev]"
```

## 程式碼風格

- Python 3.11+，行寬 120
- 使用 type hints
- 函式必須有 docstring（中文或英文）
- 變數命名：snake_case
- 類別命名：PascalCase

## 提交前檢查

```bash
make test       # 83+ tests 必須全過
make lint       # ruff check 無 error
```

## 新增模組

1. 在 `src/<domain>/` 建立 `.py`
2. 確保 `__init__.py` 存在
3. 寫對應的 `tests/test_<module>.py`
4. 如有 API 端點，更新 `API.md`
5. 更新 `CHANGELOG.md`

## 分支策略

- `main`：穩定版
- `feature/<name>`：新功能
- `fix/<name>`：修 Bug

## 測試標記

```python
@pytest.mark.unit          # 不需 DB
@pytest.mark.integration   # 需 MongoDB
@pytest.mark.slow          # API 呼叫 / 大資料
```
