#!/bin/bash
# 每小时自动下载流通股数 - 启动脚本

set -e

cd "$(dirname "$0")/.."

echo "=================================="
echo "🚀 每小时自动下载流通股数"
echo "=================================="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
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

# 选择下载模式
echo "=================================="
echo "选择下载模式:"
echo "=================================="
echo "1. 优先列表（核心 50 支股票）- 推荐"
echo "2. 全部股票（3,000+ 支）"
echo ""
read -p "请选择 (1/2): " mode

if [ "$mode" == "1" ]; then
    echo ""
    echo "✅ 开始下载优先列表股票..."
    echo ""
    
    python3 src/downloaders/hourly_outstanding_shares_downloader.py \
        --priority-list \
        --max-hours 6 \
        2>&1 | tee logs/hourly_priority_$(date +%Y%m%d_%H%M%S).log
    
elif [ "$mode" == "2" ]; then
    echo ""
    echo "⚠️  下载全部股票可能需要数小时"
    read -p "确定要继续吗？(y/N): " confirm
    
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo ""
        echo "✅ 开始下载全部股票..."
        echo ""
        
        python3 src/downloaders/hourly_outstanding_shares_downloader.py \
            --all \
            --max-hours 24 \
            2>&1 | tee logs/hourly_all_$(date +%Y%m%d_%H%M%S).log
    else
        echo "已取消"
        exit 0
    fi
else
    echo "无效的选择"
    exit 1
fi

# 验证结果
echo ""
echo "=================================="
echo "📊 验证下载结果"
echo "=================================="
echo ""

python3 scripts/verify_outstanding_shares.py

echo ""
echo "=================================="
echo "✅ 下载任务完成"
echo "=================================="
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
