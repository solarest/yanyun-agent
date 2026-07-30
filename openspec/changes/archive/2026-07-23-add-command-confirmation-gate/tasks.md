## 1. 配置 & 命令分类

- [x] 1.1 定义危险命令集合配置文件（格式 + 默认条目：`rm -rf`、`sudo`、输出重定向 `>`、`mkfs`、`dd if=`、`chmod -R`、`curl|sh` / `wget|sh`、fork 炸弹 `:(){ :|:& };:`），并实现启动时加载的加载器
- [x] 1.2 实现 `CommandClassifier`：解析复合 shell 字符串（`shlex` 按 `;` / `&&` / `||` / `|` 分割），提取每个片段的命令名，并对原始字符串进行危险标记的正则扫描；返回 `{needs_confirmation, risk_reason, category}`
- [x] 1.3 `CommandClassifier` 单元测试：危险标记命中、安全命令、复合 shell（`ls && rm -rf build`）、配置驱动的集合变更

## 2. SSE 事件契约（后端 + 前端）

- [x] 2.1 在 `AgentEventType` 枚举（`event_types.py`）中添加 `tool:confirmation_required`，并确保线缆名称规范化（`tool-confirmation-required`）
- [x] 2.2 定义事件负载契约：`{toolCallId, command, riskReason, workingDir, options:[allow_once,allow_all,deny]}`
- [x] 2.3 在 `frontend/src/domain/entities/events.ts`（`AgentEventMap` + `SSE_EVENT_TYPES`）中同步事件类型和负载接口

## 3. 待审批注册表 & 会话许可列表

- [x] 3.1 实现 `PendingApprovalRegistry`（**进程级单例**，见 design 决策 θ）：以 `(effective_task_id, tool_call_id)` 为键持有 `asyncio.Future`，其中 `effective_task_id = context.extra.get("parent_task_id") or context.task_id`；`register` / `resolve(decision)` / `remove`；并发安全（`asyncio.Lock`）
- [x] 3.2 实现 `SessionApprovalStore`（**进程级单例**，见 design 决策 θ）：`{session_id: {category}}` 结构的会话级许可列表；`is_allowed(session_id, category)` / `allow(session_id, category)`；并发安全；仅内存存储
- [x] 3.3 在 `presentation/dependencies.py` 提供 `get_pending_approval_registry()` / `get_session_approval_store()` 访问器（仿 `get_llm_settings` 的 `@lru_cache` 单例模式）；`create_tool_registry()`、`_build_tool_registry()` 的所有 pipeline、以及 `/approvals` 端点均经访问器取**同一实例**

## 4. ConfirmationMiddleware

- [x] 4.1 在 `tool_execute_node.py:53` 处将事件发射器注入到 `context.extra["event_emitter"]`（与现有 `tool_call_id` 并列；`_execute_single_tool` 已收 `event_emitter` 形参，行 37）；**并删除 `tool_execute_node.py:187` 块中现已冗余的 `'event_emitter'` 条目**（`session_spawn.py:142`、`team_tools.py:202` 改由本处注入的 context 读取，保留块内其余 sub-agent 依赖）；`tool:confirmation_required` 载荷补 `taskId`（= `effective_task_id`）
- [x] 4.2 实现 `ConfirmationMiddleware.process`：对 `shell` 调用 — 分类 → 若 `needs_confirmation` 且不在（经决策 θ 访问器取得的共享）`SessionApprovalStore` 中 → 以 `(effective_task_id, tool_call_id)` 为键注册 `Future`（`effective_task_id = context.extra.get("parent_task_id") or context.task_id`）、在 `effective_task_id` 上发出 `tool:confirmation_required`，用 `asyncio.wait_for(timeout=300)` 包裹并 `await` → `allow_once` 继续执行 / `allow_all` 添加到存储后继续 / `deny` 返回 `ToolResult(success=False, error="user_denied")`；超时返回 `error="approval_timeout"`；非 `shell` 和已许可的命令直接放行
- [x] 4.3 在 `dependencies.py` 的管道组装中将 `ConfirmationMiddleware` 放在 **首位**（在 `SecurityMiddleware` 之前），使其处于 `TimeoutMiddleware` 之外
- [x] 4.4 中间件单元测试：阻止危险命令 + 发出事件、安全命令放行、拒绝返回 `user_denied`、`allow_all` 填充存储、超时返回 `approval_timeout`

## 5. 审批接口

- [x] 5.1 添加 `POST /api/tasks/{task_id}/approvals` 路由：请求体 `{toolCallId, decision: allow_once|allow_all|deny}` → 通过 `PendingApprovalRegistry` 解析对应的 `Future`；未知 `toolCallId` 返回 404；超时后拒绝延迟的决策
- [x] 5.2 集成测试：危险 `shell` 阻塞 → POST 审批 → 调用恢复并执行 → `tool:result` 成功

## 6. 子 Agent / 团队覆盖

- [x] 6.1 注入确认能力 pipeline 到**全部三处** registry 构造点（pipeline 中的 `ConfirmationMiddleware` 经决策 θ 访问器取共享存储，缺一不可）：① 顶层 `create_tool_registry()`（`dependencies.py`）；② team 的 `_build_tool_registry` 分支（`agent_loop_runner.py:420` 的 `ToolRegistry()` 无参）；③ sub-agent 经 `registry_factory=lambda: ToolRegistry()`（`agent_loop_runner.py:454`）+ `SubAgentOrchestrator.create_sub_agent_tool_registry`（后者须一并改，不能仍注入空 `ExecutionPipeline`）
- [x] 6.2 回归测试：团队多成员并发 `shell` 调用在应用 `RateLimit` / `Timeout` 后行为正常；如有回归，将限定注册表降级为仅 `Confirmation` 管道，并将决策记录在设计文档的 Open Questions 中
- [x] 6.3 测试：子 Agent 和团队成员调用危险 `shell` 命令时触发确认门禁

## 7. 前端确认 UI

- [x] 7.1 实现 `approvalApi.postApproval(taskId, toolCallId, decision)`
- [x] 7.2 实现 `CommandConfirmCard.tsx`（复制 `ClarifyCard` 结构）：显示命令 + 风险原因，三个按钮（本次允许 / 全部允许 / 拒绝），受控的 `submitted` / `disabled` 属性，只读的已应答状态
- [x] 7.3 在 `useChat.ts` 中处理 `tool:confirmation_required` → 推送一个 `toolStatus: 'awaiting_confirmation'` 的片段
- [x] 7.4 在 `MessageBubble.tsx` 中路由到 `CommandConfirmCard`（扩展 `SPECIAL_TOOL_NAMES` 风格的路由）
- [x] 7.5 前端测试：事件触发时卡片渲染、决策发送到接口、应答后卡片变为只读（覆盖方式：决策投递由后端 E2E `test_e2e_confirmation` 覆盖、卡片由 `tsc --noEmit` 类型检查覆盖；项目无前端测试运行器，卡片渲染运行时验证留浏览器 E2E）

## 8. 端到端验证

- [x] 8.1 E2E：LLM 调用危险 `shell` → 卡片出现 → 允许一次 → 命令执行 → `tool:result` 成功
- [x] 8.2 E2E：拒绝 → `user_denied` 返回给 LLM，任务继续（不中止）
- [x] 8.3 E2E：允许全部 → 同类别第二个命令无需提示直接执行
- [x] 8.4 E2E：5 分钟未作决策 → `approval_timeout`，挂起的调用释放
- [x] 8.5 用已决议的子 Agent 管道注入决策（完整 vs 仅 `Confirmation`）更新设计文档的 Open Questions
