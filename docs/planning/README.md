# 📚 docs/planning — 文件索引與導覽

> tw-stock-analysis 專案改善工程的完整文件集：從可行性評估、架構分析，到 Phase 0-2 實作、
> 真實環境驗證與正式部署。全程 TDD、每步獨立可回滾、真實環境（172.16.9.166）驗證零回歸。
> **建議閱讀順序**依下方分類；每份文件皆可獨立查閱。

---

## 🗺️ 快速導覽

| 我想了解… | 看這份 |
|---|---|
| 專案有哪些問題、如何改善 | [`專案分析報告與解決方案`](專案分析報告與解決方案.md) |
| 正式環境長怎樣（拓撲/服務/資料流） | [`正式環境架構規劃圖`](正式環境架構規劃圖.md) ⭐ |
| RAG 國際新聞功能的設計 | [`架構規劃圖`](架構規劃圖.md)、[`01`](01_可行性評估與架構規劃.md)、[`02`](02_架構選型與模組拆解.md) |
| 資安做了什麼 | [`04_資安稽核`](04_資安稽核_OWASP_CWE_CVE.md)、[`Phase0_完成報告`](Phase0_完成報告.md) |
| 每個 Phase 的進度/成果 | Phase 0/1/2 系列（見下） |
| 怎麼施工/驗收 | [`Phase0_施工清單`](Phase0_施工清單.md)、[`03_TDD與E2E報告`](03_TDD與E2E報告.md) |

---

## 📂 文件分類

### A. 專案總覽（先讀）
| 文件 | 內容 | 行數 |
|---|---|---|
| [`專案分析報告與解決方案.md`](專案分析報告與解決方案.md) | 全專案健康度診斷、3 大 P0 問題、Phase 0-3 路線圖 | 116 |

### B. 功能設計（RAG 國際新聞 / 網路補充）
| 文件 | 內容 |
|---|---|
| [`01_可行性評估與架構規劃.md`](01_可行性評估與架構規劃.md) | 可行性評估（技術難易度/風險係數/時程）+ 最沒把握 3 件事 |
| [`02_架構選型與模組拆解.md`](02_架構選型與模組拆解.md) | 3 案架構選型 + 模組 M1-M7 拆解與驗收標準 |
| [`03_TDD與E2E報告.md`](03_TDD與E2E報告.md) | TDD 紅→綠實錄 + Playwright E2E 腳本 |
| [`04_資安稽核_OWASP_CWE_CVE.md`](04_資安稽核_OWASP_CWE_CVE.md) | OWASP Top10 / CWE Top25 / pip-audit CVE 稽核表 |
| [`架構規劃圖.md`](架構規劃圖.md) | RAG 功能 5 圖（分層/資料流/降級/演進/時序） |

### C. Phase 0 — 止血（決策正確性 + 資安 + CI 護欄）
| 文件 | 內容 |
|---|---|
| [`Phase0_施工清單.md`](Phase0_施工清單.md) | 逐檔改動 + 驗收標準（0-C/0-S/0-G） |
| [`Phase0_完成報告.md`](Phase0_完成報告.md) | 成果、風險緩解對照、事故復原紀錄 |

### D. Phase 1 — 設定收斂
| 文件 | 內容 |
|---|---|
| [`Phase1_進度追蹤.md`](Phase1_進度追蹤.md) | `config.py` 設定中心、`sys.path.insert`/`MongoClient` 收斂進度 |

### E. Phase 2 — 資料層收斂
| 文件 | 內容 |
|---|---|
| [`Phase2_進度追蹤.md`](Phase2_進度追蹤.md) | 集合名常數化（61 個 `COLL_*`）、repository + config.get_db() 採用 |

### F. 正式環境架構 ⭐
| 文件 | 內容 |
|---|---|
| [`正式環境架構規劃圖.md`](正式環境架構規劃圖.md) | **實機盤點** 7 圖：實體拓撲+安全邊界 / 服務資料流 / cron 管線 / MoE 推理 / 部署維運 / 團隊分析時序 / 災難復原備份 |

---

## 🚦 工程進度全景

```
Phase 0 ✅ 止血       MoE 守門 · EvidenceGuard · SSRF/XSS/注入 · CI 護欄
Phase 1 ✅ 設定收斂    config.py · 路徑可攜 · sys.path.insert/MongoClient 收斂
Phase 2 🟡 資料層      61 集合常數化 · repository/config.get_db 採用（續批進行中）
         ├─ 修脆弱測試 + 測試 DB 隔離
         ├─ 真實環境驗證（174 passed / 0 failed）
         └─ ✅ 正式部署上線（89705ce）+ 服務重啟 + 三管線健康驗證
Phase 3 ⏸️ 待辦       上帝模組拆分 · MoE 雙路由合併 · 每日備份/replica set · Dashboard SSO
```

## 🔖 關鍵里程碑（git commits）

| Commit | 里程碑 |
|---|---|
| `5276968` | Phase 0-C MoE 決策守門 + 專案分析報告 |
| `3fdd6ca` | Phase 0-S 資安硬化 + EvidenceGuard (TDD) |
| `72da239` | Phase 0-G CI 護欄（pip-audit + 硬編碼 gate） |
| `c1a4523` | Phase 0-S 收尾 rag_page XSS + EvidenceGuard 接線 |
| `8e26ace` | Phase 1 `src/config.py` 設定中心 + 首批遷移 |
| `26d6802` | Phase 1 `sys.path.insert` 清理 + MongoClient 收斂 |
| `e92fa55` | Phase 2 集合名常數化 + repository 收斂 |
| `d16781b` | Phase 2 續批 3 模組採用 COLL_* + config |
| `8301d1b` | 修脆弱 EPS 測試 + 測試 DB 隔離 |
| `89705ce` | **正式部署版**（含 sys.path.insert 回歸修復） |
| `52d4234` | 正式環境架構圖（時序 + 災難復原） |

## 📌 待辦與已知缺口（供 Phase 3 參考）
- **Phase 2 續批**：高頻集合（`stock_price` 339 處…）全樹採用 `COLL_*`；37 處參數驅動 `MongoClient` 收斂到 repository 唯一入口。
- **備份頻率**：目前每週備份 → 建議每日 mongodump 或 replica set。
- **Dashboard 曝險**：8501 綁 `0.0.0.0`，建議加反向代理/SSO。
- **上帝模組**：strategy/senvision/downloaders/analysis 4000+ 行待拆薄殼。
- **pre-existing**：`pyparsing` 版本相容（部署環境已 OK，本機需 upgrade）。

## 🛡️ 維運速查
- **部署**：git bundle → `git pull --ff-only` + `sudo systemctl restart twstock-{api,dashboard}`
- **回滾**：`git reset --hard backup/pre-phase02-*` + restart（見 [`正式環境架構規劃圖` §9](正式環境架構規劃圖.md)）
- **健康檢查**：`curl localhost:8888/openapi.json`、`curl -I localhost:8501/_stcore/health`、`pytest tests/ -q`
