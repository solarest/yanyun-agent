---
trigger: model_decision
description: 编写测试用例时生效
---
# 测试最佳实践

## 类型
始终生效

## 描述
项目测试策略、编写规范和最佳实践指南。

## 规则内容

### 测试金字塔

```
        /\
       /  \
      / E2E \     少量 (10%)
     /______\
    /        \
   / Integration\   适量 (20%)
  /______________\
 /                \
/    Unit Tests    \  大量 (70%)
/____________________\
```

### 单元测试规范

#### Python 后端

1. **测试文件组织**
```
backend/tests/
├── unit/
│   ├── domain/
│   │   └── test_user_entity.py
│   ├── application/
│   │   └── test_create_user_use_case.py
│   └── infrastructure/
│       └── test_user_repository.py
└── integration/
    └── test_api_endpoints.py
```

2. **测试命名规范**
```python
# 格式: test_<method>_<scenario>_<expected_result>
def test_create_user_with_valid_data_returns_user():
    pass

def test_create_user_with_duplicate_email_raises_error():
    pass

def test_calculate_total_with_empty_list_returns_zero():
    pass
```

3. **AAA 模式示例**
```python
def test_user_validation_rejects_invalid_email():
    # Arrange - 准备测试数据
    user_data = {
        "name": "John Doe",
        "email": "invalid-email",  # 无效邮箱
        "age": 25
    }
    
    # Act - 执行被测操作
    user = User(**user_data)
    is_valid = user.validate_email()
    
    # Assert - 验证结果
    assert is_valid is False
```

4. **Mock 使用规范**
```python
from unittest.mock import Mock, patch

def test_create_user_calls_repository_save():
    # Arrange
    mock_repo = Mock()
    use_case = CreateUserUseCase(mock_repo)
    dto = UserCreateDTO(name="John", email="john@example.com")
    
    # Act
    use_case.execute(dto)
    
    # Assert
    mock_repo.save.assert_called_once()
```

5. **参数化测试**
```python
import pytest

@pytest.mark.parametrize("email,expected", [
    ("user@example.com", True),
    ("invalid-email", False),
    ("@example.com", False),
    ("user@", False),
    ("", False),
])
def test_validate_email_with_various_inputs(email: str, expected: bool):
    user = User(name="Test", email=email)
    assert user.validate_email() == expected
```

6. **Fixture 使用**
```python
import pytest

@pytest.fixture
def valid_user_data():
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 25
    }

@pytest.fixture
def user_repository():
    return InMemoryUserRepository()

def test_create_user(valid_user_data, user_repository):
    # 直接使用 fixture
    user = User(**valid_user_data)
    saved = user_repository.save(user)
    assert saved.email == valid_user_data["email"]
```

#### TypeScript 前端

1. **测试文件组织**
```
frontend/src/
├── domain/
│   └── entities/
│       ├── User.ts
│       └── User.test.ts
├── application/
│   └── services/
│       ├── useUserService.ts
│       └── useUserService.test.ts
└── presentation/
    └── components/
        ├── UserCard.tsx
        └── UserCard.test.tsx
```

2. **组件测试**
```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { UserCard } from './UserCard';

describe('UserCard', () => {
  const mockUser = {
    id: '1',
    name: 'John Doe',
    email: 'john@example.com'
  };

  it('应该正确显示用户信息', () => {
    render(<UserCard user={mockUser} onClick={() => {}} />);
    
    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.getByText('john@example.com')).toBeInTheDocument();
  });

  it('应该在点击时调用 onClick 回调', () => {
    const handleClick = jest.fn();
    render(<UserCard user={mockUser} onClick={handleClick} />);
    
    fireEvent.click(screen.getByRole('button'));
    
    expect(handleClick).toHaveBeenCalledTimes(1);
    expect(handleClick).toHaveBeenCalledWith('1');
  });
});
```

3. **Hook 测试**
```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { useUserService } from './useUserService';

describe('useUserService', () => {
  it('应该获取用户列表', async () => {
    const { result } = renderHook(() => useUserService());
    
    await result.current.fetchUsers();
    
    await waitFor(() => {
      expect(result.current.users.length).toBeGreaterThan(0);
    });
  });
});
```

### 集成测试

#### Python API 测试

```python
from fastapi.testclient import TestClient
from src.presentation.app import app

client = TestClient(app)

def test_ping_endpoint_returns_ok():
    # Arrange
    payload = {"message": "ping"}
    
    # Act
    response = client.post("/api/ping", json=payload)
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data

def test_create_user_endpoint():
    # Arrange
    user_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 25
    }
    
    # Act
    response = client.post("/api/users", json=user_data)
    
    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["email"] == "john@example.com"
```

### 测试覆盖率

#### 覆盖率目标

- **领域层**: ≥ 95%（核心业务逻辑）
- **应用层**: ≥ 90%（用例编排）
- **基础设施层**: ≥ 80%（技术实现）
- **表现层**: ≥ 70%（HTTP 接口）

#### 运行覆盖率检查

```bash
# Python
uv run pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# 查看 HTML 报告
open htmlcov/index.html
```

### 测试最佳实践

#### DO ✅

1. **测试行为，而非实现**
```python
# 正确 - 测试行为
def test_user_can_validate_email():
    user = User(email="test@example.com")
    assert user.validate_email() is True

# 错误 - 测试实现细节
def test_email_field_is_set():
    user = User(email="test@example.com")
    assert user._email == "test@example.com"
```

2. **每个测试一个断言概念**
```python
# 正确 - 测试单一概念
def test_user_email_must_be_valid_format():
    user = User(email="invalid")
    assert user.validate_email() is False

# 避免 - 测试多个不相关概念
def test_user_creation():
    user = User(name="John", email="john@example.com", age=25)
    assert user.name == "John"
    assert user.validate_email() is True
    assert user.age == 25
    assert user.created_at is not None
```

3. **测试边界条件**
```python
@pytest.mark.parametrize("age,expected", [
    (-1, False),    # 边界：负数
    (0, True),      # 边界：零
    (150, True),    # 边界：最大值
    (151, False),   # 边界：超过最大值
])
def test_user_age_validation(age: int, expected: bool):
    user = User(name="Test", email="test@example.com", age=age)
    assert user.validate_age() == expected
```

4. **测试应该独立**
```python
# 正确 - 每个测试独立
def test_create_first_user():
    repo = InMemoryUserRepository()  # 每个测试创建新实例
    # ...

def test_create_second_user():
    repo = InMemoryUserRepository()  # 不依赖第一个测试
    # ...
```

5. **使用有意义的测试数据**
```python
# 正确 - 有意义的测试数据
def test_adult_user_can_purchase():
    user = User(name="Adult User", email="adult@example.com", age=25)
    assert user.can_purchase() is True

# 错误 - 无意义的测试数据
def test_user_can_purchase():
    user = User(name="asdf", email="asdf@asdf.com", age=99)
    assert user.can_purchase() is True
```

#### DON'T ❌

1. **不要测试框架代码**
```python
# 不需要测试 - 这是框架的功能
def test_pydantic_validates_email():
    # Pydantic 已经测试过这个功能
    pass
```

2. **不要忽略失败的测试**
```python
# 错误 - 跳过失败测试
@pytest.mark.skip(reason="暂时失败")
def test_something():
    pass
```

3. **不要在生产代码中写测试逻辑**
```python
# 错误
class User:
    def __init__(self, is_test: bool = False):  # 测试专用参数
        if is_test:
            self.email = "test@test.com"
```

### TDD 工作流（可选）

```
1. 写一个失败的测试 (Red)
   ↓
2. 写最少的代码让测试通过 (Green)
   ↓
3. 重构代码，保持测试通过 (Refactor)
   ↓
4. 重复
```

### 运行测试命令

```bash
# Python - 运行所有测试
uv run pytest tests/

# Python - 运行特定测试文件
uv run pytest tests/unit/domain/test_user.py

# Python - 运行特定测试函数
uv run pytest tests/ -k "test_create_user"

# Python - 失败后停止
uv run pytest tests/ -x

# Python - 详细输出
uv run pytest tests/ -v

# Python - 显示慢测试
uv run pytest tests/ --durations=10

# 前端 - 运行测试
npm test

# 前端 - 监听模式
npm run test:watch
```

### 测试检查清单

提交前检查：
- [ ] 新功能有对应的测试
- [ ] 所有测试通过
- [ ] 测试覆盖率达标
- [ ] 测试命名清晰
- [ ] 测试独立可重复
- [ ] 边界条件已测试
- [ ] 错误场景已测试
- [ ] 没有跳过失败的测试

### Spec 生成测试要求

当生成 spec 时，必须遵循 [Spec 测试要求规范](spec-testing-requirements.md)，包括：
- 功能测试场景说明（正常流程、异常流程、边界条件）
- 单元测试用例设计
- 回归测试计划
- 反复验证与子回归支持方案
