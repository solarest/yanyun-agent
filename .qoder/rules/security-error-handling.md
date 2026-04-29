---
trigger: model_decision
description: 编写api层时生效
---
# 安全和错误处理规范

## 类型
始终生效

## 描述
项目中必须遵循的安全规范和错误处理最佳实践。

## 规则内容

### 安全规范

#### 敏感信息管理

1. **绝对禁止**
   - 不要提交密码、密钥、Token 等敏感信息到代码仓库
   - 不要在代码中硬编码敏感信息
   - 不要在日志中输出敏感信息

2. **使用环境变量**
   - 所有敏感配置使用环境变量
   - 使用 `.env` 文件存储本地配置
   - 将 `.env` 加入 `.gitignore`

```python
# 正确 - 使用环境变量
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
SECRET_KEY = os.getenv("SECRET_KEY")
API_KEY = os.getenv("API_KEY")

# 错误 - 硬编码
DATABASE_URL = "postgresql://user:password123@localhost/db"
SECRET_KEY = "my-secret-key-12345"
```

```typescript
// 正确 - 使用环境变量
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const API_KEY = import.meta.env.VITE_API_KEY;

// 错误 - 硬编码
const API_BASE_URL = "https://api.example.com";
const API_KEY = "sk-1234567890";
```

3. **环境配置文件**
   - 提供 `.env.example` 作为模板
   - 在文档中说明如何配置

```bash
# .env.example
DATABASE_URL=sqlite:///./app.db
SECRET_KEY=your-secret-key-here
API_KEY=your-api-key-here
DEBUG=false
```

#### 输入验证

1. **后端验证**
   - 所有外部输入必须验证
   - 使用 Pydantic 进行数据验证
   - 验证数据类型、长度、格式、范围

```python
from pydantic import BaseModel, EmailStr, Field, validator

class UserCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(..., ge=0, le=150)
    password: str = Field(..., min_length=8)
    
    @validator('password')
    def password_strength(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v
```

2. **前端验证**
   - 在提交前进行客户端验证
   - 不要依赖客户端验证保证安全

```typescript
import { z } from 'zod';

const userSchema = z.object({
  name: z.string().min(1).max(100),
  email: z.string().email(),
  age: z.number().min(0).max(150),
  password: z.string().min(8),
});

// 验证数据
const result = userSchema.safeParse(formData);
if (!result.success) {
  // 显示验证错误
  showValidationErrors(result.error.errors);
}
```

#### SQL 注入防护

1. **使用 ORM**
   - 始终使用 SQLAlchemy ORM
   - 避免原生 SQL 查询
   - 如果必须使用原生 SQL，使用参数化查询

```python
# 正确 - 使用 ORM
users = db.query(User).filter(User.email == email).all()

# 正确 - 参数化查询
result = db.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": email}
)

# 错误 - 字符串拼接
query = f"SELECT * FROM users WHERE email = '{email}'"  # SQL 注入风险！
```

#### XSS 防护

1. **前端**
   - React 默认转义 JSX 中的内容
   - 使用 `dangerouslySetInnerHTML` 时要格外小心
   - 验证和清理用户输入

```typescript
// 正确 - React 默认转义
<div>{userInput}</div>

// 危险 - 需要清理
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userInput) }} />
```

2. **后端**
   - 在 API 响应中清理数据
   - 设置适当的安全头

```python
from fastapi.middleware.cors import CORSMiddleware

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://trusted-domain.com"],  # 不要使用 "*"
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

#### 认证和授权

1. **密码处理**
   - 永远不要明文存储密码
   - 使用 bcrypt 或 argon2 哈希密码

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 哈希密码
hashed_password = pwd_context.hash(password)

# 验证密码
is_valid = pwd_context.verify(password, hashed_password)
```

2. **Token 管理**
   - 使用 JWT 进行认证
   - 设置合理的过期时间
   - 安全存储 Token（前端使用 httpOnly cookie）

```python
from datetime import datetime, timedelta
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
```

### 错误处理

#### Python 后端

1. **自定义异常层次**

```python
# src/domain/exceptions.py
class DomainError(Exception):
    """领域层基础异常"""
    pass

class EntityNotFoundError(DomainError):
    """实体未找到"""
    pass

class ValidationError(DomainError):
    """验证错误"""
    pass

# src/application/exceptions.py
class ApplicationError(Exception):
    """应用层基础异常"""
    pass

class UseCaseError(ApplicationError):
    """用例执行错误"""
    pass
```

2. **异常处理位置**
   - 领域层：抛出异常，不捕获
   - 应用层：可以捕获并转换
   - 表现层：统一处理，返回 HTTP 响应

```python
# 表现层统一异常处理
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from src.domain.exceptions import DomainError

@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "details": exc.errors()},
    )
```

3. **错误日志**
   - 记录错误详情用于调试
   - 不要记录敏感信息
   - 使用结构化日志

```python
import logging

logger = logging.getLogger(__name__)

def process_payment(user_id: str, amount: float):
    try:
        # 处理支付
        pass
    except PaymentError as e:
        # 记录错误（不包含敏感信息）
        logger.error(
            "Payment failed",
            extra={
                "user_id": user_id,
                "amount": amount,
                "error": str(e)
            }
        )
        raise
```

#### TypeScript 前端

1. **错误边界**
   - 使用 React Error Boundary
   - 显示友好的错误信息

```typescript
import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return <div>Something went wrong. Please try again later.</div>;
    }
    return this.props.children;
  }
}
```

2. **API 错误处理**
   - 统一处理 API 错误
   - 显示用户友好的错误提示

```typescript
import axios, { AxiosError } from 'axios';

export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    
    if (axiosError.response) {
      const status = axiosError.response.status;
      
      switch (status) {
        case 400:
          return '请求参数错误，请检查输入';
        case 401:
          return '请先登录';
        case 403:
          return '没有权限执行此操作';
        case 404:
          return '请求的资源不存在';
        case 500:
          return '服务器错误，请稍后重试';
        default:
          return '请求失败，请稍后重试';
      }
    } else if (axiosError.request) {
      return '网络连接失败，请检查网络';
    }
  }
  
  return '未知错误，请稍后重试';
};
```

3. **Try-Catch 使用**
   - 在适当的位置捕获错误
   - 不要吞掉异常

```typescript
// 正确
async function fetchUsers() {
  try {
    const users = await userServiceApi.getAll();
    return users;
  } catch (error) {
    const message = handleApiError(error);
    showError(message);
    throw error; // 或者返回默认值
  }
}

// 错误 - 吞掉异常
async function fetchUsers() {
  try {
    return await userServiceApi.getAll();
  } catch (error) {
    // 什么都不做
  }
}
```

### 依赖安全

1. **定期更新依赖**
   - 使用 `uv` 锁定 Python 依赖版本
   - 使用 `npm audit` 检查前端依赖漏洞

```bash
# 检查 Python 依赖
uv sync

# 检查前端依赖
npm audit
npm audit fix
```

2. **关注安全公告**
   - 订阅依赖的安全通知
   - 及时更新有漏洞的依赖

### 安全检查清单

每次发布前检查：
- [ ] 没有硬编码的敏感信息
- [ ] 所有输入都经过验证
- [ ] 使用参数化查询或 ORM
- [ ] 密码已加密存储
- [ ] 错误信息不泄露敏感数据
- [ ] 依赖没有已知漏洞
- [ ] 配置了适当的安全头
- [ ] 日志不包含敏感信息
