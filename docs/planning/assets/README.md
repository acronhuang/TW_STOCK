# 架構圖資產（mermaid 原始碼）

`rag_arch_20260924.mmd` — RAG「網路補充/國際新聞分析」現況架構圖（對應 `../05_重新評估_20260924.md` §1）。

## 產出圖片

> 本機（Windows/離線）以 mmdc 渲染時卡在字型資源載入（fontawesome woff2 offline ENOENT），
> 與 E2E 截圖、pip-audit 線上查詢同屬「網路/離線受限」限制。請於完整環境執行：

```bash
# PNG
npx -y @mermaid-js/mermaid-cli -i rag_arch_20260924.mmd -o rag_arch_20260924.png -b white
# 或 SVG
npx -y @mermaid-js/mermaid-cli -i rag_arch_20260924.mmd -o rag_arch_20260924.svg -b white
```

亦可貼到 <https://mermaid.live> 直接匯出。
