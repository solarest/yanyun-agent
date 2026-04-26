---
trigger: model_decision
description: backend/**/*.py
---
# Python 后端代码规范

## 类型
指定文件生效：backend/**/*.py

## 描述
Python 后端代码必须遵循的编码规范和最佳实践。

## 规则内容

### 代码风格

1. **使用 ruff 进行代码格式化**
   - 行长度限制：100 字符
   - 遵循 PEP 8 规范
   - 使用 4 空格缩进

2. **命名规范**
   - 类名：PascalCase（如 `UserEntity`）
   - 函数/方法：snake_case（如 `create_user`）
   - 常量：UPPER_SNAKE_CASE（如 `MAX_RETRY_COUNT`）
   - 私有成员：前导下划线（如 `_internal_method`）

3. **类型注解（强制）**
   - 所有函数必须有类型注解
   - 使用 mypy 进行类型检查
   - 禁止使用 `Any` 类型

```python
# 正确
def calculate_total(items: list[Item], tax_rate: float) -> float:
    total = sum(item.price for item in items)
    return total * (1 + tax_rate)

# 错误 - 缺少类型注解
def calculate_total(items, tax_rate):
    return sum(item.price for item in items) * (1 + tax_rate)
```

### 导入规范

1. **导入顺序**
   - 标准库
   - 第三方库
   - 本地模块（按层依赖规则）

```python
# 正确
import os
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from src.domain.entities import User
from src.application.use_cases import CreateUserUseCase
```

2. **禁止的导入**
   - 领域层不能导入其他层
   - 应用层只能导入领域层

### 类和函数设计

1. **单一职责原则**
   - 每个类只做一件事
   - 每个函数只做一件事
   - 函数长度不超过 50 行

2. **使用数据类或 Pydantic**

```python
# 正确 - 使用 Pydantic
from pydantic import BaseModel, EmailStr

class UserCreateDTO(BaseModel):
    name: str
    email: EmailStr
    age: int

# 避免 - 使用普通字典
def create_user(data: dict):
    pass
```

3. **属性访问**
   - 使用 `@property` 装饰器
   - 避免直接暴露内部状态

### 错误处理

1. **使用自定义异常**

```python
# domain/entities/exceptions.py
class DomainError(Exception):
    """领域层基础异常类"""
    pass

class UserNotFoundError(DomainError):
    """用户未找到异常"""
    pass
```

2. **异常处理位置**
   - 领域层：抛出异常，不捕获
   - 应用层：可以捕获并转换异常
   - 表现层：统一处理异常，返回 HTTP 响应

```python
# 正确 - 表现层处理异常
from fastapi import HTTPException

@router.post("/users")
def create_user(dto: UserCreateDTO):
    try:
        user = use_case.execute(dto)
        return user
    except UserNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 文档注释

1. **所有公共接口必须有 docstring**
   - 使用 Google 风格或 reStructuredText
   - 说明参数、返回值、异常

```python
def create_user(self, dto: UserCreateDTO) -> User:
    """
    创建新用户
    
    Args:
        dto: 用户创建数据传输对象
        
    Returns:
        创建的用户实体
        
    Raises:
        ValueError: 当邮箱格式无效时
        UserAlreadyExistsError: 当用户已存在时
    """
    pass
```

### 包管理

1. **使用 uv 管理依赖**
   - 所有依赖在 `pyproject.toml` 中声明
   - 使用 `uv sync` 安装依赖
   - 使用 `uv add <package>` 添加新依赖

2. **虚拟环境**
   - 使用 uv 自动创建的 `.venv`
   - 使用 `uv run <command>` 运行命令

```bash
# 正确
uv run pytest tests/
uv run uvicorn src.presentation.app:app --reload

# 避免
source .venv/bin/activate
pytest tests/
```

### 测试规范

1. **测试文件位置**
   - 放在 `backend/tests/` 目录
   - 保持与源码相同的目录结构

2. **测试命名**
   - 格式：`test_<function>_<scenario>_<expected>`

```python
def test_create_user_with_valid_data_returns_user():
    pass

def test_create_user_with_duplicate_email_raises_error():
    pass
```

3. **AAA 模式**
   - Arrange（准备）
   - Act（执行）
   - Assert（断言）

```python
def test_calculate_total_with_tax():
    # Arrange
    items = [Item(price=100), Item(price=200)]
    tax_rate = 0.1
    
    # Act
    total = calculate_total(items, tax_rate)
    
    # Assert
    assert total == 330.0
```

### 代码质量检查

提交前必须通过：

```bash
# 代码格式化
uv run ruff format src/

# 代码检查
uv run ruff check src/

# 类型检查
uv run mypy src/

# 运行测试
uv run pytest tests/
```
