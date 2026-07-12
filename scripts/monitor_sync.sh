#!/bin/bash
# FinMind 同步監控腳本

echo "========================================================================"
echo "FinMind 同步監控"
echo "========================================================================"
echo ""

# 檢查進程
PROCESS=$(ps aux | grep "[f]inmind_full_sync")
if [ -n "$PROCESS" ]; then
    echo "✓ 同步進程運行中"
    echo "$PROCESS" | awk '{print "  PID:", $2}'
else
    echo "✗ 同步進程未運行"
fi
echo ""

# 查看最新日誌（最後 10 行，過濾進度條）
echo "最新日誌:"
echo "------------------------------------------------------------------------"
tail -20 ~/Stock/tw-stock-analysis/nohup.out 2>/dev/null | grep -v "it/s" | tail -10
echo ""

# 數據統計
echo "數據庫狀況:"
echo "------------------------------------------------------------------------"
mongosh tw_stock_analysis --quiet --eval "
  const sp = db.stock_price.distinct('stock_id').filter(s => s).length;
  const fin = db.financial_reports.distinct('symbol').filter(s => s).length;
  const per = db.taiwan_stock_per.distinct('stock_id').filter(s => s).length;
  const div = db.dividend.distinct('stock_id').filter(s => s).length;
  const total = db.stock_list.distinct('stock_id').filter(s => s).length;
  
  print('  stock_price:      ' + sp.toString().padStart(4) + ' / ' + total + ' (' + (sp/total*100).toFixed(1) + '%)');
  print('  financial:        ' + fin.toString().padStart(4) + ' / ' + total + ' (' + (fin/total*100).toFixed(1) + '%)');
  print('  per:              ' + per.toString().padStart(4) + ' / ' + total + ' (' + (per/total*100).toFixed(1) + '%)');
  print('  dividend:         ' + div.toString().padStart(4) + ' / ' + total + ' (' + (div/total*100).toFixed(1) + '%)');
" 2>/dev/null || echo "  (無法連接 MongoDB)"

echo ""
echo "========================================================================"
echo "提示: 重新執行此腳本以更新狀態"
echo "  bash scripts/monitor_sync.sh"
echo "========================================================================"
