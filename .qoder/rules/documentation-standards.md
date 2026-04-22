---
trigger: always_on
---
# 文档编写规范

## 类型
始终生效

## 描述
项目文档编写规范，包括代码注释、API 文档、README 和技术文档。

## 规则内容

### 文档层次

```
1. 代码注释         - 解释代码"为什么"这样做
2. Docstring       - 函数/类的公共接口文档
3. API 文档        - 接口使用说明和示例
4. README          - 项目概述和快速开始
5. 技术文档        - 架构设计和决策记录
```

### Python Docstring 规范

#### Google Style（推荐）

```python
def create_user(
    self, 
    name: str, 
    email: str, 
    age: int
) -> User:
    """
    创建新用户并保存到数据库
    
    这是更详细的描述，说明函数的完整行为、
    业务规则和注意事项。
    
    Args:
        name: 用户姓名，1-100个字符
        email: 用户邮箱，必须是有效格式
        age: 用户年龄，0-150之间
        
    Returns:
        创建的用户实体对象
        
    Raises:
        ValueError: 当参数验证失败时
        DuplicateEmailError: 当邮箱已存在时
        
    Example:
        >>> repo = UserRepository()
        >>> user = repo.create_user("John", "john@example.com", 25)
        >>> print(user.email)
        john@example.com
    """
    pass
```

#### 类的 Docstring

```python
class UserService:
    """
    用户服务类
    
    负责用户的生命周期管理，包括创建、查询、
    更新和删除操作。
    
    Attributes:
        repository: 用户数据仓储实例
        validator: 用户数据验证器
        
    Example:
        >>> service = UserService(repository, validator)
        >>> user = service.create_user(...)
    """
    
    def __init__(self, repository: UserRepository, validator: UserValidator):
        """
        初始化用户服务
        
        Args:
            repository: 用户数据仓储
            validator: 数据验证器
        """
        self.repository = repository
        self.validator = validator
```

#### 模块级 Docstring

```python
"""
用户管理模块

提供用户相关的业务逻辑，包括：
- 用户创建和验证
- 用户信息查询和更新
- 用户权限管理

使用示例:
    from src.application.use_cases import UserService
    
    service = UserService(repo)
    user = service.create_user(...)
"""
```

### TypeScript JSDoc 规范

```typescript
/**
 * 创建新用户
 * 
 * 验证用户数据并创建新用户账户，
 * 发送欢迎邮件。
 * 
 * @param dto - 用户创建数据传输对象
 * @param dto.name - 用户姓名，1-100字符
 * @param dto.email - 用户邮箱，必须有效格式
 * @param dto.age - 用户年龄，0-150
 * @returns 创建的用户实体
 * @throws {ValidationError} 当数据验证失败时
 * @throws {DuplicateError} 当邮箱已存在时
 * 
 * @example
 * ```typescript
 * const service = new UserService(repository);
 * const user = await service.createUser({
 *   name: 'John Doe',
 *   email: 'john@example.com',
 *   age: 25
 * });
 * ```
 */
async function createUser(dto: CreateUserDTO): Promise<User> {
  // 实现
}
```

### 接口和类型文档

```typescript
/**
 * 用户实体
 * 
 * 表示系统中的一个用户账户
 */
interface User {
  /** 用户唯一标识 */
  id: string;
  
  /** 用户姓名 */
  name: string;
  
  /** 用户邮箱（必须唯一） */
  email: string;
  
  /** 用户年龄（0-150） */
  age: number;
  
  /** 用户状态 */
  status: UserStatus;
  
  /** 创建时间（ISO 8601 格式） */
  createdAt: string;
}

/**
 * 用户状态枚举
 */
type UserStatus = 
  | 'active'      // 活跃用户
  | 'inactive'    // 未激活
  | 'suspended';  // 已封禁
```

### API 文档规范

#### FastAPI Endpoint 文档

```python
@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新用户",
    description="""
    创建新用户账户并返回用户信息。
    
    - **name**: 用户姓名（1-100字符）
    - **email**: 邮箱地址（必须唯一）
    - **age**: 年龄（0-150）
    
    创建成功后会发送欢迎邮件。
    """,
    responses={
        201: {
            "description": "用户创建成功",
            "content": {
                "application/json": {
                    "example": {
                        "id": "user_123",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "age": 25,
                        "createdAt": "2024-01-01T12:00:00Z"
                    }
                }
            }
        },
        400: {"description": "请求参数验证失败"},
        409: {"description": "邮箱已存在"},
    },
    tags=["用户管理"]
)
async def create_user(dto: UserCreateDTO):
    """创建新用户账户"""
    pass
```

### README 规范

#### 必需章节

```markdown
# 项目名称

简短的项目描述（1-2句话）

## 功能特性

- 特性 1
- 特性 2
- 特性 3

## 技术栈

- 后端: Python, FastAPI
- 前端: TypeScript, React
- 数据库: PostgreSQL

## 快速开始

### 前置要求

- Python 3.9+
- Node.js 16+
- uv（Python 包管理器）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd project

# 安装依赖
./setup.sh

# 启动服务
./bootstrap.sh start
```

### 配置

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

## 项目结构

```
project/
├── backend/      # Python 后端
├── frontend/     # TypeScript 前端
└── docs/         # 文档
```

## 开发指南

### 运行测试

```bash
# 后端
cd backend && uv run pytest

# 前端
cd frontend && npm test
```

### 代码规范

参见 [DISCIPLINE.md](DISCIPLINE.md)

## API 文档

启动服务后访问: http://localhost:8000/docs

## 部署

部署说明...

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交变更
4. 推送到分支
5. 创建 Pull Request

## 许可证

MIT License
```

### 注释最佳实践

#### 何时写注释 ✅

1. **解释业务逻辑**
```python
# 根据用户等级计算折扣
# VIP用户: 20%
# 普通用户: 5%
discount = 0.2 if user.is_vip else 0.05
```

2. **说明复杂算法**
```python
# 使用 Dijkstra 算法计算最短路径
# 时间复杂度: O((V+E) log V)
def shortest_path(graph, start, end):
    pass
```

3. **记录临时方案**
```python
# TODO: 重构为使用缓存服务
# 当前使用内存存储，生产环境应使用 Redis
_cache = {}
```

4. **解释 WHY**
```python
# 必须在这里验证邮箱，因为：
# 1. 领域层不知道 API 层的存在
# 2. 避免保存无效数据到数据库
if not validate_email(email):
    raise ValidationError("Invalid email")
```

#### 何时不写注释 ❌

1. **显而易见的代码**
```python
# 错误 - 多余的注释
# 设置用户名称
user.name = name

# 正确 - 代码自解释
user.set_name(name)
```

2. **注释掉的代码**
```python
# 错误 - 应该删除而不是注释
# def old_method():
#     pass

# 正确 - 直接删除，用 Git 历史找回
```

### TODO/FIXME 规范

```python
# TODO: 简短描述 - 可选的详细说明
# FIXME: 简短描述 - 必须说明问题
# HACK: 临时方案 - 说明为什么需要 hack
# NOTE: 重要说明 - 开发者需要注意的事项

# 示例
# TODO: 添加缓存层提高性能
# FIXME: 并发情况下可能出现竞态条件
# HACK: 绕过验证用于测试，生产环境必须移除
# NOTE: 这个算法的时间复杂度是 O(n²)，数据量大时需要优化
```

### 架构决策记录 (ADR)

```markdown
# ADR-001: 选择 FastAPI 作为 Web 框架

## 状态
已接受

## 背景
需要选择一个现代、高性能的 Python Web 框架。

## 决策
选择 FastAPI，原因：
1. 原生异步支持
2. 自动生成 API 文档
3. 基于 Pydantic 的数据验证
4. 优秀的性能表现

## 后果
- 团队需要学习异步编程
- 需要 Python 3.7+
- 生态相对年轻但发展迅速

## 日期
2024-01-01
```

### 文档检查清单

提交前检查：
- [ ] 公共函数/类有 docstring
- [ ] Docstring 包含参数、返回值、异常说明
- [ ] 复杂逻辑有注释说明
- [ ] API endpoint 有完整文档
- [ ] README 是最新的
- [ ] 变更已记录在 CHANGELOG
- [ ] 没有注释掉的代码
- [ ] TODO/FIXME 有清晰描述

### 文档工具

#### Python
- **Sphinx** - 生成项目文档网站
- **MkDocs** - Markdown 文档生成器
- **pdoc** - 自动生成 API 文档

#### TypeScript
- **TypeDoc** - 从 TypeScript 注释生成文档
- **Storybook** - 组件文档和演示

#### 通用
- **Swagger/OpenAPI** - API 文档标准
- **Mermaid** - 图表和流程图
- **PlantUML** - UML 图表
