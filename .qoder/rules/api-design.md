---
trigger: always_on
---
# API 设计规范

## 类型
始终生效

## 描述
RESTful API 设计原则、规范和最佳实践。

## 规则内容

### RESTful 设计原则

#### URL 设计规范

1. **使用名词而非动词**
```
✅ GET    /api/users          # 获取用户列表
✅ POST   /api/users          # 创建用户
❌ GET    /api/getUsers
❌ POST   /api/createUser
```

2. **使用复数名词**
```
✅ /api/users
✅ /api/posts
❌ /api/user
❌ /api/post
```

3. **使用嵌套资源表示关系**
```
✅ /api/users/123/posts       # 用户的帖子
✅ /api/posts/456/comments    # 帖子的评论
❌ /api/users-posts/123
```

4. **使用连字符提高可读性**
```
✅ /api/user-profiles
✅ /api/blog-posts
❌ /api/user_profiles
❌ /api/blogPosts
```

5. **版本控制**
```
✅ /api/v1/users
✅ /api/v2/users
```

### HTTP 方法规范

| 方法 | 用途 | 幂等性 | 示例 |
|------|------|--------|------|
| GET | 获取资源 | ✅ | `GET /api/users` |
| POST | 创建资源 | ❌ | `POST /api/users` |
| PUT | 全量更新 | ✅ | `PUT /api/users/123` |
| PATCH | 部分更新 | ❌ | `PATCH /api/users/123` |
| DELETE | 删除资源 | ✅ | `DELETE /api/users/123` |

### 状态码规范

#### 成功响应

| 状态码 | 说明 | 使用场景 |
|--------|------|----------|
| 200 OK | 成功 | GET/PUT/PATCH 成功 |
| 201 Created | 已创建 | POST 成功创建资源 |
| 204 No Content | 无内容 | DELETE 成功 |

#### 客户端错误

| 状态码 | 说明 | 使用场景 |
|--------|------|----------|
| 400 Bad Request | 请求错误 | 参数验证失败 |
| 401 Unauthorized | 未认证 | 未登录或 Token 无效 |
| 403 Forbidden | 无权限 | 权限不足 |
| 404 Not Found | 未找到 | 资源不存在 |
| 409 Conflict | 冲突 | 资源已存在 |
| 422 Unprocessable Entity | 验证错误 | 数据验证失败 |

#### 服务器错误

| 状态码 | 说明 | 使用场景 |
|--------|------|----------|
| 500 Internal Server Error | 服务器错误 | 未知错误 |
| 502 Bad Gateway | 网关错误 | 上游服务错误 |
| 503 Service Unavailable | 服务不可用 | 维护或过载 |

### 响应格式规范

#### 成功响应

```python
# 单个资源
{
    "id": "user_123",
    "name": "John Doe",
    "email": "john@example.com",
    "createdAt": "2024-01-01T12:00:00Z"
}

# 资源列表
{
    "data": [
        {"id": "1", "name": "John"},
        {"id": "2", "name": "Jane"}
    ],
    "pagination": {
        "page": 1,
        "pageSize": 20,
        "total": 100,
        "totalPages": 5
    }
}
```

#### 错误响应

```python
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "请求参数验证失败",
        "details": [
            {
                "field": "email",
                "message": "邮箱格式无效"
            },
            {
                "field": "age",
                "message": "年龄必须在 0-150 之间"
            }
        ]
    }
}
```

### FastAPI 实现示例

#### 基础 CRUD 端点

```python
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])

# DTO 定义
class UserCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="用户姓名")
    email: str = Field(..., description="邮箱地址")
    age: int = Field(..., ge=0, le=150, description="年龄")

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    age: int
    created_at: str
    
    class Config:
        from_attributes = True

class ErrorResponse(BaseModel):
    error: dict

# 端点实现
@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建用户",
    description="创建新用户账户",
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        409: {"model": ErrorResponse, "description": "邮箱已存在"}
    }
)
async def create_user(dto: UserCreateDTO):
    """创建新用户"""
    try:
        user = use_case.execute(dto)
        return user
    except DuplicateEmailError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_EMAIL", "message": str(e)}}
        )

@router.get(
    "",
    response_model=List[UserResponse],
    summary="获取用户列表",
    description="分页获取用户列表"
)
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词")
):
    """获取用户列表"""
    return use_case.execute(page=page, page_size=page_size, search=search)

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="获取用户详情",
    responses={404: {"description": "用户不存在"}}
)
async def get_user(user_id: str):
    """获取用户详情"""
    user = use_case.execute(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}}
        )
    return user

@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="更新用户",
    responses={
        404: {"description": "用户不存在"},
        409: {"description": "邮箱已存在"}
    }
)
async def update_user(user_id: str, dto: UserCreateDTO):
    """更新用户信息"""
    pass

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除用户",
    responses={404: {"description": "用户不存在"}}
)
async def delete_user(user_id: str):
    """删除用户"""
    pass
```

### 查询参数规范

```python
# 分页
GET /api/users?page=1&page_size=20

# 排序
GET /api/users?sort=created_at&order=desc

# 过滤
GET /api/users?status=active&role=admin

# 搜索
GET /api/users?search=john

# 字段选择
GET /api/users?fields=id,name,email
```

### 认证和授权

#### JWT 认证

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """获取当前认证用户"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="无效 Token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 验证失败")

@router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user)):
    """获取当前用户资料"""
    pass
```

#### 权限控制

```python
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"

def require_role(required_role: Role):
    """角色权限装饰器"""
    def decorator(func):
        async def wrapper(*args, current_user: dict = Depends(get_current_user), **kwargs):
            if current_user["role"] != required_role:
                raise HTTPException(status_code=403, detail="权限不足")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@router.delete("/users/{user_id}")
@require_role(Role.ADMIN)
async def delete_user(user_id: str):
    """只有管理员可以删除用户"""
    pass
```

### API 限流

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, dto: LoginDTO):
    """登录接口 - 每分钟最多 10 次"""
    pass
```

### 文件上传

```python
from fastapi import UploadFile, File

@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    """上传用户头像"""
    # 验证文件类型
    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="只支持 JPEG 和 PNG 格式")
    
    # 验证文件大小（5MB）
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 5MB")
    
    # 处理上传
    pass
```

### 批量操作

```python
@router.post("/users/bulk")
async def bulk_create_users(users: List[UserCreateDTO]):
    """批量创建用户"""
    if len(users) > 100:
        raise HTTPException(status_code=400, detail="最多支持批量创建 100 个用户")
    
    # 批量处理
    pass
```

### API 版本控制

```python
# v1 路由
api_v1 = APIRouter(prefix="/api/v1")

# v2 路由
api_v2 = APIRouter(prefix="/api/v2")

# 注册到应用
app.include_router(api_v1)
app.include_router(api_v2)
```

### OpenAPI 文档

```python
app = FastAPI(
    title="用户管理 API",
    description="用户管理系统 RESTful API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "开发团队",
        "email": "dev@example.com"
    },
    license_info={
        "name": "MIT",
    }
)
```

### API 设计检查清单

创建 API 端点时检查：
- [ ] URL 使用名词复数形式
- [ ] HTTP 方法使用正确
- [ ] 状态码返回准确
- [ ] 响应格式一致
- [ ] 错误信息清晰
- [ ] 有完整的文档注释
- [ ] 参数验证完善
- [ ] 认证授权正确
- [ ] 有适当的限流
- [ ] 支持分页（列表接口）
- [ ] 返回资源位置（创建接口）

### 最佳实践

#### DO ✅

1. **使用 DTO 分离数据模型**
```python
# 请求 DTO
class UserCreateDTO(BaseModel):
    name: str
    email: str

# 响应 DTO
class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: str
```

2. **统一的错误格式**
```python
class APIError(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None
```

3. **使用依赖注入**
```python
def get_user_service() -> UserService:
    return UserService(repository)

@router.post("/users")
async def create_user(
    dto: UserCreateDTO,
    service: UserService = Depends(get_user_service)
):
    pass
```

#### DON'T ❌

1. **不要在 URL 中暴露内部 ID**
```
❌ /api/users/internal-id-12345
✅ /api/users/123
```

2. **不要返回敏感信息**
```python
# 错误
{
    "id": "1",
    "password_hash": "$2b$12$...",  # 绝不返回
    "token": "secret"  # 绝不返回
}

# 正确
{
    "id": "1",
    "name": "John"
}
```

3. **不要混用响应格式**
```python
# 错误 - 格式不统一
def endpoint1():
    return {"success": True, "data": user}

def endpoint2():
    return user

# 正确 - 统一格式
def endpoint1():
    return user

def endpoint2():
    return user
```
