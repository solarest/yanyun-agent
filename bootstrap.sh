#!/usr/bin/env bash
set -e

# ==========================================
# DDD 服务管理脚本
# 用途: 启动、重启、停止前后端服务
# ==========================================

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_PID_FILE="$PROJECT_ROOT/.backend.pid"
FRONTEND_PID_FILE="$PROJECT_ROOT/.frontend.pid"
LOG_DIR="$PROJECT_ROOT/logs"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# ==========================================
# 辅助函数
# ==========================================

# 检查进程是否存在
is_process_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            return 0
        else
            # PID 文件存在但进程不存在,清理
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# 获取进程状态
get_process_status() {
    local name=$1
    local pid_file=$2
    
    if is_process_running "$pid_file"; then
        local pid=$(cat "$pid_file")
        echo -e "${GREEN}● 运行中${NC} (PID: $pid)"
    else
        echo -e "${RED}○ 已停止${NC}"
    fi
}

# 确保日志目录存在
ensure_log_dir() {
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
    fi
}

# ==========================================
# 后端管理
# ==========================================

start_backend() {
    if is_process_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        log_warn "后端服务已在运行 (PID: $pid)"
        return 0
    fi
    
    log_info "启动后端服务..."
    cd "$BACKEND_DIR"
    
    # 检查虚拟环境
    if [ ! -d ".venv" ]; then
        log_error "后端虚拟环境不存在,请先运行: ./setup.sh"
        return 1
    fi
    
    # 启动后端
    ensure_log_dir
    uv run uvicorn src.presentation.app:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        > "$LOG_DIR/backend.log" 2>&1 &
    
    local pid=$!
    echo $pid > "$BACKEND_PID_FILE"
    
    # 等待服务启动
    sleep 2
    if ps -p $pid > /dev/null 2>&1; then
        log_info "后端服务已启动 (PID: $pid)"
        log_info "API 文档: http://localhost:8000/docs"
    else
        log_error "后端服务启动失败,查看日志: $LOG_DIR/backend.log"
        return 1
    fi
    
    cd "$PROJECT_ROOT"
}

stop_backend() {
    if is_process_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        log_info "停止后端服务 (PID: $pid)..."
        kill $pid 2>/dev/null || true
        
        # 等待进程结束
        local count=0
        while ps -p $pid > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        # 如果还没结束,强制杀死
        if ps -p $pid > /dev/null 2>&1; then
            log_warn "强制停止后端服务..."
            kill -9 $pid 2>/dev/null || true
        fi
        
        rm -f "$BACKEND_PID_FILE"
        log_info "后端服务已停止"
    else
        log_info "后端服务未运行"
    fi
}

# ==========================================
# 前端管理
# ==========================================

start_frontend() {
    if is_process_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        log_warn "前端服务已在运行 (PID: $pid)"
        return 0
    fi
    
    log_info "启动前端服务..."
    cd "$FRONTEND_DIR"
    
    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        log_error "前端依赖未安装,请先运行: ./setup.sh"
        return 1
    fi
    
    # 启动前端
    ensure_log_dir
    npm run dev \
        > "$LOG_DIR/frontend.log" 2>&1 &
    
    local pid=$!
    echo $pid > "$FRONTEND_PID_FILE"
    
    # 等待服务启动
    sleep 3
    if ps -p $pid > /dev/null 2>&1; then
        log_info "前端服务已启动 (PID: $pid)"
        log_info "访问地址: http://localhost:3000"
    else
        log_error "前端服务启动失败,查看日志: $LOG_DIR/frontend.log"
        return 1
    fi
    
    cd "$PROJECT_ROOT"
}

stop_frontend() {
    if is_process_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        log_info "停止前端服务 (PID: $pid)..."
        
        # 停止 npm 进程及其子进程
        kill $pid 2>/dev/null || true
        # 也停止可能的子进程 (Vite)
        pkill -P $pid 2>/dev/null || true
        
        # 等待进程结束
        local count=0
        while ps -p $pid > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        # 如果还没结束,强制杀死
        if ps -p $pid > /dev/null 2>&1; then
            log_warn "强制停止前端服务..."
            kill -9 $pid 2>/dev/null || true
            pkill -9 -P $pid 2>/dev/null || true
        fi
        
        rm -f "$FRONTEND_PID_FILE"
        log_info "前端服务已停止"
    else
        log_info "前端服务未运行"
    fi
}

# ==========================================
# 服务状态
# ==========================================

status() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}DDD 项目服务状态${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo ""
    echo "后端 (http://localhost:8000):"
    echo "  状态: $(get_process_status "backend" "$BACKEND_PID_FILE")"
    echo ""
    echo "前端 (http://localhost:3000):"
    echo "  状态: $(get_process_status "frontend" "$FRONTEND_PID_FILE")"
    echo ""
}

# ==========================================
# 查看日志
# ==========================================

show_logs() {
    local service=$1
    
    ensure_log_dir
    
    case $service in
        backend)
            if [ -f "$LOG_DIR/backend.log" ]; then
                tail -f "$LOG_DIR/backend.log"
            else
                log_warn "后端日志不存在"
            fi
            ;;
        frontend)
            if [ -f "$LOG_DIR/frontend.log" ]; then
                tail -f "$LOG_DIR/frontend.log"
            else
                log_warn "前端日志不存在"
            fi
            ;;
        *)
            log_info "查看所有日志..."
            if [ -f "$LOG_DIR/backend.log" ]; then
                echo -e "\n${GREEN}=== 后端日志 ===${NC}"
                tail -20 "$LOG_DIR/backend.log"
            fi
            if [ -f "$LOG_DIR/frontend.log" ]; then
                echo -e "\n${GREEN}=== 前端日志 ===${NC}"
                tail -20 "$LOG_DIR/frontend.log"
            fi
            ;;
    esac
}

# ==========================================
# 主流程
# ==========================================

usage() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}DDD 项目服务管理${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo ""
    echo "用法: ./bootstrap.sh <命令> [选项]"
    echo ""
    echo "命令:"
    echo "  start           启动所有服务"
    echo "  stop            停止所有服务"
    echo "  restart         重启所有服务"
    echo "  status          查看服务状态"
    echo "  logs [service]  查看日志 (service: backend|frontend|all)"
    echo ""
    echo "示例:"
    echo "  ./bootstrap.sh start        # 启动所有服务"
    echo "  ./bootstrap.sh stop         # 停止所有服务"
    echo "  ./bootstrap.sh restart      # 重启所有服务"
    echo "  ./bootstrap.sh status       # 查看状态"
    echo "  ./bootstrap.sh logs backend # 查看后端日志"
    echo ""
}

main() {
    local command=${1:-}
    
    case $command in
        start)
            log_info "启动所有服务..."
            start_backend
            start_frontend
            log_info "=========================================="
            log_info "所有服务已启动"
            log_info "=========================================="
            log_info "后端: http://localhost:8000"
            log_info "前端: http://localhost:3000"
            log_info ""
            log_info "停止服务: ./bootstrap.sh stop"
            log_info "查看日志: ./bootstrap.sh logs"
            ;;
        stop)
            log_info "停止所有服务..."
            stop_backend
            stop_frontend
            log_info "所有服务已停止"
            ;;
        restart)
            log_info "重启所有服务..."
            stop_backend
            stop_frontend
            sleep 1
            start_backend
            start_frontend
            log_info "所有服务已重启"
            ;;
        status)
            status
            ;;
        logs)
            show_logs ${2:-all}
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
