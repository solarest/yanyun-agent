---
trigger: model_decision
description: 
---
# 项目规则和约定

## 类型
模型决策

## 描述
当生成代码、添加功能、重构或审查代码时应用这些规则。涵盖 DDD 架构、代码质量、测试和文档。

## 规则内容

### 工作原则

1. **先理解再编码**
   - 理解业务需求和领域概念
   - 确认在正确的层添加代码
   - 检查是否有现有类似实现

2. **保持简单**
   - 优先选择简单直接的解决方案
   - 避免过度设计
   - 遵循 KISS 原则

3. **保持一致性**
   - 遵循项目现有代码风格
   - 使用相同的命名模式
   - 参考现有代码的结构

### 代码生成规则

#### 添加新功能时

1. **分析需求**
   - 识别涉及的领域实体
   - 确定业务规则和约束
   - 明确输入输出

2. **实现顺序**
   ```
   领域层 → 应用层 → 基础设施层 → 表现层 → 前端
   ```

3. **Spec 要求**
   - 必须按照 [Spec 测试要求规范](spec-testing-requirements.md) 编写 spec
   - 包含功能测试、单元测试和回归测试说明
   - 确保测试可反复验证和支持子回归

4. **检查清单**
   - [ ] 在领域层定义 Entity 和 Repository 接口
   - [ ] 在应用层创建 Use Case 和 DTO
   - [ ] 在基础设施层实现 Repository
   - [ ] 在表现层添加路由
   - [ ] 添加单元测试
   - [ ] 更新文档
   - [ ] 完成 spec 中的测试计划

#### 修改现有代码时

1. **影响分析**
   - 识别受影响的模块
   - 检查依赖关系
   - 评估向后兼容性

2. **重构原则**
   - 小步重构
   - 保持测试通过
   - 提交前验证

### 代码质量标准

#### 命名规范

**Python:**
- 类名: `PascalCase`
- 函数/方法: `snake_case`
- 常量: `UPPER_SNAKE_CASE`
- 私有成员: `_leading_underscore`

**TypeScript:**
- 类/接口/类型: `PascalCase`
- 函数/变量: `camelCase`
- 常量: `UPPER_SNAKE_CASE`
- 文件名: `PascalCase` (组件) 或 `camelCase` (工具)

#### 函数设计

1. **单一职责**
   - 每个函数只做一件事
   - 函数长度不超过 50 行
   - 参数不超过 4 个（超过则使用对象）

2. **纯函数优先**
   - 优先使用纯函数
   - 避免副作用
   - 明确标注不纯的操作

3. **错误处理**
   - 使用自定义异常
   - 在合适的层级处理错误
   - 提供有意义的错误信息

#### 代码注释

1. **何时注释**
   - 解释"为什么"而不是"做什么"
   - 复杂算法或业务逻辑
   - 临时解决方案或 hack
   - 公开 API 文档

2. **注释风格**

```python
# Python - Google Style
def calculate_tax(income: float, tax_rate: float) -> float:
    """
    计算所得税
    
    Args:
        income: 收入金额
        tax_rate: 税率（0-1之间的小数）
        
    Returns:
        应缴税额
        
    Raises:
        ValueError: 当税率不在有效范围时
    """
    pass
```

```typescript
// TypeScript - JSDoc
/**
 * 计算用户折扣
 * @param user - 用户对象
 * @param purchaseAmount - 购买金额
 * @returns 折扣百分比（0-100）
 * @throws {Error} 当用户状态无效时
 */
function calculateDiscount(user: User, purchaseAmount: number): number {
  // ...
}
```

### 测试指导

#### 测试策略

1. **测试金字塔**
   - 大量单元测试（70%）
   - 适量集成测试（20%）
   - 少量 E2E 测试（10%）

2. **测试命名**
   ```
   test_<function>_<scenario>_<expected>
   ```

3. **AAA 模式**
   ```
   Arrange - 准备测试数据
   Act - 执行被测函数
   Assert - 验证结果
   ```

#### 测试覆盖

**必须测试的内容：**
- 领域层业务逻辑
- 应用层用例
- 基础设施层关键实现
- API 端点
- 前端组件渲染和交互

**可选测试的内容：**
- 简单的 getter/setter
- 框架代码（路由配置等）
- 纯 UI 组件（无逻辑）

### 文档要求

#### 代码文档

1. **必须文档化**
   - 所有公共类和函数
   - 复杂算法
   - 业务规则
   - API 接口

2. **README 更新时机**
   - 添加新功能模块
   - 变更 API
   - 修改安装步骤
   - 新增环境变量

#### API 文档

1. **FastAPI 自动生成**
   - 使用 Pydantic 模型
   - 添加 endpoint 描述
   - 提供示例

```python
@router.post(
    "/users",
    response_model=UserDTO,
    summary="创建新用户",
    description="创建新用户并返回用户信息",
    responses={
        400: {"description": "请求参数错误"},
        409: {"description": "用户已存在"}
    }
)
def create_user(dto: UserCreateDTO):
    """创建新用户"""
    pass
```

### 性能考虑

#### 后端性能

1. **数据库查询**
   - 使用索引
   - 避免 N+1 查询
   - 使用分页
   - 只查询需要的字段

2. **缓存策略**
   - 缓存频繁读取的数据
   - 设置合理的过期时间
   - 注意缓存一致性

#### 前端性能

1. **组件优化**
   - 使用 React.memo
   - 合理使用 useMemo 和 useCallback
   - 避免不必要的重渲染

2. **资源优化**
   - 代码分割
   - 图片压缩
   - 懒加载

### 常见陷阱

#### 避免的反模式

1. **DDD 相关**
   - ❌ 在领域层依赖框架
   - ❌ 在领域层处理 HTTP 请求
   - ❌ 贫血领域模型（只有 getter/setter）
   - ❌ 应用层包含业务逻辑

2. **代码质量**
   - ❌ 过长的函数（>50 行）
   - ❌ 过深的嵌套（>3 层）
   - ❌ 魔法数字和字符串
   - ❌ 重复代码

3. **测试相关**
   - ❌ 测试实现细节
   - ❌ 测试之间相互依赖
   - ❌ 忽略失败的测试
   - ❌ 测试覆盖率造假

### 工具和命令

#### 开发命令

**后端:**
```bash
# 安装依赖
uv sync

# 添加依赖
uv add <package>

# 运行开发服务器
uv run uvicorn src.presentation.app:app --reload

# 代码格式化
uv run ruff format src/

# 代码检查
uv run ruff check src/

# 类型检查
uv run mypy src/

# 运行测试
uv run pytest tests/
```

**前端:**
```bash
# 安装依赖
npm install

# 运行开发服务器
npm run dev

# 类型检查
npm run type-check

# 构建
npm run build

# 测试
npm test
```

### 审查要点

当审查代码时，检查：

1. **架构合规性**
   - 是否遵循 DDD 分层
   - 依赖关系是否正确
   - 职责是否清晰

2. **代码质量**
   - 命名是否清晰
   - 函数是否简洁
   - 是否有重复代码

3. **安全性**
   - 输入是否验证
   - 敏感信息是否保护
   - 是否有注入风险

4. **测试**
   - 是否添加了测试
   - 测试是否充分
   - 测试是否独立

5. **性能**
   - 是否有明显的性能问题
   - 是否使用了合适的算法
   - 是否有不必要的计算

### 持续改进

1. **技术债务**
   - 及时记录 TODO/FIXME
   - 定期回顾和清理
   - 优先处理高风险债务

2. **知识沉淀**
   - 记录设计决策
   - 分享最佳实践
   - 更新文档

3. **规则演进**
   - 根据实践调整规则
   - 收集团队反馈
   - 保持规则实用性
