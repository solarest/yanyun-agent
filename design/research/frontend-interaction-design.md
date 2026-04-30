# Agent-Loop 与前端交互技术方案设计

> 基于 12 个主流 Coding Agent 产品的源码分析,总结最佳实践并输出完整的前后端交互设计方案。

---

## 一、各产品前端交互技术方案分析

### 1.1 技术栈概览

| 产品 | UI 类型 | 前端框架 | 传输协议 | 状态管理 | 特色 |
|------|---------|----------|----------|----------|------|
| **OpenHands** | Web App | React 19 + Vite 7 | Socket.IO (V0) / WebSocket (V1) + REST | Zustand + React Query | 双 WebSocket 架构(主 Agent + Planning Agent) |
| **Cline** | VS Code Extension | React (Webview) | gRPC-over-PostMessage (ProtoBus) | React Context | ProtoBus 架构,双通道状态更新 |
| **OpenClaw** | Web App | Lit + Vite | WebSocket + 自研 JSON-RPC 帧协议 | 组件内状态 | 挑战-响应握手,dropIfSlow 流控 |
| **Codex CLI** | TUI | Ratatui + Crossterm (Rust) | JSON-RPC over mpsc/WebSocket | 内部事件总线 | 四层事件总线,newline-gated 流式渲染 |
| **Gemini CLI** | TUI | React + Ink (Node.js) | 内存 EventEmitter | 25+ React Context | useGeminiStream 核心 Hook,工具调度器 |
| **Goose** | Desktop App | Tauri 2 + React 19 | ACP (JSON-RPC over WebSocket/SSE) | Zustand + React Query | Tauri IPC + WebSocket 双通道 |
| **Claude Code** | TUI | 专有实现 | 流式 API + Hook 系统 | 文件系统 | Hook 系统(4种),Promise 机制 |
| **Aider** | TUI | 纯文本终端 | 无(同步 REPL) | Git | Repo Map,用户驱动 |
| **OpenCode** | TUI | Ink (React TUI) | 内存事件 | Effect 框架 | Doom Loop 检测 |
| **Open Interpreter** | TUI | 纯文本 | 无(同步 REPL) | self.messages | Generator 流式 |
| **SWE-agent** | TUI | 纯文本 | 无(同步 REPL) | history 列表 | Docker 沙箱 |

### 1.2 详细技术分析

#### 1.2.1 OpenHands — 事件驱动的 Web 架构

**传输机制:**
- V0 使用 Socket.IO,支持 Redis 集群,最大 HTTP 缓冲 4MB
- V1 迁移到原生 WebSocket + REST API,支持双连接(主 Agent + Planning Agent)
- 连接时通过 `latest_event_id` 参数补发历史事件

**事件类型:**
- Action 类型:15+ 种(message, read, write, run, browse, delegate, think, finish 等)
- Observation 类型:12+ 种(read, edit, browse, run, agent_state_changed 等)
- Agent 状态:13 种(LOADING, INIT, RUNNING, AWAITING_USER_INPUT, FINISHED, ERROR 等)

**状态同步:**
- Zustand 多 Store 分离(conversation, event, agent, browser, command, metrics, security)
- EventStore 实现 O(1) 去重检查 + 按时间戳排序(支持乱序事件)
- React Query 缓存失效机制,action 事件触发相关查询刷新
- 乐观更新 + localStorage 本地持久化

**文件变更推送:**
- 通过 EventStream 发布-订阅模式,事件广播到前端
- V1 提供专门的文件 REST API(读取沙箱文件)
- PlanningFileEditorObservation 专门处理规划文件编辑

---

#### 1.2.2 Cline — VS Code Webview 的 ProtoBus 架构

**传输机制:**
- 在 VS Code `postMessage` 之上构建类 gRPC 的 RPC 层
- 使用 Protocol Buffers 定义服务契约(StateService, UiService, McpService, FileService, TaskService 等)
- 支持一元请求和流式请求(is_streaming 标志)

**消息结构:**
```typescript
// 请求: Webview -> Extension
{ type: "grpc_request", grpc_request: { service, method, message, request_id, is_streaming } }

// 响应: Extension -> Webview
{ type: "grpc_response", grpc_response: { message, request_id, error, is_streaming, sequence_number } }
```

**双通道状态更新:**
- ExtensionState 流:完整状态(50+ 字段),低频推送
- PartialMessage 流:仅增量消息,高频实时推送(用于流式文本、工具进度)

**Agent Loop 展示:**
- ClineMessage 数组传递完整执行历史
- 每条消息: type(ask/say) + ask/say 子类型 + 文本/图片/文件
- ChatRow 组件根据类型路由到不同渲染组件(DiffEditRow, CommandOutputRow, BrowserSessionRow 等)

---

#### 1.2.3 OpenClaw — 自研帧协议的 WebSocket 架构

**传输机制:**
- 完全基于 WebSocket,不使用 SSE 或 REST 作为主通道
- 自研 JSON-RPC 帧协议(三种帧:req/res/event,通过 type 字段区分)
- TypeBox + AJV 做 Schema 验证

**握手协议(三步挑战-响应):**
```
Client                    Gateway
  |---- TCP/WS Open ------->|
  |<-- connect.challenge --|   (nonce)
  |---- connect(req) ------>|   (签名+nonce+认证)
  |<-- hello-ok(res) ------|   (features/snapshot/policy)
```

**事件系统:**
- 20+ 种事件类型(agent, chat, session.message, session.tool, tick, heartbeat 等)
- Agent 事件: runId + seq + stream + ts + data
- Chat 事件: state 状态机(delta/final/aborted/error)

**流控机制:**
- seq 自增序列号,检测消息丢失
- dropIfSlow: 慢客户端保护(socket.bufferedAmount > MAX 时丢弃非关键事件)
- Scope 权限守卫: 不同事件需要不同权限

---

#### 1.2.4 Codex CLI — Rust TUI 的四层事件总线

**传输机制:**
- 进程内: tokio mpsc 通道(Embedded 模式)
- 远程: WebSocket (tokio-tungstenite, Remote 模式)
- 协议: 轻量级 JSON-RPC(不含 "jsonrpc": "2.0" 字段)

**四层事件总线:**
1. App Server Protocol: ClientRequest/Response, ServerRequest/Response, Notification
2. AppServerClient: 传输适配层(InProcess mpsc / Remote WebSocket)
3. AppEvent: UI 内部消息总线(60+ 种事件类型)
4. TuiEvent: 终端输入事件(Key, Paste, Draw)

**流式输出策略:**
- MarkdownStreamCollector: newline-gated markdown commit
- StreamController: FIFO queue + tick-based drain animation(打字机效果)
- 反压处理: Lossless 事件阻塞 + Best-effort 事件丢弃 + Lagged 标记

---

#### 1.2.5 Gemini CLI — React Ink TUI

**传输机制:**
- 内存 EventEmitter(CoreEvents + AppEvents)
- 事件缓冲机制: UI 未订阅时缓冲最多 10000 条,订阅后回放

**核心流处理:**
- useGeminiStream Hook(2000+ 行): 接收 SSE/Stream,管理工具调用生命周期
- useToolScheduler: 工具状态跟踪(scheduled -> validating -> awaiting_approval -> executing -> success/error)
- 25+ React Context Provider 覆盖所有状态域

**工具展示:**
- ToolGroupMessage: 工具调用组聚合显示
- 紧凑模式: 对 read_file, grep 等工具简化显示
- 确认对话框: ToolConfirmationQueue 组件

---

#### 1.2.6 Goose — Tauri 桌面应用 + ACP 协议

**双通道架构:**
- Tauri IPC: 系统操作(文件、Git、凭证等)
- WebSocket: AI 对话流(ACP 协议, JSON-RPC over WebSocket)

**ACP 协议(Agent Communication Protocol):**
- 客户端请求: Initialize, NewSession, Prompt, Cancel, Authenticate 等
- 服务端通知: SessionNotification(流式消息), RequestPermission(工具确认)
- 支持 WebSocket 和 HTTP+SSE 两种传输

**进程隔离:**
- Tauri 主进程 spawn `goose serve` 进程
- serve 进程独立管理 WebSocket 连接和 Agent 生命周期
- 每个 WebSocket 连接对应一个 ACP 会话

---

## 二、横向对比 — 设计优劣分析

### 2.1 传输协议对比

| 协议 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **SSE** | 浏览器原生,自动重连,简单 | 单向,无法客户端推送 | 简单流式输出 |
| **WebSocket** | 双向,低延迟,灵活 | 需自行实现重连/心跳 | 实时交互应用 |
| **Socket.IO** | 内置重连/房间/广播 | 较重,依赖服务端库 | 需要快速原型 |
| **PostMessage** | 安全隔离(沙箱) | 仅限 Webview,低速 | IDE 扩展 |
| **JSON-RPC over WS** | 结构化,类型安全 | 需自行实现 | 复杂协议交互 |

**最佳实践:**
- OpenClaw 的自研帧协议最严谨(类型安全 + Schema 验证 + 流控)
- OpenHands 的双 WebSocket 架构适合多 Agent 场景
- Cline 的 ProtoBus 展示了如何在受限环境(postMessage)中实现结构化通信

### 2.2 事件设计对比

| 维度 | 最佳实践 | 代表产品 |
|------|----------|----------|
| **事件分类** | 按生命周期/阶段/LLM/工具/检测分类 | SSE 流式设计方案 |
| **去重机制** | O(1) eventId Set 检查 | OpenHands |
| **乱序处理** | 时间戳排序 + lastEventId 补发 | OpenHands, OpenClaw |
| **流控机制** | dropIfSlow + seq 序列号 | OpenClaw |
| **反压处理** | Lossless/Best-effort 分级 | Codex CLI |
| **事件持久化** | SQLite + TTL 清理 | SSE 流式设计方案 |

### 2.3 状态管理对比

| 方案 | 适用场景 | 代表产品 |
|------|----------|----------|
| **Zustand + React Query** | Web App,需要服务端缓存 | OpenHands, Goose |
| **React Context** | Webview/小型应用 | Cline, Gemini CLI |
| **内部事件总线** | TUI/CLI | Codex CLI |
| **文件系统** | 持久化 Agent | Claude Code |

### 2.4 流式渲染对比

| 策略 | 实现 | 代表产品 |
|------|------|----------|
| **Newline-gated commit** | 遇到换行符才提交完整行 | Codex CLI |
| **增量 append** | 直接追加 delta | Cline(PartialMessage) |
| **requestAnimationFrame 节流** | 限制到 60fps | SSE 流式设计方案 |
| **VirtualizedList** | 虚拟滚动长列表 | Gemini CLI, OpenHands |

---

## 三、设计方案

### 3.1 架构总览

基于以上分析,推荐以下架构方案:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React 19)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │  Zustand     │  │  React Query │  │  Event Store     │       │
│  │  Stores      │  │  (Cache)     │  │  (去重/排序/回放)│       │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘       │
│         │                 │                    │                 │
│  ┌──────┴─────────────────┴────────────────────┴────────────┐   │
│  │          WebSocket Client + SSE Fallback                  │   │
│  │  ┌─────────────────┐    ┌──────────────────────────┐    │   │
│  │  │ Primary WS      │    │ SSE Fallback             │    │   │
│  │  │ (JSON-RPC)      │    │ (流式输出降级)           │    │   │
│  │  └─────────────────┘    └──────────────────────────┘    │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                    │
│  ┌──────────────────────────┴───────────────────────────────┐   │
│  │          REST API Client                                 │   │
│  │  (任务创建/审批/文件操作/历史查询)                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │    Backend (Node.js)    │
              │                         │
              │  ┌───────────────────┐  │
              │  │  WebSocket Server │  │
              │  │  (JSON-RPC)       │  │
              │  │  - 事件推送       │  │
              │  │  - 审批交互       │  │
              │  │  - 心跳/重连      │  │
              │  └────────┬──────────┘  │
              │           │             │
              │  ┌────────┴──────────┐  │
              │  │  SSE Server       │  │
              │  │  (流式输出降级)   │  │
              │  └────────┬──────────┘  │
              │           │             │
              │  ┌────────┴──────────┐  │
              │  │  REST API         │  │
              │  │  /api/v1/tasks    │  │
              │  │  /api/v1/approval │  │
              │  │  /api/v1/files    │  │
              │  └────────┬──────────┘  │
              │           │             │
              │  ┌────────┴───────────┐ │
              │  │  EventDispatcher   │ │
              │  │  (Pub/Sub + Store) │ │
              │  └────────┬───────────┘ │
              │           │             │
              │  ┌────────┴───────────┐ │
              │  │  Agent-Loop        │ │
              │  │  (LoopController)  │ │
              │  └────────────────────┘ │
              └─────────────────────────┘
```

### 3.2 传输层设计

#### 3.2.1 主通道: WebSocket + JSON-RPC

**协议设计:**
```typescript
// 请求帧 (Client -> Server)
{ jsonrpc: "2.0", id: "uuid", method: "task.send", params: { taskId, message } }

// 响应帧 (Server -> Client)
{ jsonrpc: "2.0", id: "uuid", result: { success: true } }
{ jsonrpc: "2.0", id: "uuid", error: { code: -32600, message: "..." } }

// 通知帧 (Server -> Client, 无需响应)
{ jsonrpc: "2.0", method: "event", params: { type: "phase:changed", data: {...}, seq: 42 } }
```

**为什么选择 JSON-RPC 2.0:**
- 标准化协议,生态工具丰富
- 支持请求-响应和通知两种模式
- id 字段天然支持请求关联
- 类型安全,易于 Schema 验证

**连接管理:**
```typescript
interface ConnectionConfig {
  url: string;
  reconnect: boolean;
  maxReconnectAttempts: 10;
  reconnectDelay: [1000, 30000];  // [initial, max]
  heartbeatInterval: 15000;       // 15 秒心跳
  heartbeatTimeout: 45000;        // 3 倍心跳超时
}
```

**重连策略:**
- 指数退避: 1s -> 2s -> 4s -> 8s -> 16s -> 30s(上限)
- 超过 10 次停止重连,提示用户手动刷新
- 重连时携带 `lastSeq` 参数,补发缺失事件

#### 3.2.2 降级通道: SSE

**使用场景:**
- WebSocket 不可用(网络限制/代理拦截)
- 仅需要接收流式输出(单向场景)
- 作为 WebSocket 断连期间的临时通道

**SSE 事件格式:**
```
id: 42
event: phase-changed
data: {"phase": "thinking", "turn": 3, "timestamp": "..."}

```

### 3.3 事件类型设计

#### 3.3.1 事件分类体系

```
AgentEvent
├── TaskLifecycle        (task:created, task:started, task:completed, task:failed, task:cancelled)
├── PhaseChanged         (phase:changed — 最核心的状态切换事件)
├── LLMInteraction       (llm:chunk, llm:complete, llm:error, llm:tool_calls)
├── ToolExecution        (tool:call, tool:security_check, tool:approval_request, tool:result, tool:error)
├── DetectionRecovery    (loop:detected, stuck:detected, context:compacting, model:fallback)
├── MultiAgent           (subagent:created, subagent:completed, subagent:failed)
└── Metrics              (cost:update, stats:update)
```

#### 3.3.2 核心事件定义

**Phase Changed 事件(状态机核心):**

```typescript
interface PhaseChangedEvent {
  type: "phase:changed";
  data: {
    taskId: string;
    phase: Phase;
    previousPhase: Phase;
    turn: number;
    phaseDetails?: Record<string, unknown>;
    timestamp: string;
  };
  seq: number;  // 单调递增序列号
}

type Phase =
  | "idle"              // 空闲
  | "thinking"          // LLM 思考中
  | "tool_call"         // 工具调用中
  | "tool_security"     // 安全检查中
  | "tool_approval"     // 等待用户审批
  | "tool_executing"    // 工具执行中
  | "context_compacting" // 上下文压缩中
  | "loop_correction"   // Loop 纠正中
  | "stuck_recovery"    // Stuck 恢复中
  | "model_fallback"    // 模型回退中
  | "subagent_running"  // 子 Agent 执行中
  | "completion_verification" // 完成条件验证
  | "completed"         // 任务完成
  | "failed"            // 任务失败
  | "cancelled";        // 任务取消
```

**Tool Approval Request 事件(用户交互):**

```typescript
interface ToolApprovalRequestEvent {
  type: "tool:approval_request";
  data: {
    taskId: string;
    toolCallId: string;
    toolName: string;
    input: Record<string, unknown>;
    risk: "low" | "medium" | "high";
    reason: string;
    timeout: number;  // 超时时间(ms)
    timestamp: string;
  };
  seq: number;
}
```

#### 3.3.3 事件流示例

```
seq: 1   task:created          → 前端: 创建任务卡片
seq: 2   task:started          → 前端: 显示"运行中"
seq: 3   phase:changed(thinking) → 前端: 显示"思考中..."
seq: 4   llm:chunk{text: "I"}  → 前端: 流式显示 "I"
seq: 5   llm:chunk{text: " need"} → 前端: 流式显示 " need"
...
seq: 15  llm:complete          → 前端: 停止流式,保存完整文本
seq: 16  llm:tool_calls        → 前端: 显示待执行工具列表
seq: 17  phase:changed(tool_call) → 前端: 切换到"工具调用"阶段
seq: 18  tool:call             → 前端: read_file 卡片变为 executing
seq: 19  tool:security_check   → 前端: 显示安全检查结果
seq: 20  tool:result           → 前端: 显示工具执行结果
seq: 21  cost:update           → 前端: 更新成本显示
seq: 22  phase:changed(thinking) → 前端: 切换到"思考中..."(下一轮)
...
seq: 50  task:completed        → 前端: 显示完成状态和结果
```

### 3.4 后端架构设计

#### 3.4.1 EventDispatcher (发布-订阅)

```typescript
interface IEventDispatcher {
  subscribe(taskId: string, lastSeq: number, sink: EventSink): Unsubscribe;
  publish(taskId: string, event: AgentEvent): Promise<void>;
  closeAll(taskId: string): void;
}

interface EventSink {
  onEvent(event: AgentEvent): void;
  onClose(): void;
}
```

**实现要点:**
- 内存事件队列: 最近 1000 个事件保留在内存,重连补发无需查 DB
- SQLite 持久化: 事件写入 `sse_events` 表,支持断线重连补发
- 批量写入: `llm:chunk` 每 10 个批量写入,减少 DB 写入 90%

#### 3.4.2 EventStore (持久化)

```sql
CREATE TABLE agent_events (
  seq INTEGER PRIMARY KEY,        -- 单调递增
  task_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_data TEXT NOT NULL,       -- JSON
  created_at TEXT DEFAULT (datetime('now')),
  INDEX idx_task_id (task_id),
  INDEX idx_created_at (created_at)
);
```

```typescript
interface IEventStore {
  save(taskId: string, event: AgentEvent): Promise<void>;
  getAfter(taskId: string, lastSeq: number): Promise<AgentEvent[]>;
  cleanup(maxAgeMs: number): Promise<number>;
  getStateSnapshot(taskId: string): Promise<TaskStateSnapshot>;
}
```

#### 3.4.3 WebSocket Server

```typescript
// 连接建立
ws.on('connection', (ws, req) => {
  const taskId = extractTaskId(req);
  const lastSeq = extractLastSeq(req);

  // 补发缺失事件
  if (lastSeq > 0) {
    const missed = eventStore.getAfter(taskId, lastSeq);
    missed.forEach(evt => ws.send(formatJSONRPC(evt)));
  }

  // 订阅实时事件
  const unsubscribe = dispatcher.subscribe(taskId, lastSeq, {
    onEvent: evt => ws.send(formatJSONRPC(evt)),
    onClose: () => unsubscribe()
  });

  // 心跳
  const heartbeat = setInterval(() => {
    ws.send(JSON.stringify({ jsonrpc: "2.0", method: "ping" }));
  }, 15000);

  ws.on('close', () => {
    clearInterval(heartbeat);
    unsubscribe();
  });
});
```

#### 3.4.4 REST API 端点

```
POST   /api/v1/tasks                    # 创建并启动任务
GET    /api/v1/tasks/:id                # 获取任务状态
DELETE /api/v1/tasks/:id                # 取消任务
POST   /api/v1/tasks/:id/approval       # 提交工具审批结果
GET    /api/v1/tasks/:id/events         # 获取历史事件(分页)
GET    /api/v1/tasks/:id/files          # 列出任务相关文件
GET    /api/v1/tasks/:id/files/:path    # 读取文件内容
POST   /api/v1/tasks/:id/files/:path    # 写入文件内容
```

### 3.5 前端架构设计

#### 3.5.1 状态管理

**Zustand Store 分层:**

```typescript
// 1. Task Store — 任务基本信息
interface TaskState {
  taskId: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled';
  message: string;
  createdAt: string;
}

// 2. Phase Store — 当前阶段
interface PhaseState {
  currentPhase: Phase;
  previousPhase: Phase;
  currentTurn: number;
}

// 3. LLM Store — LLM 输出
interface LLMState {
  streamingText: string;      // 当前流式文本
  completedText: string[];    // 已完成的文本段
  toolCalls: ToolCallInfo[];  // 工具调用列表
}

// 4. Tool Store — 工具执行历史
interface ToolState {
  toolCalls: ToolCallUI[];    // 工具调用历史
  pendingApproval: ApprovalRequest | null;
}

// 5. Detection Store — 检测与恢复
interface DetectionState {
  loopDetections: LoopDetection[];
  stuckDetections: StuckDetection[];
  contextCompactions: ContextCompaction[];
  modelFallbacks: ModelFallback[];
}

// 6. Metrics Store — 成本与统计
interface MetricsState {
  totalCost: number;
  budgetLimit: number;
  stats: TaskStats;
}
```

#### 3.5.2 WebSocket Client

```typescript
class AgentWebSocketClient {
  private ws: WebSocket | null = null;
  private pendingRequests = new Map<string, { resolve, reject }>();
  private eventHandlers = new Map<string, Set<(data: any) => void>>();
  private lastSeq = 0;
  private reconnectAttempts = 0;

  async connect(url: string, taskId: string) {
    this.ws = new WebSocket(`${url}?taskId=${taskId}&lastSeq=${this.lastSeq}`);

    this.ws.onmessage = (event) => {
      const frame = JSON.parse(event.data);

      if (frame.id && this.pendingRequests.has(frame.id)) {
        // 响应帧
        const { resolve, reject } = this.pendingRequests.get(frame.id);
        frame.error ? reject(frame.error) : resolve(frame.result);
      } else if (frame.method === "event") {
        // 通知帧
        const evt = frame.params;
        this.lastSeq = evt.seq;
        this.emit(evt.type, evt.data);
      } else if (frame.method === "ping") {
        // 心跳
        this.resetHeartbeatTimeout();
      }
    };

    this.ws.onclose = () => this.scheduleReconnect();
  }

  async sendRequest(method: string, params: any): Promise<any> {
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  on(eventType: string, handler: (data: any) => void): Unsubscribe {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType).add(handler);
    return () => this.eventHandlers.get(eventType).delete(handler);
  }

  private emit(eventType: string, data: any) {
    this.eventHandlers.get(eventType)?.forEach(h => h(data));
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= 10) return;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;
    setTimeout(() => this.connect(this.url, this.taskId), delay);
  }
}
```

#### 3.5.3 Event Store (前端)

```typescript
class EventStore {
  private events: AgentEvent[] = [];
  private eventIds = new Set<string>();

  addEvent(event: AgentEvent) {
    // O(1) 去重
    if (this.eventIds.has(event.seq.toString())) return;

    this.events.push(event);
    this.eventIds.add(event.seq.toString());

    // 按 seq 排序(支持乱序到达)
    if (this.events.length > 1 && event.seq < this.events[this.events.length - 2].seq) {
      this.events.sort((a, b) => a.seq - b.seq);
    }

    // 限制内存中的事件数(超过 5000 条清理旧事件)
    if (this.events.length > 5000) {
      this.events = this.events.slice(-3000);
      this.eventIds = new Set(this.events.map(e => e.seq.toString()));
    }
  }

  getEvents(): AgentEvent[] {
    return [...this.events];
  }

  getStateSnapshot(): TaskStateSnapshot {
    // 从事件流中重建状态快照
    return reconstructState(this.events);
  }
}
```

#### 3.5.4 React 组件结构

```
<TaskPanel>
├── <TaskStatusBar>          // 任务状态 + 阶段 + 轮次
├── <LLMOutputArea>          // LLM 流式输出 + 思考过程
│   ├── <ThinkingIndicator>  // 思考中动画
│   ├── <StreamingText>      // 流式文本(打字机效果)
│   └── <CompletedText>      // 已完成文本(可折叠)
├── <ToolCallTimeline>       // 工具调用时间线
│   ├── <ToolCallCard>       // 单个工具调用卡片
│   │   ├── <ToolIcon>       // 工具图标 + 名称
│   │   ├── <ToolParams>     // 参数(可展开)
│   │   ├── <StatusIndicator> // 状态(pending/executing/success/error)
│   │   ├── <SecurityChecks>  // 安全检查详情
│   │   └── <ToolResult>     // 执行结果(可展开)
│   └── <ApprovalDialog>     // 审批对话框(弹窗)
├── <DetectionNotifications> // 检测与恢复通知
│   ├── <LoopDetectionAlert> // Loop 检测警告
│   ├── <StuckDetectionAlert> // Stuck 恢复通知
│   └── <ModelFallbackAlert>  // 模型回退通知
├── <CostAndStatsPanel>      // 成本与统计
│   ├── <CostProgressBar>    // 成本进度条
│   ├── <TurnProgress>       // 轮次进度
│   └── <ContextWindowUsage> // 上下文窗口使用率
├── <SubAgentPanel>          // 子 Agent 面板
│   └── <SubAgentCard>       // 子 Agent 卡片(类型/任务/状态)
└── <ActionButtons>          // 操作按钮(暂停/继续/取消)
```

### 3.6 可靠性设计

#### 3.6.1 断线重连

```
前端                    后端
  |---- WS Open --------->|
  |---- ?lastSeq=15 ------>|
  |<-- event(seq:16) -----|  (补发)
  |<-- event(seq:17) -----|  (补发)
  |<-- event(seq:18) -----|  (补发)
  |=== 实时事件 ==========|
  |<-- event(seq:19) -----|
```

**重连流程:**
1. WebSocket 断连,触发 `onclose`
2. 指数退避重连(1s -> 2s -> 4s -> ... -> 30s)
3. 重连时携带 `lastSeq` 参数
4. 后端从 EventStore 查询 `seq > lastSeq` 的事件
5. 按顺序补发,补发完成后开始推送实时事件
6. 前端 EventStore O(1) 去重,避免重复渲染

#### 3.6.2 心跳机制

- 后端每 15 秒发送 ping 通知
- 前端收到 ping 后重置超时计时器
- 超过 45 秒(3 倍心跳间隔)未收到 ping,主动断连并触发重连

#### 3.6.3 事件限流

| 事件类型 | 频率 | 策略 |
|---------|------|------|
| `llm:chunk` | ~50-200/s | 前端用 requestAnimationFrame 节流渲染 |
| `cost:update` | 每轮 1 次 | 无需限流 |
| `stats:update` | 每轮 1 次 | 无需限流 |
| 其他事件 | 按需 | 无需限流 |

#### 3.6.4 事件清理

```sql
-- 每天清理超过 24 小时的事件
DELETE FROM agent_events WHERE created_at < datetime('now', '-24 hours');
```

已完成的任务保留完整事件日志,支持事后回放。

### 3.7 性能优化

#### 3.7.1 后端优化

| 优化点 | 策略 | 效果 |
|--------|------|------|
| 事件批量写入 | llm:chunk 每 10 个批量写入 SQLite | 减少 DB 写入 90% |
| 内存事件队列 | 最近 1000 个事件保留在内存 | 重连补发无需查 DB |
| 连接池 | 同一任务多订阅者共享事件源 | 减少重复推送 |
| Gzip 压缩 | tool:result 大输出事件启用压缩 | 传输体积减少 60% |

#### 3.7.2 前端优化

| 优化点 | 策略 | 效果 |
|--------|------|------|
| requestAnimationFrame | LLM chunk 渲染限制到 60fps | 避免渲染卡顿 |
| 虚拟滚动 | 工具调用时间线超过 50 条启用 | 保持流畅滚动 |
| 文本增量渲染 | LLM chunk 只做 append,不重新渲染 | 减少 DOM 操作 |
| Web Worker 解析 | 大 JSON 事件在 Worker 中解析 | 不阻塞主线程 |

### 3.8 安全设计

#### 3.8.1 传输安全

- WebSocket 使用 WSS(加密)
- JSON-RPC 请求携带 auth token
- 心跳超时自动断连

#### 3.8.2 审批机制

```
Agent                    前端                    用户
  |                       |                       |
  |-- tool:approval_request -->|                   |
  |                       |-- 显示审批对话框 ----->|
  |                       |<-- 用户批准/拒绝 -----|
  |<-- POST /approval ----|                       |
  |-- 继续执行/拒绝 ------->|                       |
```

#### 3.8.3 权限控制

- 不同事件类型需要不同权限
- 工具执行前安全检查(多检查器链)
- 高风险操作强制用户确认

---

## 四、与各产品的对比总结

### 4.1 我们的方案借鉴了哪些最佳实践

| 设计点 | 借鉴来源 | 应用方式 |
|--------|----------|----------|
| JSON-RPC over WebSocket | OpenClaw, Goose | 结构化双向通信 |
| 事件去重 + 时间戳排序 | OpenHands | O(1) eventId Set 检查 |
| seq 序列号 + dropIfSlow | OpenClaw | 慢客户端保护 |
| 双通道状态更新 | Cline | ExtensionState + PartialMessage |
| Newline-gated 流式 | Codex CLI | 打字机效果 |
| Zustand + React Query | OpenHands, Goose | 状态管理分层 |
| 三层 Loop 检测 | Gemini CLI | 工具重复 + 内容重复 + LLM 辅助 |
| 五种 Stuck 检测 | OpenHands | 覆盖最常见卡住场景 |
| Hook 系统 | Claude Code, Gemini CLI | 8 种 Hook 覆盖全生命周期 |
| 挑战-响应握手 | OpenClaw | 安全连接建立 |

### 4.2 我们的方案改进了什么

| 改进点 | 问题 | 解决方案 |
|--------|------|----------|
| 统一协议 | 各产品协议各异 | 采用标准 JSON-RPC 2.0 |
| 事件持久化 | 部分产品无持久化 | SQLite + TTL 自动清理 |
| 断线重连 | 部分产品无重连机制 | lastSeq 补发 + 指数退避 |
| 流控机制 | 大事件阻塞 | dropIfSlow + 反压分级 |
| 前端事件总线 | 直接绑定,难以扩展 | EventStore 统一管理 |
| 审批交互 | 部分产品无审批 | 标准化审批请求/响应 |
| 成本追踪 | 部分产品无成本 | cost:update 实时推送 |

---

## 五、实施计划

### Phase 1: 核心基础设施 (Week 1-2)
- [ ] 实现 EventDispatcher (Pub/Sub)
- [ ] 实现 EventStore (SQLite 持久化)
- [ ] 实现 WebSocket Server (JSON-RPC)
- [ ] 实现 SSE Server (降级通道)

### Phase 2: Agent-Loop 集成 (Week 3-4)
- [ ] 在 LoopController 中集成事件发射
- [ ] 实现所有事件类型定义
- [ ] 实现阶段状态机流转
- [ ] 实现 Loop 检测 + Stuck 检测

### Phase 3: 前端基础 (Week 5-6)
- [ ] 实现 WebSocket Client (JSON-RPC)
- [ ] 实现 EventStore (前端去重/排序)
- [ ] 实现 Zustand Store 分层
- [ ] 实现 React Query 缓存

### Phase 4: UI 组件 (Week 7-8)
- [ ] 实现 TaskPanel 主面板
- [ ] 实现 LLMOutputArea (流式输出)
- [ ] 实现 ToolCallTimeline (工具时间线)
- [ ] 实现 ApprovalDialog (审批对话框)
- [ ] 实现 DetectionNotifications

### Phase 5: 可靠性 + 性能 (Week 9-10)
- [ ] 实现断线重连 + 事件补发
- [ ] 实现心跳机制
- [ ] 实现事件限流
- [ ] 实现性能优化(虚拟滚动,增量渲染等)

### Phase 6: 测试 + 文档 (Week 11-12)
- [ ] 单元测试
- [ ] 集成测试
- [ ] E2E 测试
- [ ] 文档编写

---

> **本文档与 `sse-streaming-design.md` 中的 SSE 事件协议完全对齐,所有事件类型和阶段枚举对应 Loop 控制器中的实际状态流转。**
