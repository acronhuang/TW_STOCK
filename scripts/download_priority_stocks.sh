#!/bin/bash
# P2-B 优先下载核心股票脚本
# 执行时间: 次日 API 配额重置后

set -e

cd "$(dirname "$0")/.."

echo "=================================="
echo "🚀 P2-B 优先下载核心股票"
echo "=================================="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 检查环境变量
if [ -z "$FINMIND_API_TOKEN" ]; then
    echo "⚠️  未设定 FINMIND_API_TOKEN，从 .env 文件读取..."
    export FINMIND_API_TOKEN=$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)
fi

if [ -z "$FINMIND_API_TOKEN" ]; then
    echo "❌ 错误: 找不到 FINMIND_API_TOKEN"
    echo "请设定环境变量或在 .env 文件中配置"
    exit 1
fi

echo "✅ API Token 已设定"
echo ""

# 阶段 1: 下载核心 50 支股票
echo "=================================="
echo "📥 阶段 1: 下载核心 50 支股票"
echo "=================================="
echo ""

python3 src/downloaders/outstanding_shares_downloader.py \
    --priority-list \
    --skip-existing \
    --execute \
    2>&1 | tee logs/priority_download_$(date +%Y%m%d_%H%M%S).log

echo ""
echo "✅ 阶段 1 完成"
echo ""

# 阶段 2: 验证核心股票
echo "=================================="
echo "🔍 阶段 2: 验证核心股票"
echo "=================================="
echo ""

python3 scripts/verify_outstanding_shares.py

echo ""

# 阶段 3: 询问是否继续下载剩余股票
echo "=================================="
echo "📥 阶段 3: 下载剩余股票（可选）"
echo "=================================="
echo ""
echo "核心股票已下载完成。"
echo ""
read -p "是否继续下载剩余股票？(y/N): " continue_download

if [[ "$continue_download" =~ ^[Yy]$ ]]; then
    echo ""
    echo "⏳ 开始下载剩余股票..."
    echo ""
    
    python3 src/downloaders/outstanding_shares_downloader.py \
        --all \
        --skip-existing \
        --execute \
        2>&1 | tee logs/remaining_download_$(date +%Y%m%d_%H%M%S).log
    
    echo ""
    echo "✅ 剩余股票下载完成"
else
    echo ""
    echo "⏸️  跳过剩余股票下载"
    echo "（可稍后执行: python3 src/downloaders/outstanding_shares_downloader.py --all --skip-existing --execute）"
fi

echo ""
echo "=================================="
echo "📊 最终统计"
echo "=================================="
echo ""

python3 scripts/verify_outstanding_shares.py

echo ""
echo "=================================="
echo "✅ P2-B 下载任务完成"
echo "=================================="
echo ""
echo "下一步: 计算市值和周转率"
echo "  python3 src/calculators/market_metrics_calculator.py --all --execute"
echo ""
