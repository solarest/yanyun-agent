# 1. Agent 设计

> 对应 `0_outline.md` 第 1 章

## 1.1 Agent 定义

### 核心配置文件（OpenClaw 模式）

> 详细技术方案：[1.1-agent-design.md](./1.1-agent-design.md)

| 文件 | 职责 | 说明 |
|------|------|------|
| `IDENTITY.md` | 代理身份定义与系统边界约束 | 名称、版本、能力描述、职责范围、权限边界 |
| `SOUL.md` | 响应语气、行为特征及输出格式配置 | 语言风格、性格特征、交互偏好、输出格式 |
| `AGENTS.md` | 代理调度规则与标准作业程序 | 任务处理流程、决策规则、SOP 定义 |
| `BOOTSTRAP.md` | 初始化序列与核心系统提示词 | 启动配置、系统级提示词模板、安全约束 |
| `MEMORY.md` | 长期上下文数据与既定规则的持久化存储 | 初始为空，运行时积累长期记忆与既定规则 |
| `TOOLS.md` | 工具授权注册表及调用参数规范 | 可用工具列表、调用权限、参数约束 |
| `USER.md` | 用户画像数据与交互限制配置 | 目标用户特征、偏好设定、交互规则 |

### 领域实体

```
domain/entities/agent.py       — Agent 实体
domain/entities/agent_state.py — Agent 状态
```

## 1.2 Prompt Builder

### 分层构建策略

```
系统提示词（前缀固定）
  └── 安全约束、格式要求
任务提示词（动态组装）
  └── 根据任务类型选择组件
Schema 定义（输出约束）
  └── Pydantic 定义，与领域层 DTO 对齐
Few-shot 管理（示例库）
  └── 按场景动态选择
```

### 实现位置

```
domain/services/prompt_builder.py  — 领域服务：提示词构建逻辑
```

## 1.3 Agent Loop

### 核心循环

基于 LangGraph StateGraph 实现：

```
llm_call → tool_execute → loop_detect → stuck_detect → complete_check
```

### 实现位置

```
application/use_cases/agent_workflow.py  — 工作流编排
infrastructure/agent/nodes/              — 图节点实现
```

### Context 管理

| 策略 | 说明 |
|------|------|
| 裁剪 | 控制上下文长度，保留关键信息 |
| 压缩 | 历史对话摘要，减少 Token 消耗 |
| 注入 | 动态信息注入（记忆、工具结果） |

## 1.4 Tools

### 工具分类

| 类型 | 说明 | 实现位置 |
|------|------|----------|
| web search | 网络搜索 | `infrastructure/tools/` |
| file | 文件操作 | `infrastructure/tools/` |
| clarify | 澄清提问 | `infrastructure/tools/` |
| plan | 任务规划 | `infrastructure/tools/` |
| mcp | MCP 协议集成 | `infrastructure/tools/` |
| skills | 技能系统 | `infrastructure/tools/` |
| sub-agent | 子 Agent 委派 | `infrastructure/tools/` |

### 安全机制

- 工具执行超时
- 工具沙箱执行
- 工具调用限流

## 1.5 Memory 系统

### 记忆类型

| 类型 | 说明 | 存储 |
|------|------|------|
| 情景记忆 | 什么时间发生了什么 | 向量数据库 |
| 语义记忆 | 通用知识 | 向量数据库 |

### 处理流程

```
交互 → 本地记忆存储 → daily summary → dream integration
```

### 实现位置

```
infrastructure/memory/             — 记忆实现
domain/entities/memory.py          — 记忆实体（待创建）
domain/repositories/memory_repository.py  — 接口（待创建）
```

## 1.6 Multi-Agent 系统

### 协作模式

| 模式 | 说明 |
|------|------|
| Supervisor | 监督者协调 |
| Peer-to-Peer | 对等协作 |
| Pipeline | 流水线式 |

### 通信协议

- 异步消息传递
- 超时重试
- 消息追踪
