# 台股分析系統 — 工作規則

> **這份檔案每一輪對話都會被讀進 context，所以必須短。**
> 細節寫進 `docs/adr/`，這裡只放「不看會出事」的部分。要加東西前先問：
> 這條規則值得每一輪都付一次 token 嗎？不值得就寫成 ADR。

這是 **production**，不是實驗 repo。跑在 `172.16.9.166`，MongoDB `tw_stock_analysis`，
57 個 cron、26 個 dashboard 頁面、每晚實際產出投資建議。改壞了是真的壞掉。

---

## 一、動手前必看

### 🔴 跑任何腳本前，先 grep LINE 耦合

```bash
grep -rn "line_notif\|LineNotif\|send_line\|notifier" <要跑的腳本>
```

有耦合就加 `--no-line`，或確認不會觸發。
**曾經因為漏了這步，真的發出 5 則通知給使用者。** 這是雙向坑——漏發和誤發都算。

### 🔴 不准殺 production 進程

週跑、cron、dashboard、api server——停任何一個都要先問。
週跑跑滿要 48 小時，看起來像卡住其實是正常的。

### 🔴 驗證必須用 production 的執行參數（ADR-0006）

驗證腳本一律 `import` production 函式，**禁止重新實作邏輯**。
而且不只 import 函式，**執行參數也要一樣**——
「我跑的和它跑的不一樣」已經造成過兩次誤判。

具體：迴歸閘跑的是 `pytest -m "not integration and not slow"`。
直接跑 `pytest` 會多撈進 integration 測試，得到不同結論。

### 🔴 檢查要能失敗，且要有雙向對照組（ADR-0002）

新增或修改任何檢查／驗證，兩條硬性門檻：

1. **可失敗性** —— 舉得出一組真實輸入使它回傳未通過。舉不出來就不算檢查。
2. **無資料 ≠ 通過** —— 查無資料時要回報「無資料」，不得當成通過。

加上一條實務規則：**對照組要雙向**。只測「有問題的那邊」，一個永遠回空的過濾器
也會通過。正反都要，而且對照組必須真的測得出差別。

> 實例：`live_advisor` 的投組名稱對不上，`portfolio_name=live` 給「買 10 賣 0」、
> `main` 給「買 0 賣 7」，**建議完全相反**。而端點回 200、`sell_count: 0`，
> 外觀完全正常。單邊跑再多次都看不出來。

### 🔴 數字用程式算，不要心算

張數、筆數、百分比、涵蓋率——一律寫成程式印出來再引用。
心算錯過不只一次。

### 🔴 刪 DB 表前走完六查

尤其第 1 步的「全 repo 引用掃描」要**真的無差別**：所有副檔名、所有目錄、含註解與字串。
只跟已知呼叫鏈會漏。順序是**先移除死碼，最後才刪表**。

已知**不可刪**的表（都曾差點被誤刪）：

| 表 | 為什麼 |
|---|---|
| `financial_statements` | `hsieh_dividend.py` 的**主路徑**（非 fallback，無處可退）——謝式存股的負債比／速動比／未分配盈餘三道門檻全靠它，刪了會**靜默不加分**。另有 11 檔 KY 股（含 `1626` 艾美特-KY，2025Q3 總資產 79.7 億）只有這張表有 |
| `portfolio_trades` | 已凍結但**不是子集**：1108／2892 兩檔已賣出持倉的唯一紀錄、`commission`/`cost`/`total` 三欄、2026-04 價格快照 |

---

## 二、工作流程

```
需求／設計    grill-with-docs                     既有流程,不換
                  ↓
計畫          writing-plans                       ⚠ 計畫寫進 docs/plans/
                                                  ⚠ 不要建 worktree(這裡是 trunk-based)
                  ↓
實作          test-driven-development
              systematic-debugging                卡住時
                  ↓
驗證          verification-before-completion
              ＋ 雙向對照組(見上)
                  ↓
審查          requesting-code-review
              → code-review-and-quality
              → receiving-code-review
                  ↓
部署          見下節
```

`using-git-worktrees` / `finishing-a-development-branch` / `using-superpowers` /
`brainstorming` 已停用——前兩個假設了這個 repo 沒有的分支流程，後兩個與
`grill-with-docs` 搶同一個位置。若有 skill 想叫它們，直接跳過那步。

---

## 三、部署迴圈

```bash
# 1. 本機改 → commit 到 main → push(這裡是 trunk-based,無 feature branch)
git add -A && git commit && git push origin HEAD

# 2. .166 拉取
ssh mdsadmin@172.16.9.166 'cd /home/mdsadmin/Stock/tw-stock-analysis && git pull'

# 3. 迴歸閘(在 .166,用專案 venv,參數不可改)
/home/mdsadmin/Stock/.venv/bin/python3 -m pytest -m "not integration and not slow" -q

# 4. 重啟受影響的服務(見下)

# 5. 🔴 用真實資料驗一次,確認 production 沒被測試波及
```

**第 5 步不能省。** 測試用的 fixture 可能直接寫 production DB ——
`src/portfolio/lots.py` 的 `replace_lots()` 是 `delete_many({})` **全刪重寫、
沒有投組名稱過濾**，在 production DB 上跑會清掉真實持倉。
任何測試碰到它，一律用獨立測試 DB。

### 重啟服務

| 服務 | 埠 | 重啟注意 |
|---|---|---|
| Streamlit dashboard | 8501 | 改頁面**必須重啟**，重整沒用（子模組已在 `sys.modules`） |
| FastAPI server | 8888 | |

重啟 Streamlit 的三個坑（都踩過）：

1. `pkill -f "streamlit run"` 會**匹配到自己的遠端 shell** → 用 `kill <pid>`
2. 重導向的**日誌目錄要先存在**，否則 shell 在 fork 前就中止 →
   舊的殺了、新的沒起（曾中斷 90 秒）。`logs/` 在 repo 底下不是 `~/Stock/`
3. 啟動參數與 cwd **照抄** `ps -p <pid> -o args=` 和 `readlink /proc/<pid>/cwd`，別憑記憶
4. kill 之後要 poll 到 HTTP 200 才算完成

---

## 四、這個 repo 的地雷

| 地雷 | 症狀 | 正解 |
|---|---|---|
| `date` 欄位有三種表示法 | 查錯型別靜默回 0 筆 | 午夜 datetime／16:00 datetime／字串並存，先確認該表用哪種 |
| 各表的股票代號**欄位名不一致** | 查錯欄位靜默回 0 筆 | `financial_statements` 用 `symbol`，`taiwan_stock_info` 用 `stock_id`。查之前先 `find_one()` 看欄位 |
| `_id` 是**建立**時間 | 用它查「最近更新」永遠是舊資料 | 寫入時間看 `updated_at` |
| ssh heredoc 用 `<<EOF` | `$gt` 被 shell 吃掉 → 靜默回 0 筆 | 一律 `<<'EOF'` |
| 指令接 `\| head` | 遮蔽結束碼，失敗看起來像成功 | 用 `${PIPESTATUS[0]}` |
| 財報三來源都是**累計制** | 直接相減得到錯的單季值 | OpenAPI／MOPS／FinMind 都要先差分 |
| 空查詢偽裝成「沒事可做」 | 回 200、count 0，外觀正常 | 區分「看過了沒有」與「根本沒讀到」 |

---

## 五、需求與 ADR 慣例

- **需求的載體是可執行的檢查**（ADR-0001），門檻變更要留 ADR
- **狀態與告警分離**（ADR-0009）：狀態覆寫，告警只在狀態轉變時記錄
- **測試分兩類**（ADR-0011）：斷言邏輯的進迴歸閘；斷言真實數值（會隨財報變）的不進
- 決策寫 `docs/adr/NNNN-標題.md`，計畫寫 `docs/plans/`
- 詞彙定義在 `CONTEXT.md`，用詞和它衝突要先提出來

---

## 六、回報方式

跑了什麼就說跑了什麼，沒跑就說沒跑。測試失敗要貼實際輸出。
**沒有驗證證據就不要說「完成」「通過」「修好了」。**

這個專案反覆出現的失敗模式是**靜默降級**——
結構上不可能失敗的檢查、無資料被當成通過、未驗證的代理指標推出全域結論。
剩下的每一個數字都還是對的，所以看不出來。看到「全部通過」時，先問它**能不能失敗**。
