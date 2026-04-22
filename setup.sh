#!/usr/bin/env bash
set -e

# ==========================================
# DDD 项目环境安装脚本
# 用途: 安装前后端所需的所有依赖
# ==========================================

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# ==========================================
# 检查依赖
# ==========================================

check_prerequisites() {
    log_info "检查系统依赖..."
    
    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装,请先安装 Python 3.9+"
        exit 1
    fi
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    log_info "Python 版本: $PYTHON_VERSION"
    
    # 检查 uv (Python 包管理器,如果不存在则安装)
    if ! command -v uv &> /dev/null; then
        log_warn "uv 未安装,正在安装..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # 添加 uv 到 PATH
        source "$HOME/.local/bin/env" 2>/dev/null || export PATH="$HOME/.local/bin:$PATH"
        log_info "uv 安装完成"
    fi
    log_info "uv 已就绪"
    
    # 检查 Node.js
    if ! command -v node &> /dev/null; then
        log_warn "Node.js 未安装"
        if command -v brew &> /dev/null; then
            log_info "使用 Homebrew 安装 Node.js..."
            brew install node
        else
            log_error "请先安装 Node.js: https://nodejs.org/ 或使用 brew install node"
            exit 1
        fi
    fi
    NODE_VERSION=$(node --version)
    log_info "Node.js 版本: $NODE_VERSION"
    
    # 检查 npm
    if ! command -v npm &> /dev/null; then
        log_error "npm 未安装"
        exit 1
    fi
    log_info "npm 已就绪"
}

# ==========================================
# 安装后端依赖
# ==========================================

setup_backend() {
    log_info "安装后端依赖..."
    cd "$BACKEND_DIR"
    
    # 使用 uv 创建虚拟环境并安装依赖
    log_info "使用 uv 创建虚拟环境并安装依赖..."
    uv sync
    
    log_info "后端依赖安装完成"
    cd "$PROJECT_ROOT"
}

# ==========================================
# 安装前端依赖
# ==========================================

setup_frontend() {
    log_info "安装前端依赖..."
    cd "$FRONTEND_DIR"
    
    if [ -d "node_modules" ]; then
        log_warn "node_modules 已存在,将重新安装"
        rm -rf node_modules package-lock.json
    fi
    
    log_info "使用 npm 安装前端依赖..."
    npm install
    
    log_info "前端依赖安装完成"
    cd "$PROJECT_ROOT"
}

# ==========================================
# 主流程
# ==========================================

main() {
    log_info "=========================================="
    log_info "DDD 项目环境安装"
    log_info "=========================================="
    
    check_prerequisites
    setup_backend
    setup_frontend
    
    log_info "=========================================="
    log_info "环境安装完成!"
    log_info "=========================================="
    log_info ""
    log_info "启动服务:"
    log_info "  ./bootstrap.sh start"
    log_info ""
    log_info "或者分别启动:"
    log_info "  后端: cd backend && uv run uvicorn src.presentation.app:app --reload --port 8000"
    log_info "  前端: cd frontend && npm run dev"
}

main "$@"
