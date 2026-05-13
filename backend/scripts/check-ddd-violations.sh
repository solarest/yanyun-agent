#!/usr/bin/env bash
set -e

# ==========================================
# DDD 架构依赖检查脚本
# 用途: 检查代码是否违反 DDD 分层架构规则
# ==========================================

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

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

log_section() {
    echo -e "\n${BLUE}========== $1 ==========${NC}"
}

# ==========================================
# 检查函数
# ==========================================

check_domain_dependencies() {
    log_section "检查领域层依赖"
    
    local violations=0
    
    # 检查是否导入应用层
    log_info "检查领域层 → 应用层依赖..."
    local app_deps=$(cd "$BACKEND_DIR" && grep -r "from src\.application" src/domain/ 2>/dev/null || true)
    if [ -n "$app_deps" ]; then
        log_error "发现领域层依赖应用层:"
        echo "$app_deps"
        violations=$((violations + 1))
    else
        log_info "✅ 领域层未依赖应用层"
    fi
    
    # 检查是否导入基础设施层
    log_info "检查领域层 → 基础设施层依赖..."
    local infra_deps=$(cd "$BACKEND_DIR" && grep -r "from src\.infrastructure" src/domain/ 2>/dev/null || true)
    if [ -n "$infra_deps" ]; then
        log_error "发现领域层依赖基础设施层:"
        echo "$infra_deps"
        violations=$((violations + 1))
    else
        log_info "✅ 领域层未依赖基础设施层"
    fi
    
    # 检查是否导入表现层
    log_info "检查领域层 → 表现层依赖..."
    local pres_deps=$(cd "$BACKEND_DIR" && grep -r "from src\.presentation" src/domain/ 2>/dev/null || true)
    if [ -n "$pres_deps" ]; then
        log_error "发现领域层依赖表现层:"
        echo "$pres_deps"
        violations=$((violations + 1))
    else
        log_info "✅ 领域层未依赖表现层"
    fi
    
    return $violations
}

check_application_dependencies() {
    log_section "检查应用层依赖"
    
    log_info "检查应用层 → 基础设施层依赖..."
    local infra_deps=$(cd "$BACKEND_DIR" && grep -r "from src\.infrastructure" src/application/ 2>/dev/null || true)
    if [ -n "$infra_deps" ]; then
        log_warn "发现应用层依赖基础设施层（可能存在架构违规）:"
        echo "$infra_deps"
        echo ""
        log_warn "提示: 应用层应该依赖领域层接口，而不是基础设施层实现"
        return 1
    else
        log_info "✅ 应用层未依赖基础设施层"
        return 0
    fi
}

check_infrastructure_dependencies() {
    log_section "检查基础设施层依赖"
    
    log_info "检查基础设施层 → 应用层依赖..."
    local app_deps=$(cd "$BACKEND_DIR" && grep -r "from src\.application" src/infrastructure/ 2>/dev/null || true)
    if [ -n "$app_deps" ]; then
        log_warn "发现基础设施层依赖应用层（可能存在架构违规）:"
        echo "$app_deps"
        echo ""
        log_warn "提示: 基础设施层应该依赖领域层，而不是应用层"
        return 1
    else
        log_info "✅ 基础设施层未依赖应用层"
        return 0
    fi
}

# ==========================================
# 主流程
# ==========================================

main() {
    log_info "DDD 架构依赖检查开始"
    log_info "项目路径: $PROJECT_ROOT"
    
    local total_violations=0
    
    # 执行各项检查
    check_domain_dependencies || total_violations=$((total_violations + $?))
    check_application_dependencies || total_violations=$((total_violations + 1))
    check_infrastructure_dependencies || total_violations=$((total_violations + 1))
    
    # 输出总结
    log_section "检查总结"
    if [ $total_violations -eq 0 ]; then
        log_info "✅ 所有依赖检查通过！架构合规。"
        exit 0
    else
        log_error "❌ 发现 $total_violations 个架构违规"
        log_error ""
        log_error "请参考 .qoder/rules/ddd-governance.md 了解修复方案"
        exit 1
    fi
}

# 执行主流程
main
