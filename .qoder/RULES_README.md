# Qoder 规约使用说明

本目录包含项目的架构规范和开发约定，用于指导 AI 助手和开发团队遵循正确的开发实践。

## 规则文件说明

### 1. DDD 架构相关

#### [ddd-architecture.md](ddd-architecture.md) - 基础架构规则
- **触发**: 始终生效
- **内容**: DDD 四层架构定义、依赖规则、目录结构
- **适用**: 所有代码生成和审查场景

#### [ddd-governance.md](ddd-governance.md) - 架构治理实战 ⭐ 新增
- **触发**: 模型决策（架构审查、重构、新增功能时）
- **内容**: 
  - 依赖关系审计规则和检查命令
  - 分层职责判断指南
  - Entity-DTO 转换模式
  - 依赖注入最佳实践
  - 常见架构违规案例
  - 重构安全检查清单
  - 架构评分标准
- **适用**: DDD 架构审查、重构、问题排查

### 2. 代码质量相关

#### [project-conventions.md](project-conventions.md)
- **触发**: 模型决策
- **内容**: 工作原则、代码生成规则、命名规范、测试指导

#### [python-backend.md](python-backend.md)
- **触发**: 模型决策（backend/**/*.py）
- **内容**: Python 后端代码规范

#### [typescript-frontend.md](typescript-frontend.md)
- **触发**: 模型决策（frontend/**/*.{ts,tsx}）
- **内容**: TypeScript 前端代码规范

### 3. 安全与测试相关

#### [security-error-handling.md](security-error-handling.md)
- **触发**: 模型决策（编写 API 层时）
- **内容**: 安全规范、错误处理

#### [spec-testing-requirements.md](spec-testing-requirements.md)
- **触发**: 模型决策（生成测试时）
- **内容**: Spec 测试要求

#### [testing-best-practices.md](testing-best-practices.md)
- **触发**: 模型决策（编写测试时）
- **内容**: 测试最佳实践

## 快速开始

### 1. 添加新功能时

AI 助手会自动参考以下规则：
1. `ddd-architecture.md` - 确定代码放在哪个层
2. `ddd-governance.md` - 检查依赖关系是否正确
3. `project-conventions.md` - 遵循命名和代码风格

### 2. 重构代码时

AI 助手会：
1. 参考 `ddd-governance.md` 中的重构安全检查清单
2. 使用 `check-ddd-violations.sh` 脚本验证
3. 确保不违反依赖规则

### 3. 代码审查时

AI 助手会检查：
1. 导入语句是否符合依赖规则
2. 类是否放在正确的层
3. 是否有跨层依赖
4. 是否使用了接口而非具体实现

## 自动化检查

### 提交前检查

```bash
# 运行 DDD 架构依赖检查
cd backend && bash scripts/check-ddd-violations.sh

# 运行代码质量检查
cd backend && uv run ruff check src/

# 运行测试
cd backend && uv run pytest tests/
```

### 手动检查依赖违规

```bash
# 检查领域层是否依赖其他层
cd backend && grep -r "from src\.\(application\|infrastructure\|presentation\)" src/domain/

# 检查应用层是否依赖基础设施层
cd backend && grep -r "from src\.infrastructure" src/application/

# 检查基础设施层是否依赖应用层
cd backend && grep -r "from src\.application" src/infrastructure/
```

## 架构审计报告

完整的架构分析和修复记录见：
- [backend/DDD_ARCHITECTURE_AUDIT.md](../backend/DDD_ARCHITECTURE_AUDIT.md)

包含：
- 当前架构评分
- 违规清单
- 修复实施记录
- 依赖关系图

## 维护指南

### 何时更新规约

1. **发现新的架构问题** → 更新 `ddd-governance.md`
2. **添加新的开发规范** → 创建新的 `.md` 文件
3. **修改进度工具** → 更新检查脚本
4. **技术栈变化** → 更新相关规则

### 规约版本管理

所有规约文件都应该：
- 有清晰的标题和描述
- 包含创建时间和维护者
- 有具体的示例代码
- 有检查清单和验证方法

## 相关资源

- [LangGraph 工作流文档](../docs/langgraph-workflow.md)
- [设计文档](../design/)
- [项目 README](../README.md)

---

**最后更新**: 2026-05-10  
**维护者**: 项目架构团队
