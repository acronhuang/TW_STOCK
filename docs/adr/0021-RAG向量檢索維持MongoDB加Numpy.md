---
status: accepted
date: 2026-10-09
---

# RAG 向量檢索維持 MongoDB 加 Numpy，暫不導入 Milvus

本決定以正式機 `172.16.9.166` 為準；本機工作區只是開發備存，不能作為容量或效能依據。

## 現況量測

2026-10-09 在正式機 revision `daba5ab` 量得：

| 項目 | 結果 |
|---|---:|
| `stockrag.docs` 語料塊 | 11,695 |
| 向量維度 | 1,024 |
| MongoDB 文件資料量 | 170,672,790 bytes（約 163 MiB） |
| 載入並正規化整個語料矩陣 | 2.44 s |
| 已載入矩陣的 cosine 內積 | 0.79 ms/查詢 |
| CLI 端到端檢索 | 7.00 s |

端到端時間含向 `172.16.9.28` 的 Ollama `bge-m3` 請求；不是向量內積的時間。
`dashboard/pages/rag_page.py` 以 `st.cache_resource` 常駐語料，因此 2.44 秒載入只會發生在
dashboard 啟動或快取失效，並非每次使用者查詢都會付出。

目前的查詢也不是單純向量近鄰：`scripts/stockrag_search.py` 將 cosine、繁中文字元 bigram、
RRF 與文件時間衰減組合。Milvus 只會替換 cosine 的其中一段，仍須保留應用層的字面排序、
時間衰減與結果融合。

## 決定

**維持 MongoDB 儲存向量與 Numpy 精確比對，暫不遷移 Milvus。**

此規模下，Milvus 的 ANN 索引不會改善可感知延遲：可替換的工作僅為每查詢 0.79 ms，
而目前秒級時間主要在 embedding 網路呼叫。正式機也沒有 `docker`、`containerd` 或其 systemd
服務；導入 Milvus 會先新增容器執行環境、資料卷、備份、健康檢查、升級與告警等維運面。

現行 ingest 對每個變更檔案先 `delete_many({"path": rel})`，再以 `(path, chunk_idx)` 唯一鍵
批次寫回。Milvus 可以透過穩定主鍵與 upsert 實作相近語意，但遷移仍需重新驗證刪除、更新、
失敗重跑與中繼資料同步；這不是目前 0.79 ms 可以合理交換的複雜度。

## 2026-10-13 增補：新聞與重大訊息語料

2026-10-12 起新增 `stockrag.news_docs`（重大訊息與媒體標題，另一個集合，不與 `stockrag.docs` 混用），
同樣以 MongoDB 儲存向量、Numpy 精確比對。正式機實測：

| 項目 | 結果 |
|---|---:|
| `news_docs` 語料 | 20,361 |
| 向量維度 | 1,024 |
| MongoDB 資料量 | 298,451,996 bytes（約 285 MiB） |
| 載入整個語料矩陣 | 4.58 s |
| 已載入矩陣的 cosine 內積 | 中位數 1.91 ms、P95 2.14 ms |
| 兩個集合合計向量數 | 32,056 |

仍遠低於下列「100,000 塊」與「P95 50 ms」門檻，本決定不變。
`news_docs` 每日約增加數百則，`--days 90` 的視窗讓規模大致穩定；若改為保留全部歷史，才需要依下方門檻重新評估。

## 重新評估門檻

滿足任一條件時，才建立隔離的 Milvus PoC，而不是直接切換正式流量：

1. 語料超過 100,000 塊，或常駐向量與中繼資料使 dashboard 無法在正式機記憶體預算內穩定運行。
2. 排除 embedding 與 LLM 時，暖快取檢索的 P95 超過 50 ms，且已確認是向量排序而非字面 bigram 或 RRF。
3. 需要目前架構無法提供的能力，例如高併發 ANN 查詢、向量資料獨立擴縮，且該需求已量化為 SLO。

PoC 必須以正式語料副本與固定查詢集同時跑精確 Numpy 對照。只有在下列全數通過時才提出遷移 ADR：

- `recall@5` 對精確搜尋基準至少 0.98。
- 向量搜尋 P95 明顯優於基準，且端到端 SLO 也實際受益。
- `(path, chunk_idx)` 的新增、覆寫、刪除、失敗重跑，以及 weekly ingest 後的筆數均通過一致性檢查。
- 保留字元 bigram、RRF 與時間衰減後，既有檢索測試與 dashboard 行為不退化。
- 有已演練的資料備份、還原、健康檢查與版本升級程序。

## Consequences

- 應優先量測並改善 Ollama embedding 延遲；那才是目前互動檢索的主要可改善時間。
- 既有 MongoDB 索引仍只服務 `(path, chunk_idx)` 去重與中繼資料，向量相似度由 Numpy 精確計算。
- 不新增 `pymilvus`、容器服務或雙寫路徑，避免在尚無效益時引入資料漂移與額外故障面。
- 本 ADR 取代 `docs/archive/CURRENT_STATE_2026-07-20.md` 中「正式機沒有 docker」作為當前決策依據；
  該檔是歷史快照，本文件的正式機量測優先。