# Python + TypeScript DDD 架构脚手架

一个基于 DDD(领域驱动设计)架构的全栈项目脚手架,包含 Python 后端和 TypeScript/React 前端。

## 项目结构

```
.
├── backend/                    # Python DDD 后端
│   ├── src/
│   │   ├── domain/            # 领域层 - 核心业务规则和抽象
│   │   ├── application/       # 应用层 - 用例编排
│   │   ├── infrastructure/    # 基础设施层 - 技术实现
│   │   └── presentation/      # 表现层 - HTTP 接口
│   ├── tests/
│   ├── requirements.txt
│   └── pyproject.toml
└── frontend/                   # TypeScript React 前端
    ├── src/
    │   ├── domain/            # 领域定义(类型和接口)
    │   ├── application/       # 应用服务(Hooks)
    │   ├── infrastructure/    # API 客户端实现
    │   └── presentation/      # React 组件
    ├── package.json
    └── vite.config.ts
```

## 技术栈

### 后端
- **FastAPI** - 现代 Python Web 框架
- **Pydantic** - 数据验证和序列化
- **SQLAlchemy** - ORM (配置为 SQLite)
- **DDD 架构** - 领域驱动设计

### 前端
- **React 18** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **Axios** - HTTP 客户端

## 快速开始

### 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn src.presentation.app:app --reload --host 0.0.0.0 --port 8000
```

后端运行在: `http://localhost:8000`
API 文档: `http://localhost:8000/docs`
健康检查: `http://localhost:8000/health`

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在: `http://localhost:3000`

> 前端通过 Vite 代理将 `/api` 请求转发到后端 `http://localhost:8000`

## DDD 架构说明

### 后端分层

1. **领域层 (Domain)**
   - 定义 Entity 基类和 Repository 接口
   - 纯 Python,无框架依赖
   - 包含核心业务规则

2. **应用层 (Application)**
   - 实现 Use Cases(用例)
   - 定义 DTOs(数据传输对象)
   - 编排业务流程

3. **基础设施层 (Infrastructure)**
   - 实现 Repository 接口
   - 数据库配置和 ORM 模型
   - 外部服务集成

4. **表现层 (Presentation)**
   - FastAPI 路由定义
   - 依赖注入配置
   - HTTP 请求/响应处理

### 依赖关系

```
Presentation → Application → Domain ← Infrastructure
```

- 应用层依赖领域层(接口)
- 基础设施层实现领域层接口
- 表现层通过依赖注入使用应用层

## 示例接口

### POST /api/ping

测试接口,演示完整的请求流程:

**请求:**
```json
{
  "message": "ping"
}
```

**响应:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T12:00:00",
  "message": "ping - entity count: 0",
  "server": "ddd-python-backend"
}
```

## 开发指南

### 添加新的业务模块

1. **领域层**: 在 `domain/` 中定义 Entity 和 Repository 接口
2. **应用层**: 在 `application/` 中创建 Use Case 和 DTO
3. **基础设施层**: 在 `infrastructure/` 中实现 Repository
4. **表现层**: 在 `presentation/routes/` 中添加路由

### 前端添加新功能

1. **领域层**: 在 `domain/` 中定义类型和接口
2. **基础设施层**: 在 `infrastructure/api/` 中实现 API 调用
3. **应用层**: 在 `application/services/` 中创建服务 Hook
4. **表现层**: 在 `presentation/` 中创建组件

## 命令

### 后端
```bash
# 运行类型检查
mypy src

# 运行测试
pytest tests/

# 代码格式化
ruff format src/
ruff check src/
```

### 前端
```bash
# 类型检查
npm run type-check

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 许可证

MIT
