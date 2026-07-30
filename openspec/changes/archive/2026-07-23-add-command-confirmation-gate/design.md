## Context

`shell` 工具是全仓唯一的命令执行路径（`backend/src/infrastructure/tools/builtin/shell.py`），用 `asyncio.create_subprocess_shell` 把原始命令串经 `/bin/sh -c` 执行，无 shlex 拆分、无转义。工具执行走一条**完全线性、单入口**的链路：

```
ToolExecuteNode._execute_single_tool  (tool_execute_node.py:76)
  → ToolRegistry.execute             (registry.py:66-81)
  → ExecutionPipeline.execute         (pipeline.py:40)
  → 洋葱中间件: Security → RateLimit → Timeout(30s) → Sandbox → final_handler
  → final_handler: t.func(inp, ctx)   (pipeline.py:54，全仓唯一 .func 调用)
```

中间件协议 `async def process(tool, input, context, next_handler) -> ToolResult`（`register/pipeline.py:15-24`，`tools/pipeline.py` 为兼容 shim）天然允许在调用 `next_handler` 前 `await` 任意异步闸门。`tool_call_id` 已在 `tool_execute_node.py:53` 被塞进 `context.extra`。

关键现状缺口：

- **0 命令分类**：全仓无任何黑 / 白名单、正则、危险分级；`SandboxMiddleware` 是 no-op（只事后打 `sandboxed=True` 标记）。
- **0 工具级同步请求 / 响应**：既有"暂停"模式（`clarify`）是灭火式——返回 `metadata.awaiting_user_input=True` → `route_after_tool_execute` 路由到 `END` → 任务置 `COMPLETED` → 用户回答是一条**新消息**开新 turn。无 `interrupt()`、无 checkpointer（`workflow_builder.py:63` `compile()` 无 checkpointer 参数）。
- **sub-agent / team 绕过全部中间件**：`agent_loop_runner.py` 的 `_build_tool_registry` 用**默认空 `ExecutionPipeline`** 构造 registry（约 420、454 行），故这些 scoped registry 的工具调用不过任何中间件。而 team member / sub-agent **是带 `shell` 工具的**。
- **SSE 只有 `tool:call` / `tool:result`**（`event_types.py:33-35`），运行态仅 `running → success|error`。保留未用的 `task:paused` / `task:resumed` 事件与 `TaskStatus.PAUSED`，以及声明却全仓未读的 `ToolCallState{VALIDATING/SCHEDULED/...}` 枚举。
- 部署：单机自用，事件循环存活、SSE 流保持即满足。

## Goals / Non-Goals

**Goals:**

- 命中可配置危险命令集合的 `shell` 调用，在执行前**同步阻塞**等待用户确认。
- 三选项：本次允许 / 全部允许 / 拒绝；"全部允许"在本会话内对同类命令不再追问。
- 非危险命令、已放行命令**零打扰**。
- 覆盖 sub-agent / team 成员的 `shell` 调用（它们当前绕过中间件）。
- 前端在工具挂起期间渲染确认卡，按钮经新端点回传决策、唤醒被阻塞的工具。

**Non-Goals:**

- 不做命令改写 / 沙箱化执行（`SandboxMiddleware` 真正落地是另一独立工作）。
- 不做抗崩溃持久化（见 Decisions 的 C 路线）。
- 不覆盖 `shell` 以外的工具（架构上通用，但本变更只闸 `shell`）。
- 不复用 `clarify` 那套灭火式回路——我们阻塞而非终止。

## Decisions

### 决策 α：阻塞闸门（B），而非灭火式（A）或抗崩溃（C）

三种路线对比：

| | A 灭火式复用 | B 同步阻塞闸门 | C 持久化暂停 |
|---|---|---|---|
| 是否真阻塞 | ✗ turn 终止 | ✓ `await Future` | ✓ |
| LLM 上下文保活 | ✗ 要重发 | ✓ 原地 | ✓ |
| "全部允许"落地 | 麻烦（要 stash 命令） | 顺（会话级 store） | 顺 |
| 回答回路 | 新消息→LLM 重读 | 专用 approve 端点 | 专用 approve 端点 |
| 重启安全 | ✓（消息已持久） | ✗ 内存 Future 丢 | ✓（落 DB） |
| 复用现成件 | `awaiting_user_input`+END | （无，需新建端点+Event） | +`PAUSED` 状态 |

**选 B。** 理由：① 最贴用户原话"调用前加前置操作"+"页面上确认"——工具协程原地挂起、turn 不终止；② allow / deny / allow-all 是**系统决策**，不该让 LLM 当聊天重新解读再重发命令（A 的致命伤：回答成新消息、原 `tool_call_id` 被废弃、`ToolMessage` 不会被重注入新 turn，靠 LLM"大概会"重发同一命令不可靠）；③ 工程量小于 C——单机自用场景下，重启丢失待审批可接受（task 置 failed / 用户重跑）。

**否决 A**：让系统解读决策而非 LLM，意味着 A 也得新建专用端点 + 命令 stash + 自动重放，净工程量反超 B，且污染 agent loop turn 逻辑。
**否决 C（本变更内）**：`workflow.compile()` 无 checkpointer 可借，C 要从零造持久化（DB 暂存待审批 + task 置 `PAUSED` + 重启重注入挂起 tool_call + 点亮 `task:paused` / `resumed`），列为未来升级。

### 决策 β：内存态审批，单机自用

`SessionApprovalStore` 与待审批 `Future` 都在进程内存。重启 → 待审批 Future 丢失 → 该 task 标记 failed（或保留 running 由看门狗收尾），用户重跑即可。无 DB 持久化。这是 B 的明确取舍，C 路线才上 DB。

### 决策 γ：可配置危险命令集合 + 复合 shell 颗粒度

危险集合放**配置文件**（非硬编码），默认含 `rm -rf`、`sudo`、输出重定向 `>`、`mkfs`、`dd if=`、`chmod -R`、`curl|sh` / `wget|sh`、fork bomb `:(){ :|:& };:` 等。

**匹配颗粒度**（难点）：复合 shell 串含管道 / `&&` / `;` / `$()` / 子 shell。选**危险词扫描**而非精确命令拆分：用 `shlex` 尽力拆出顶层命令段（按 `;` / `&&` / `||` / `|` 切），对每段提取首词为命令名；再对**整串**做危险词正则扫描。两条命中其一即判需确认。理由：精确拆分 shell 语法易错且漏判（`$()` 展开后才知危险），危险词扫描保守偏向"多问"，符合安全闸门语义。误报代价（多一次确认）远低于漏报代价（删库）。

### 决策 δ："全部允许" = 本会话级、按命令类别

`SessionApprovalStore` 以会话为作用域（非跨会话持久），key 为**命令类别 / 模式**（如 `rm-recursive`、`sudo`、`redirect-overwrite`），非精确命令串。理由：按精确串放行几乎等于"本次允许"，失去意义；按类别放行才真正减少打扰。会话级避免长期放行累积风险（重启 / 新会话重新把关）。

### 决策 ε：拒绝 = 回 `user_denied` 给 LLM，不中止任务

拒绝时返回 `ToolResult(success=False, error="user_denied", output="用户拒绝执行该命令")`，工具调用正常返回、LLM 据此自行调整方案（换命令 / 放弃 / 解释）。不中止整条 task——保持 Agent 自主性，把"怎么办"交回 LLM。

### 决策 ζ：注入确认 pipeline 到 sub-agent / team scoped registry

`_build_tool_registry` 当前用空 `ExecutionPipeline`。本变更让它注入一个**确认能力 pipeline**。

**副影响处理**：注入非空 pipeline 后，sub-agent / team 工具将首次受 `Security` / `RateLimit` / `Timeout` / `Sandbox` 约束（既有行为变化）。design 取向：**注入与顶层相同的全量 pipeline**（而非仅 `Confirmation`），理由——这些中间件本就该对所有执行生效，sub-agent / team 当前"绕过"本身就是缺陷；顺带修正。若实现期发现回归问题，可降级为仅注入 `Confirmation`（design 留此 fallback，见 Open Questions）。

注入点共三处，缺一不可：① 顶层 `create_tool_registry()`（`dependencies.py`）；② team 的 `_build_tool_registry` 分支（`agent_loop_runner.py:420` 的 `ToolRegistry()` 无参 → 空 pipeline）；③ sub-agent 经 `registry_factory=lambda: ToolRegistry()`（`agent_loop_runner.py:454`）+ `SubAgentOrchestrator.create_sub_agent_tool_registry`（后者 spec 须一并改，不能仍注入空 pipeline）。注入的 pipeline 中的 `ConfirmationMiddleware` 必须经决策 θ 的访问器取**共享**审批存储实例，否则端点解析不到 sub-agent/team 的 Future。

### 决策 η：审批超时 5 分钟自动 deny

`ConfirmationMiddleware` 用 `asyncio.wait_for(Future, timeout=300)` 包裹等待；超时返回 `error="approval_timeout"`（视同 deny）。防止挂起的 Future 永久占内存 / 工具协程永久挂起。超时时长配置化，默认 300s。

### 决策：中间件排序——Confirmation 置于 Timeout 之外

`TimeoutMiddleware` 把 `next_handler` 包在 `asyncio.wait_for(30s)` 里。若 `Confirmation` 在其**之内**，用户思考超 30s 会把闸门 kill。故 `Confirmation` **必须 add 在 `Timeout` 之前**（= 更外层）。组装顺序：

```
Confirmation → Security → RateLimit → Timeout(30s) → Sandbox → final_handler
```

这样 30s 超时只包"批准后的真实执行"，不含等待审批时间。

### 决策：SSE 事件与状态

新增 `tool:confirmation_required` 事件（payload：`{toolCallId, command, riskReason, workingDir, options:[allow_once,allow_all,deny]}`），**不**复用保留未用的 `task:paused`（task 状态保持 running，只是工具协程挂起）。前端 segment 新增 `toolStatus: 'awaiting_confirmation'`。可顺带点亮死枚举 `ToolCallState`（加 `AWAITING_CONFIRMATION`），但运行态用 ad-hoc 字符串亦可，非阻塞。

### 决策：emitter 注入 `context.extra`

中间件只收 `context`（`ToolContext`），拿不到 graph config 里的 event emitter。在 `tool_execute_node.py:53`（已设 `tool_call_id`）处顺手把 emitter 塞进 `context.extra["event_emitter"]`，`ConfirmationMiddleware` 即可经它发 `tool:confirmation_required`。备选：在节点层（`tool:call` 之后、`tool_registry.execute` 之前）发确认事件——但那样分类逻辑就散到节点、脱离中间件，不取。

### 决策 θ：审批存储为进程级共享单例 + 按"有效 task_id"建键

`PendingApprovalRegistry` 与 `SessionApprovalStore` 都是**进程级单例**——在 `presentation/dependencies.py` 提供 `get_pending_approval_registry()` / `get_session_approval_store()` 访问器，仿 `get_llm_settings` 的 `@lru_cache` 模式。所有 `ConfirmationMiddleware` 实例（顶层 / sub-agent / team member）与 `POST /approvals` 端点**都经访问器取同一实例**。

理由：确认 Future 产生于"每次新建"的 pipeline——`create_tool_registry()` 每用例新建、`_build_tool_registry()` 每次调用新建——但端点只凭 `(task_id, tool_call_id)` 解析、不知 Future 来自哪个作用域。只有共享单例才能让端点够得着 sub-agent/team 的 Future。这恰好承接决策 β（单机内存态）：进程单例就是那块内存。`SessionApprovalStore` 同理必须共享：sub-agent 的 allow-all 才能在同会话的顶层 agent 生效，符合 spec"同会话不再追问"语义——per-pipeline store 会割裂这一语义。

**键的一致性（关键子问题）**：端点路径含 `task_id`，但 sub-agent/team 的 Future 若按其自身 `context.task_id`（sub-task）登记、前端却按所在 SSE 流的**父 task_id** POST，键不匹配 → 404。复用既有管线：sub-agent（`tool_execute_node.py:191`）与 team member（`team_tools.py:162`）都已把 `parent_task_id` 放进 `context.extra`，且二者事件**本就发在父 task_id 上**（`team_tools.py:340`）。故：

- `PendingApprovalRegistry` 键 = `(effective_task_id, tool_call_id)`，其中 `effective_task_id = context.extra.get("parent_task_id") or context.task_id`——sub-agent/team 取父 task_id、顶层取自身 task_id。
- `ConfirmationMiddleware` 登记 Future 与发 `tool:confirmation_required` 都用 `effective_task_id`。
- 前端收到事件时所在流即父 task_id，POST `/api/tasks/{父task_id}/approvals` 与登记键一致。
- 事件 payload 补 `taskId`（= `effective_task_id`），让前端不必靠"所在流"推断，多任务卡片场景也稳。

## Risks / Trade-offs

- **[重启丢失待审批]** → 单机自用可接受；task 标 failed、用户重跑。未来上 C（DB 持久化）彻底解。
- **[危险词扫描误报]** → 多一次确认，成本低；可接受，符合安全闸门"宁多问不漏"。配置文件可调。
- **[危险词扫描漏报]** → 真风险。缓解：默认集合保守偏严 + 记录命中 / 未命中日志便于审查；明确"非安全沙箱，仅人在回路提示"，不替代真沙箱。
- **[sub-agent 注入全量 pipeline 的回归]** → 原本绕过中间件的 sub-agent / team 工具突然受 `RateLimit` / `Timeout` 约束可能改变行为。缓解：实现期跑回归（尤其 team 多成员并发调用触发 `RateLimit`）；必要时降级为仅注入 `Confirmation`（见 Open Questions）。
- **[多个待确认命令并发]** → 一个 turn 内 LLM 可能并发多个 shell `tool_call`（`tool_execute_node` 用 `asyncio.gather`）。每个 `tool_call` 各自挂起、各自确认；前端按 `toolCallId` 区分卡片。无全局锁。需确保 `SessionApprovalStore` 并发安全（`asyncio.Lock` 或线程安全结构）。
- **[用户离线 / 关闭页面]** → 5 分钟超时自动 deny 收尾，不留僵尸 Future。
- **[clarify / task_create 优先级过滤]** → 非风险，记录交互：一 turn 内若 LLM 同时发危险 `shell` 与 `clarify` / `task_create`，后者会把 `shell` 过滤掉、本 turn 不执行（`tool_execute_node.py:228-259`）；`shell` 延后到下一 turn 才触发确认门。符合预期，无需处理。

## Migration Plan

新增能力，无数据迁移。部署：

1. 合入危险命令集合配置文件，默认集合随变更交付。
2. 前后端同步发布（新 SSE 事件 + 新端点 + 新前端卡）。
3. 回滚：移除 `ConfirmationMiddleware` 的 `add_middleware` 一行 + 前端忽略未知事件即可恢复原行为（危险命令集合配置与 classifier 留存无害）。

## Open Questions

- sub-agent / team 注入：**已选全量 pipeline**（决策 ζ 主决策）。6.2 单元级并发回归通过、未触发降级；真实 team 多成员并发下的 RateLimit / Timeout 回归仍待 8.x E2E 确认，届时若回归再降级为仅 `Confirmation`。
- 危险命令集合的默认条目与分类类别名——评审配置文件草稿时定稿。
- "全部允许"作用域是否需要可配置（会话级 vs agent 级）——初版固定会话级，按需再加。
- 超时时长 300s 是否需配置化暴露——初版写死默认 + 配置文件可覆盖。
