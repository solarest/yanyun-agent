---
trigger: always_on
---
# DDD 架构规则

## 类型
始终生效

## 描述
本项目采用 DDD（领域驱动设计）架构，所有代码必须遵循分层架构和依赖规则。

## 规则内容

### 分层架构

项目严格分为四层：

1. **领域层 (Domain)** - 核心业务规则和抽象
   - 定义 Entity（实体）
   - 定义 Repository 接口
   - 定义领域服务
   - 包含核心业务逻辑和规则
   - 纯 Python/TypeScript，无框架依赖

2. **应用层 (Application)** - 用例编排
   - 实现 Use Cases（用例）
   - 定义 DTOs（数据传输对象）
   - 编排业务流程
   - 协调领域对象

3. **基础设施层 (Infrastructure)** - 技术实现
   - 实现 Repository 接口
   - 数据库配置和 ORM 模型
   - 外部服务集成
   - 文件存储、消息队列等

4. **表现层 (Presentation)** - 接口层
   - HTTP 路由定义
   - 依赖注入配置
   - 请求/响应处理
   - 中间件

### 依赖规则

```
Presentation → Application → Domain ← Infrastructure
```

**严格约束：**
- 领域层不能依赖任何其他层
- 应用层只能依赖领域层（接口）
- 基础设施层实现领域层接口
- 表现层通过依赖注入使用应用层
- 禁止跨层依赖和循环依赖

### Python 后端实现

```
backend/src/
├── domain/
│   ├── entities/        # 实体定义
│   └── repositories/    # Repository 接口
├── application/
│   ├── dtos/           # 数据传输对象
│   └── use_cases/      # 用例实现
├── infrastructure/
│   ├── database/       # 数据库配置
│   └── repositories/   # Repository 实现
└── presentation/
    ├── routes/         # 路由定义
    └── dependencies/   # 依赖注入
```

### TypeScript 前端实现

```
frontend/src/
├── domain/
│   └── entities/       # 领域类型和接口
├── application/
│   └── services/       # 应用服务（Hooks）
├── infrastructure/
│   └── api/           # API 客户端实现
└── presentation/
    ├── components/    # React 组件
    └── pages/         # 页面组件
```

### 编码示例

#### 领域层 - Entity 定义

```python
# 正确示例
from src.domain.entities.base import BaseEntity

class User(BaseEntity):
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
    
    def validate_email(self) -> bool:
        """领域规则：验证邮箱格式"""
        return '@' in self.email
```

#### 应用层 - Use Case

```python
# 正确示例
from src.domain.repositories import IUserRepository
from src.application.dtos import UserDTO

class CreateUserUseCase:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo
    
    def execute(self, dto: UserDTO) -> User:
        user = User(name=dto.name, email=dto.email)
        if not user.validate_email():
            raise ValueError("Invalid email")
        return self.user_repo.save(user)
```

### 检查清单

添加新功能时：
- [ ] 在领域层定义 Entity 和 Repository 接口
- [ ] 在应用层创建 Use Case 和 DTO
- [ ] 在基础设施层实现 Repository
- [ ] 在表现层添加路由
- [ ] 确保依赖关系正确（不违反依赖倒置）
