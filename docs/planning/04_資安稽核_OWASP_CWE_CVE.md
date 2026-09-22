# 資安稽核結果表 — OWASP Top 10 (2021) / CWE Top 25 / 第三方 CVE

> 範圍：`src/analysis/web_search.py`、`src/analysis/international_news.py`、`dashboard/pages/rag_page.py` 及其相依。
> 工具：pip-audit 2.10（實跑）、ruff 0.15（實跑）、人工邏輯審查。日期基準：功能當前版本。

## 1. OWASP Top 10 (2021) 對照
| # | 類別 | 適用 | 發現 | 風險 | 建議緩解 |
|---|---|:--:|---|:--:|---|
| A01 | 權限控制失效 | ○ | 頁面本身無授權層（Streamlit 內網假設） | 中 | 部署層加反向代理/SSO；勿公網直曝 |
| A02 | 加密失效 | ○ | Ollama 走 **http** 明文(172.16.9.27) | 中 | 內網可接受；跨網段改 https/隧道 |
| A03 | 注入 | ◎ | 使用者 `q`+`event_type` 直接進 LLM prompt → **提示注入**；RSS 標題內容再進 UI markdown → 潛在 **XSS/內容注入** | 高 | prompt 加分隔與指令防護；`st.markdown` 對外部標題以純文字呈現或跳脫連結 |
| A05 | 安全設定錯誤 | ◎ | 硬編碼 IP/路徑、無設定外部化、fail-open 但無日誌 | 中 | 設定移 env；加最小化錯誤日誌 |
| A06 | 易受攻擊元件 | ◎ | 見 §3 CVE（ipython 傳遞相依） | 中 | 升級/移除受影響元件 |
| A08 | 軟體與資料完整性 | ○ | 依賴非官方 Google News RSS，來源可被污染 | 中 | 來源白名單 + EvidenceGuard 過濾 |
| A09 | 記錄與監控不足 | ◎ | 外部呼叫失敗僅 fail-open，無告警/計數 | 中 | 加結構化日誌與失敗率指標 |
| A10 | SSRF | ◎ | `RAG_OLLAMA_URL` 由 env 決定，若可被外部影響→**SSRF** | 中 | 校驗白名單主機、禁止使用者可控 |
| A04/A07 | 不安全設計/認證 | △ | 無認證流程，屬部署範疇 | 低 | 依部署環境補強 |

◎=需處理 ○=需留意 △=部署層

## 2. CWE Top 25 對照（僅列命中）
| CWE | 名稱 | 位置 | 風險 | 緩解 |
|---|---|---|:--:|---|
| CWE-79 | XSS/內容注入 | `rag_page` 以 markdown 顯示外部 RSS 標題/連結 | 高 | 標題純文字化、連結白名單協定(http/https) |
| CWE-1333 | ReDoS（正則） | `web_search` 多個 `re.findall(...DOTALL)` 對外部文字 | 中 | 限制回應大小、避免巢狀量詞、加長度上限 |
| CWE-918 | SSRF | `international_news.OLLAMA` env→urlopen | 中 | 主機白名單、禁使用者可控 URL |
| CWE-77/94 | 指令/提示注入 | LLM prompt 併入使用者輸入 | 高 | 指令隔離 + 輸出後 EvidenceGuard |
| CWE-20 | 輸入驗證不足 | `q`、`event_type`、`region` 未驗證 | 中 | 白名單 region/event，長度上限 |
| CWE-400 | 資源耗用 | 無快取/退避，可被高頻觸發外呼 | 中 | RateLimiter + TTL 快取（文件2 M2/M3） |
| CWE-798 | 硬編碼敏感設定 | `172.16.9.27`、`/home/mdsadmin/...` | 中 | 全面外部化（文件2 D 節） |
| CWE-117 | 日誌注入/不足 | 幾乎無日誌 | 低 | 結構化日誌並跳脫外部字串 |

## 3. 第三方套件 CVE 比對（pip-audit 實跑結果）
指令：`pip-audit -r <deps> --desc`
| 套件 | 版本 | 漏洞 ID | 修復版本 | 說明 | 對本專案影響 |
|---|---|---|---|---|---|
| ipython | 7.34.0 | PYSEC-2023-17 | 8.10.0 | `set_term_title` 於 Windows 且無 ctypes 時的命令注入（傳遞相依） | 低（非直接使用；Windows 有 ctypes 即不可達）；仍建議升級 |
| requests | ≥2.31 | 無（當前解析未報） | — | 本功能主要 HTTP 客戶端 | 保持 ≥2.32；持續追蹤 |
| urllib3 | ≥2.0 | 無（當前解析未報） | — | international_news 用標準庫 urllib，另 requests 依賴 | 維持 ≥2.2 |

> 說明：pip-audit 依當前可解析環境比對 PyPI/OSV 諮詢；上線前應於**鎖定版本(requirements.lock)** 再跑一次並納入 CI。

## 4. 稽核總結與優先修補
| 優先 | 項目 | 對應 | 工時 |
|:--:|---|---|---|
| P0 | 外部 RSS 標題/連結顯示防 XSS（CWE-79） | rag_page | 0.25 天 |
| P0 | 提示注入隔離 + EvidenceGuard 輸出過濾（CWE-77/94, A03） | international_news + 新模組 M5 | 0.75 天 |
| P1 | SSRF 主機白名單 + 設定外部化（CWE-918/798） | 兩檔 + env | 0.5 天 |
| P1 | RSS 回應大小上限 + ReDoS 加固（CWE-1333/400） | web_search | 0.25 天 |
| P2 | 結構化日誌與失敗率指標（A09） | 全域 | 0.5 天 |
| P2 | 升級 ipython≥8.10 並在 CI 加 pip-audit（A06） | 相依/CI | 0.25 天 |

**結論**：功能邏輯層健壯（fail-open、受限提示、去重、8 測試綠）；**上線前必修 P0 兩項**（XSS 與提示注入/輸出過濾），P1 建議一併完成。無「未緩解的高風險直接 CVE」，ipython 為低影響傳遞相依。
