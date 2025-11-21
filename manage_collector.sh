#!/bin/bash

# 数据采集器管理脚本
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 激活conda环境
source ~/software/miniconda3/bin/activate datagem

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

show_help() {
    cat << EOF
========================================
数据采集器管理工具
========================================

用法: $0 <命令>

命令:
  start       启动数据采集器
  stop        停止数据采集器
  restart     重启数据采集器
  status      查看运行状态
  stats       查看数据库统计
  logs        查看实时日志
  test        测试单次采集
  
示例:
  $0 start        # 启动采集
  $0 status       # 查看状态
  $0 logs         # 查看日志

========================================
EOF
}

check_status() {
    if pgrep -f "streaming_collector_sqlite.py --continuous" > /dev/null; then
        return 0  # 运行中
    else
        return 1  # 未运行
    fi
}

start_collector() {
    if check_status; then
        echo -e "${YELLOW}⚠ 采集器已在运行中${NC}"
        echo "PID: $(pgrep -f streaming_collector_sqlite.py)"
        return
    fi
    
    echo -e "${GREEN}🚀 启动数据采集器...${NC}"
    nohup python streaming_collector_sqlite.py --continuous --interval 600 > collector_output.log 2>&1 &
    PID=$!
    sleep 2
    
    if check_status; then
        echo -e "${GREEN}✓ 采集器已启动${NC}"
        echo "PID: $PID"
        echo "数据库: weather_stream.db"
        echo "日志: streaming_collector.log"
        echo ""
        echo "查看实时日志: $0 logs"
    else
        echo -e "${RED}✗ 启动失败${NC}"
        cat collector_output.log
    fi
}

stop_collector() {
    if ! check_status; then
        echo -e "${YELLOW}⚠ 采集器未在运行${NC}"
        return
    fi
    
    echo -e "${YELLOW}🛑 停止数据采集器...${NC}"
    pkill -f "streaming_collector_sqlite.py --continuous"
    sleep 2
    
    if ! check_status; then
        echo -e "${GREEN}✓ 采集器已停止${NC}"
    else
        echo -e "${RED}✗ 停止失败，尝试强制停止...${NC}"
        pkill -9 -f "streaming_collector_sqlite.py"
    fi
}

show_status() {
    echo "========================================"
    echo "数据采集器状态"
    echo "========================================"
    
    if check_status; then
        PID=$(pgrep -f streaming_collector_sqlite.py)
        echo -e "状态: ${GREEN}✓ 运行中${NC}"
        echo "PID: $PID"
        echo "启动时间: $(ps -p $PID -o lstart=)"
        echo ""
        echo "最近日志:"
        tail -5 streaming_collector.log
    else
        echo -e "状态: ${RED}✗ 未运行${NC}"
    fi
    
    echo ""
    echo "========================================"
}

show_stats() {
    echo "========================================"
    echo "数据库统计"
    echo "========================================"
    python streaming_collector_sqlite.py --once --stats 2>/dev/null || true
}

show_logs() {
    echo "========================================"
    echo "实时日志 (按 Ctrl+C 退出)"
    echo "========================================"
    tail -f streaming_collector.log
}

test_collection() {
    echo "========================================"
    echo "测试单次数据采集"
    echo "========================================"
    python streaming_collector_sqlite.py --once --stats
}

# 主逻辑
case "${1:-}" in
    start)
        start_collector
        ;;
    stop)
        stop_collector
        ;;
    restart)
        stop_collector
        sleep 2
        start_collector
        ;;
    status)
        show_status
        ;;
    stats)
        show_stats
        ;;
    logs)
        show_logs
        ;;
    test)
        test_collection
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo -e "${RED}错误: 未知命令 '$1'${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac

