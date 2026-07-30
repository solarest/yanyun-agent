## Why

`shell` 工具通过 `asyncio.create_subprocess_shell` 把原始命令串直接喂给 `/bin/sh -c`，全仓**没有任何命令分类 / 黑名单 / 危险判定**——工具描述里"dangerous commands may be blocked by security policy"是一句空头支票，从未实现。结果是：Agent（尤其自主运行的 sub-agent / team member）可以无任何人在回路地执行破坏性命令（`rm -rf`、`sudo`、`dd`、`mkfs`…）。本变更新增一道**执行前确认闸门**：命中可配置危险命令集合的 `shell` 调用，先在 UI 上请用户拍板（本次允许 / 全部允许 / 拒绝），放行或拒绝后才继续。

## What Changes

- 新增 `CommandClassifier`：从配置文件读取危险命令集合，判定一条 shell 命令是否需要确认（含复合 shell——管道 / `&&` / `;` / `$()` / 子 shell——的匹配颗粒度策略）。
- 新增 `ConfirmationMiddleware`：挂进工具 `ExecutionPipeline`，对需要确认的 `shell` 调用**同步阻塞**在一个 `asyncio.Future`（以 `tool_call_id` 为 key）上，直到用户响应；非危险命令与已放行命令不受影响。
- 新增 `SessionApprovalStore`：本会话级、按命令类别 / 模式的"全部允许"白名单，闸门每次先查它、命中即直放。
- 新增 SSE 事件 `tool:confirmation_required`：工具挂起期间向前端推送待确认信息（命令、风险原因、`toolCallId`）。
- 新增 `POST /api/tasks/{task_id}/approvals` 端点：`{toolCallId, decision: allow_once|allow_all|deny}` 唤醒对应 Future。
- 新增前端 `CommandConfirmCard`（克隆 `ClarifyCard` 骨架）+ approval API 客户端 + `useChat` SSE 处理 + `MessageBubble` 路由。
- 把"确认能力 pipeline"注入 sub-agent / team 的 scoped registry——它们当前用空 `ExecutionPipeline`、绕过所有中间件。
- 拒绝时返回 `ToolResult(success=False, error="user_denied")` 给 LLM 自行调整，不中止整条任务。

无对外契约破坏：`tool:call` / `tool:result` 契约不变，仅新增一个事件与一个端点；非危险命令行为不变。

## Capabilities

### New Capabilities

- `command-confirmation`: 对 `shell` 工具的执行前人在回路确认——危险命令分类、同步阻塞闸门、会话级"全部允许"白名单、确认所需的 SSE 事件与 HTTP 端点、前端确认卡。

### Modified Capabilities

<!-- 无既有 spec：openspec/specs/ 为空，本变更为首个能力，无既有需求被修改。 -->

## Impact

- **后端**：`infrastructure/tools/register/middleware/`（新增 `ConfirmationMiddleware`）、`presentation/dependencies.py`（pipeline 组装顺序——Confirmation 须置于 `TimeoutMiddleware` 之外）、`infrastructure/agent/nodes/tool_execute_node.py`（把 event emitter 注入 `context.extra`）、`application/services/agent_loop_runner.py`（scoped registry 注入确认 pipeline）、新增 classifier / approval store / approvals 路由 / SSE 事件枚举与 DTO。
- **前端**：`presentation/components/chat/`（新增 `CommandConfirmCard`）、`application/services/useChat.ts`、`presentation/components/chat/MessageBubble.tsx`、`domain/entities/events.ts`、新增 `approvalApi`。
- **副影响（须在 design 妥善处理）**：给 sub-agent / team scoped registry 注入非空 pipeline 后，这些原本绕过中间件的工具将**首次**受到 `Security` / `RateLimit` / `Timeout` / `Sandbox` 约束——是既有行为变化，design 需决定是注入全量 pipeline 还是仅注入 `Confirmation`。
- **配置**：新增一份危险命令集合配置文件（非硬编码）。
- **不在范围内**：抗崩溃持久化（C 路线——DB 暂存待审批 + task 置 `PAUSED` + 重启重注入 + 点亮 `task:paused` / `task:resumed`）列为未来升级，仅 design.md 提及，本变更不实现。
