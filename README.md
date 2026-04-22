# YanYun Agent - 开源可扩展的 AI Agent 框架

一个基于 LangGraph 构建的开源、可扩展的 AI Agent 框架，采用 DDD（领域驱动设计）架构，包含 Python 后端和 TypeScript/React 前端。

## ✨ 特性

- 🧠 **智能工作流** - 基于 LangGraph 的状态机工作流，支持复杂的 Agent 决策逻辑
- 🔍 **循环检测** - 自动检测并处理 Agent 循环行为，支持三级递进式纠正
- 📦 **上下文压缩** - 智能管理对话上下文，避免 token 超限
- 🛡️ **卡住检测** - 实时监控 Agent 状态，防止任务停滞
- ✅ **完成验证** - 多层验证机制确保任务真正完成
- 🔌 **可扩展架构** - DDD 分层设计，易于添加新工具和能力
- 📊 **实时流式输出** - SSE 事件流，实时展示 Agent 思考过程
- 🎨 **现代化界面** - React + TypeScript 构建的直观用户界面

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    Presentation Layer                   │
│  React UI Components ↔ FastAPI Routes ↔ SSE Streaming   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                    Application Layer                    │
│         Use Cases ↔ Services ↔ DTOs ↔ LangGraph         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                      Domain Layer                       │
│    Entities ↔ Repository Interfaces ↔ Business Rules    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Infrastructure Layer                   │
│  LLM Integration ↔ Tool Registry ↔ Database ↔ Repos     │
└─────────────────────────────────────────────────────────┘
```

### 依赖关系

```
Presentation → Application → Domain ← Infrastructure
```

## 🚀 Agent 工作流

Agent 基于 LangGraph StateGraph 构建，包含以下核心节点：

```
[LLM 调用] → [路由决策] → [工具执行] → [循环检测] → [完成检查]
     ↑           ↓                          ↓
     │    [上下文压缩]              [卡住检测]
     └──────────────────────────────────────┘
```

完整流程图请查看 [LangGraph 工作流文档](docs/langgraph-workflow.md)

### 核心节点

| 节点 | 职责 | 文档 |
|------|------|------|
| **LLM 调用** | 流式调用大语言模型 | [llm_call_node.py](backend/src/infrastructure/agent/nodes/llm_call_node.py) |
| **工具执行** | 执行工具调用链 | [tool_execute_node.py](backend/src/infrastructure/agent/nodes/tool_execute_node.py) |
| **循环检测** | 检测并处理循环行为 | [loop_detect_node.py](backend/src/infrastructure/agent/nodes/loop_detect_node.py) |
| **完成检查** | 验证任务完成状态 | [complete_check_node.py](backend/src/infrastructure/agent/nodes/complete_check_node.py) |
| **上下文压缩** | 管理对话上下文 | [context_compact_node.py](backend/src/infrastructure/agent/nodes/context_compact_node.py) |
| **卡住检测** | 检测任务停滞 | [stuck_detect_node.py](backend/src/infrastructure/agent/nodes/stuck_detect_node.py) |

## 📁 项目结构

```
.
├── backend/                    # Python DDD 后端
│   ├── src/
│   │   ├── domain/            # 领域层 - 核心业务规则和抽象
│   │   │   ├── entities/      # Agent 状态、任务、消息等实体
│   │   │   └── repositories/  # Repository 接口定义
│   │   ├── application/       # 应用层 - 用例编排
│   │   │   ├── dtos/          # 数据传输对象
│   │   │   ├── services/      # Agent 工作流服务
│   │   │   └── use_cases/     # 业务用例
│   │   ├── infrastructure/    # 基础设施层 - 技术实现
│   │   │   ├── agent/         # LangGraph Agent 节点
│   │   │   ├── database/      # 数据库配置和模型
│   │   │   ├── llm/           # LLM 模型工厂
│   │   │   └── repositories/  # Repository 实现
│   │   └── presentation/      # 表现层 - HTTP 接口
│   │       ├── routes/        # API 路由
│   │       └── dependencies/  # 依赖注入
│   └── tests/                 # 测试
├── frontend/                   # TypeScript React 前端
│   ├── src/
│   │   ├── domain/            # 领域类型定义
│   │   ├── application/       # 应用服务（Hooks）
│   │   ├── infrastructure/    # API 客户端
│   │   └── presentation/      # React 组件和页面
│   └── package.json
└── docs/                       # 项目文档
```

## 🛠️ 技术栈

### 后端
- **FastAPI** - 现代高性能 Python Web 框架
- **LangGraph** - 基于状态机的 Agent 工作流引擎
- **LangChain** - LLM 应用开发框架
- **Pydantic** - 数据验证和序列化
- **SQLAlchemy** - ORM (支持 SQLite/PostgreSQL)
- **DDD 架构** - 领域驱动设计，清晰的分层架构

### 前端
- **React 18** - 现代化的 UI 框架
- **TypeScript** - 类型安全的 JavaScript
- **Vite** - 快速的构建工具
- **Axios** - HTTP 客户端
- **SSE** - Server-Sent Events 实时流

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+
- uv（Python 包管理器）

### 一键启动

```bash
# 克隆项目
git clone <repository-url>
cd yanyun-agent

# 安装依赖并启动
./setup.sh
./bootstrap.sh start
```

### 手动启动

#### 后端

```bash
cd backend

# 安装依赖（使用 uv）
uv sync

# 启动开发服务器
uv run uvicorn src.presentation.app:app --reload --host 0.0.0.0 --port 8000
```

后端运行在: `http://localhost:8000`
- API 文档: `http://localhost:8000/docs`
- 健康检查: `http://localhost:8000/health`

#### 前端

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

## 📖 API 接口

### 任务管理

#### POST /api/tasks
创建新的 Agent 任务

**请求:**
```json
{
  "message": "帮我分析这个项目的代码结构"
}
```

**响应:**
```json
{
  "taskId": "task_123",
  "status": "running",
  "createdAt": "2024-01-01T12:00:00Z"
}
```

#### GET /api/tasks/:taskId/events
订阅任务事件流（SSE）

### 健康检查

#### POST /api/ping
测试接口，验证系统状态

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
  "server": "yanyun-agent"
}
```

## 🔧 扩展开发

### 添加新的 Agent 工具

1. **定义工具** - 在 `backend/src/infrastructure/agent/tools/` 中创建工具实现
2. **注册工具** - 在工具注册表中注册新工具
3. **更新工作流** - 如需修改工作流，参考 [LangGraph 工作流文档](docs/langgraph-workflow.md)

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

## 📝 开发命令

### 后端
```bash
# 安装依赖
uv sync

# 添加新依赖
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

# 运行测试并生成覆盖率报告
uv run pytest tests/ --cov=src --cov-report=html
```

### 前端
```bash
# 安装依赖
npm install

# 运行开发服务器
npm run dev

# 类型检查
npm run type-check

# 代码检查
npm run lint

# 构建生产版本
npm run build

# 预览生产构建
npm run preview

# 运行测试
npm test
```

## 📚 文档

- [LangGraph 工作流文档](docs/langgraph-workflow.md) - Agent 工作流详细说明
- [API 文档](http://localhost:8000/docs) - FastAPI 自动生成的 Swagger UI
- [项目纪律](DISCIPLINE.md) - 代码规范和最佳实践
- [Qoder 规则](.qoder/rules/) - AI 辅助开发规则集

## 🤝 贡献指南

我们欢迎所有形式的贡献！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 贡献前请阅读

- [项目纪律](DISCIPLINE.md) - 了解代码规范
- [DDD 架构规则](.qoder/rules/ddd-architecture.md) - 理解架构设计
- [测试最佳实践](.qoder/rules/testing-best-practices.md) - 编写高质量测试

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 强大的 Agent 工作流引擎
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://github.com/tiangolo/fastapi) - 现代 Web 框架
- 所有贡献者和使用者
