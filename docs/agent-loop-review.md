# WordLight Agent Loop 执行链审查报告

> 审查方式:纯只读静态审查(未修改任何文件)。
> 审查范围:`infrastructure/agent/nodes/*`、`application/services/agent_loop_{runner,context,lifecycle}.py`、`application/agent_loop/*`、`graph_resume_manager.py`、`prompt_context_impl.py`、`sse_stream.py`、`domain/agent_loop/*`、`infrastructure/tools/confirmation/*`、相关单元测试。
> 以下按严重程度排序。标注「需运行验证」的条目表示无法仅从静态阅读确认精确行为。

---

## 一、高危发现

### H1. 确认中断(resume)后整批工具重复执行,同批副作用翻倍
- **位置**:`tool_execute_node.py:274-363`
- **问题**:`_execute_single_tool` 对 `pending_tools` **整批并行执行后才检查确认标记**;命中 `CONFIRMATION_METADATA_KEY` 后 `interrupt()` 暂停。LangGraph 的 interrupt 语义是:恢复时以 checkpoint 时的**节点输入状态**重新执行整个节点。因此 resume 时 `execute()` 从头重跑,整批工具再次执行:
  - 同批**非确认**工具(如 `file_write`、`web_search`)副作用执行 2 次(中断前 1 次 + resume 1 次),即使最终用户 **deny** 也无法撤回;
  - 确认工具本身因中间件在闸门前返回标记(不真正执行,见 `confirmation.py:103-115`),副作用恰好只发生 1 次——掩盖了问题;
  - 若同批有 N 个危险命令,每次 resume 只处理第一个(`break`,见 :363),其余确认被静默丢弃。
- **为什么是问题**:确认闸门形同虚设(兄弟工具已在确认前执行),且 shell/file 类工具重复执行是严重的正确性+安全缺陷。
- **修复方向(最小改动)**:确认检查放到执行**之前**:先扫描 `pending_tools` 是否存在确认标记工具——无法预知,正确做法是改为「先逐工具执行,命中确认即中断,中断**前不执行后续工具**」,即把 gather 拆成顺序执行并在确认处提前 `interrupt()`;resume 后用状态字段(如 `interrupted_call_id`)跳过已执行工具。需运行验证具体执行次数。

### H2. 进程重启后的 checkpoint 恢复路径配置残缺,必然失败
- **位置**:`graph_resume_manager.py:142-209`(`_resume_from_checkpoint`)、`sse_stream.py:90-153`(`_try_resume_task`)
- **问题**:两条重启恢复路径构建的 `config` 只含 `thread_id/checkpoint_ns/event_emitter/llm_model/session_id`,**缺少 `llm`、`tool_registry`、`send_message_use_case`、`checkpointer_file` 等**。而 `llm_call_node.py:53` 直接 `config["configurable"]["llm"]`(KeyError)、`tool_execute_node.py:179` 直接取 `tool_registry`(KeyError)。恢复的图第一次进节点即崩溃 → 被 `except` 捕获 → task 标记 failed。此外:
  - `sse_stream.py:133` 用 `graph.ainvoke(None, config)` 恢复——对**有 pending interrupt** 的 checkpoint 应传 `Command(resume=decision)`;`None` 会重新从 checkpoint 继续执行而非给出决策,语义错误;
  - `sse_stream.py:99-149` 的 `_run()` 闭包持有 `task_repo`,而 `task_repo` 绑定在 `async with AsyncSessionLocal() as db:`(第 99 行)内,`_try_resume_task` 返回时 session 已关闭,后台 `_run` 再 `task_repo.update` 必然失败(异常被 `except: pass` 吞掉,状态永不落库)。
- **为什么是问题**:「重启后恢复」特性实际不可用,且失败被静默吞掉。
- **修复方向**:恢复前用 `resume_meta.json`(send_message.py:158 已写)重建完整 config(复用 `AgentLoopContext.build_all` 的依赖构建);恢复必须用 `Command(resume=...)`;`_run` 内自建 DB session(在任务内 `async with AsyncSessionLocal()`)。需运行验证。

### H3. SSE 重连对 RUNNING 任务重复启动后台恢复 → 同一任务并发执行
- **位置**:`sse_stream.py:62, 90-150`
- **问题**:`_try_resume_task` 在**每次** SSE 连接建立时执行,只要 `task.status == "running"` 且 `checkpointer.json` 存在就 `asyncio.create_task(_run())`。而 `checkpointer.json` 由 `save_checkpoint_node` 在**每轮 llm_call 前**写入(workflow_builder.py:74-75),即正常运行中文件始终存在。后果:
  - 运行中断线重连 → 同 task 出现第二个并发循环:LLM 重复调用、工具重复执行、事件交错;
  - **确认等待期间**(status 仍是 RUNNING,见 `agent_loop_lifecycle.py:132-135`)客户端重连 → `ainvoke(None)` 与 pending interrupt 冲突 → 大概率把任务标记 failed;
  - 多个 FileBackedSaver 实例并发写同一 `checkpointer.json`(`file_backed_saver.py:122` 非原子写)存在文件损坏竞态。
- **修复方向**:加防重入标记(如 `task_dir/.resuming` 文件或 `app.state.resuming_tasks` 集合);仅当任务处于 PAUSED/中断态才允许恢复;恢复进程内对 task 加 per-task `asyncio.Lock`。需运行验证。

### H4. 紧急压缩恢复成功后,残留 `error` 字段导致任务误标 FAILED
- **位置**:`error_handlers/context_limit.py:31-37` + `llm_call_node.py:192-221` + `task_completion_service.py:202`
- **问题**:`ContextLimitErrorHandler` 第一次超限返回 `{"error": str(error), "should_end": False, "emergency_compact_requested": True}` → 走紧急压缩 → 再次 llm_call 成功。但 `llm_call_node` 的返回 dict **不含 `error` 键**(不重置),`context_compact`、`tool_execute` 同样不触碰 `error`,于是 `state.error` 永久残留。最终 `finalize` 中 `task.status = FAILED if error else COMPLETED`(task_completion_service.py:202)——**恢复成功的任务被标记为失败**。
- **修复方向**:`ContextLimitErrorHandler` 恢复分支返回 `"error": None`;或 llm_call 成功路径显式 `"error": None`。需运行验证(需构造一次超限+恢复场景)。

### H5. 取消「等待确认中」的任务无效,状态与注册表不一致
- **位置**:`application/tasks/management.py:99-129` + `agent_loop_lifecycle.py:137-158`
- **问题**:中断后任务 status 为 RUNNING 且后台 asyncio task 已结束(被 done callback 从 `running_tasks` 弹出)。`cancel()`:asyncio_task 为 None → 进入 `if task.status == PAUSED` 分支判断为 False(RUNNING)→ **直接返回 `{"cancelled": True}`**,DB 状态不更新、无 TASK_CANCELLED 事件、`ResumeContext`(`graph_resume_manager.py:36-38`)与 `PendingApprovalRegistry`(`store.py:25-42`)条目全部残留;后续用户再点批准,已"取消"的任务仍会恢复执行。
- **修复方向**:cancel 对 RUNNING 且无 asyncio_task 的任务(即中断挂起态)同样走 CANCELLED 落库 + 事件;并清理 `ResumeContext._pending`、registry。

### H6. StreamEventService 内部状态永不清理(内存泄漏)
- **位置**:`stream_event.py:31-35`(`_task_dirs/_sequences/_chunk_buffers/_locks`)、`agent_loop_lifecycle.py:109-111`、`task_completion_service.py` 全流程
- **问题**:`remove_task_dir` 只在 resume 完成回调中调用(lifecycle.py:110-111);**正常完成路径**(`handle_normal_completion` → `finalize`)从不清理。`_task_dirs`、`_sequences`、`_chunk_buffers`、`_locks` 按 task_id 只增不减;`_subscribers` 依赖客户端断开时 unsubscribe 清理。长跑服务每完成一个任务就永久多占 4 个 dict 条目。
- **修复方向**:在 `finalize`(或 `AgentLoopRunner.run` 的 finally)统一调用 `event_emitter.remove_task_dir(task.id)`,并清理 `_sequences/_locks/_chunk_buffers`;注意清理顺序须在最后一次 `emit` 之后(见 M7)。

---

## 二、中危发现

### M1. `max_turns` 预算未强制执行(死代码)
- **位置**:`base_node.py:146-155`(`_exhausted_turn_budget` 定义后无任何调用点;grep 全库无引用)
- **问题**:`current_turn >= max_turns` 从不检查,`route_after_llm`(`agent_routing.py:27-50`)也不看 turn。LLM 若持续输出 tool_calls,循环无上界(仅靠每轮 300s 超时与压缩兜底)。
- **修复方向**:在 `llm_call_node` 返回前判断 `current_turn >= max_turns` 则强制 `should_end=True`;或删除死代码并加对应测试。

### M2. DB 模式下当前用户消息在 LLM 上下文重复
- **位置**:`send_message.py:176-184` + `history_loader.py:89-93`
- **问题**:无 `file_storage` 时 `user_msg` 直接 `message_repo.add` 入库;随后 `history_loader.load` 的 `list_by_session`(`sqlite_session_message_repo.py:63-74`,无状态过滤)已包含刚保存的用户消息,又在 :92 `messages.append(HumanMessage(content))` **再追加一次** → LLM 收到重复用户输入。文件存储模式下用户消息延迟写入(不重复),两模式行为不一致。
- **修复方向**:追加前按 `content == 最后一条 user 消息` 去重,或 DB 模式不追加。需运行验证(取决于部署是否启用 file_storage)。

### M3. 进程重启后事件 seq 从 0 重计,与已落盘序号冲突 → 新事件丢失
- **位置**:`stream_event.py:33, 98-99` + `sse_stream.py:42, 56-73`
- **问题**:`_sequences` 是内存 defaultdict;重启后归零,而 `events.jsonl` 已有序号到 N。新事件从 1 开始:重连客户端 `last-event-id=N` 时 `get_events_after` 与生成器的 `seq > max_replayed_seq` 过滤会**全部跳过 seq ≤ N 的新事件**——恢复后的运行结果对客户端不可见(且文件里出现重复 seq)。
- **修复方向**:初始化 `_sequences[task_id]` 为 `read_events` 的最大 seq(或持久化计数器)。

### M4. 订阅推送无界队列 + 慢消费者阻塞所有订阅者
- **位置**:`stream_event.py:111-113`
- **问题**:`for queue in ...: await queue.put(...)` 在锁外逐队列串行 await;任一订阅者消费慢(或断线未及时 unsubscribe,`is_disconnected` 每 15s 才查一次)会拖慢所有订阅者与事件写入;队列无 maxsize,断线期间事件无限堆积。
- **修复方向**:`queue.put_nowait` + 满则剔除该订阅者;或 subscribe 时绑定 `task` 由 StreamEventService 主动推送。

### M5. LLM 流式 chunk 发射失败会中断整个 LLM 调用
- **位置**:`llm_call_node.py:110-124`
- **问题**:`await context.event_emitter.emit_llm_chunk(...)` / `emit_thinking_chunk(...)` 无 `try/except`;与 `tool_execute_node._emit_tool_event`(:30-41,用 `emit_safe`)不一致。事件写入(文件 I/O)或推送失败 → 异常冒泡到外层 `except` → 整轮 LLM 输出作废、触发错误处理。
- **修复方向**:改用 `emit_safe`(接口已提供,`event_emitter.py:51-62`)。

### M6. 每个请求新建后台 DB session 且从不关闭
- **位置**:`dependencies.py:250-301`(`bg_db = SAAsyncSession(async_engine)`)
- **问题**:`get_send_message_use_case` 每次调用创建独立 AsyncSession,任务生命周期持有,完成后无 `close()`。SQLite 连接池(默认 pool_size≈5)下并发消息会耗尽连接、新请求阻塞。
- **修复方向**:runner 完成/异常后关闭 session(在 `SendMessageUseCase` 增加 `close()` 或 context manager,路由/生命周期调用)。

### M7. resume 完成后重复 TASK_COMPLETED,且第二个事件不落盘
- **位置**:`agent_loop_lifecycle.py:94-119`
- **问题**:`_on_resume_complete` 先调 `finalize`(内部已 emit TASK_COMPLETED,task_completion_service.py:237),随后 `remove_task_dir`(:110-111)再 `emit(TASK_COMPLETED)`(:112-115)——live 订阅者收到**两个** TASK_COMPLETED;第二个事件在 task_dir 移除后发射,`_save_event` 静默跳过(`stream_event.py:53-58`),重连客户端 replay 只看到第一个。此外 remove_task_dir 顺序也影响 M6 的清理时机。
- **修复方向**:删除冗余的第二个 emit;`remove_task_dir` 放到所有 emit 之后。

### M8. `save_checkpoint_node` 序列化的是进程单例 checkpointer,而非图绑定实例
- **位置**:`save_checkpoint_node.py:45`(直接 `_default_checkpointer()`)+ `workflow_builder.py:30-35, 80-106`
- **问题**:`build_with_checkpointer(FileBackedSaver(...))` 编译的图里,该节点仍然 dump **全局单例 MemorySaver** 的状态。当前因恢复路径 config 无 `checkpointer_file` 而恰好 no-op(未写出错误数据),但这是脆弱的巧合;若未来恢复路径补上该键,会把单例(可能含其他任务)状态写到错误文件。
- **修复方向**:从 `config["configurable"]` 或 graph 实例取当前 checkpointer(如经 `context` 传入),或恢复路径显式用 `FileBackedSaver` 自身持久化。需运行验证。

### M9. FileBackedSaver 每次写入全量序列化、非原子写
- **位置**:`file_backed_saver.py:111-124`
- **问题**:`put/aput/put_writes` 每次都 `json.dumps` 整个 storage/writes/blobs 并 `write_text` 覆盖。长对话下每轮 I/O 量 O(消息总量)累积 O(n²);写中途崩溃会留下损坏 JSON(加载时仅 log,`_load` :137-138,之后 checkpoint 丢失)。
- **修复方向**:原子写(`tmp + rename`),可选节流/增量。

### M10. 压缩按位置裁剪,不保证工具调用轮次完整性
- **位置**:`compact_utils.py:81-138`(对比 `prompt_context_impl.py:82-142` 是分组原子裁剪)
- **问题**:`micro/emergency compact` 按「保留最近 N 条」位置裁剪,`add_messages` reducer(`agent_state.py:17`)不做轮次校验。若 assistant(tool_calls) 被裁而 ToolMessage 留在窗口内(或反之),LLM API 会因「tool message 无对应 tool_call」返回 400 → 整轮失败。初始历史加载有分组保护,循环内压缩没有。
- **修复方向**:裁剪前按 `MessageGroup` 分组(复用 `PromptContextImpl.group_messages`),整组原子移除;或裁剪时对窗口边界做 tool 轮次回退。需运行验证。

---

## 三、低危发现

- **L1** `domain/agent_loop/state.py:8-14`:`AgentState` 与 `aggregates/agent/agent_state.py:17` 重复定义,前者 reducer 是 `left + right`(不处理 RemoveMessage),后者才是 `add_messages`。若任何路径误用前者,压缩失效。属死代码漂移风险,建议删除其一。
- **L2** `store.py:25-42` / `graph_resume_manager.py:36-38`:待审批注册表、会话 allow-all、ResumeContext 均无过期/取消清理(见 H5),长跑进程缓慢增长。
- **L3** 魔法数字与常量不一致:`llm_timeout_sec=300` 硬编码(`llm_call_node.py:99`)与 `TimeoutErrorHandler(timeout_sec=300)`(`agent_loop_context.py:216`)两处;`chunk_flush_size` 默认 10(`stream_event.py:28`)vs `app.py:111` 传 5。
- **L4** `send_message.py:206`:若 `event_emitter/tool_registry/loop_runner` 任一缺失,消息已保存、返回 202,但 loop 静默不启动,无任何错误信号。
- **L5** `send_message.py:190-193`:`title_generator.generate` fire-and-forget 无异常处理(未 retrieve 的异常)。
- **L6** `session_management.py:65-67`:先删消息再删 session,无事务;session 删除失败时消息已丢。
- **L7** `tool_execute_node.py:338-340`:allow_all 时 `meta.get("session_id")` 为空则 `session_store.allow` 静默不执行,用户以为"全部允许"实际只生效本次。

---

## 四、安全相关

- **S1(中)** 工具结果/LLM 输出被原样信任并注入 LLM 上下文与 DB:`tool_execute_node.py:409-416` 将 `result.output` 直接作为 ToolMessage content 回喂 LLM(工具输出提示注入面);`tool_output_limits` 仅按长度截断(`tool_output_limits.py`),无内容净化/来源标注。DB 侧 `task_completion_service.py:114-145` 同样只截断。建议至少对工具输出加来源前缀与长度上限(已有上限),并在 prompt 中声明工具输出不可信。
- **S2(低)** 所有任务/SSE/审批路由无鉴权,`task_id/session_id` 可枚举(`sse_stream.py:17`、`tasks.py:188` 等)——全局问题,超出本次 loop 范围,仅提示。

---

## 五、做得好的地方

1. `BaseNode` 模板方法统一了日志/phase 事件/异常处理,并正确**透传 GraphInterrupt**(`base_node.py:91-93`),不吞 interrupt。
2. 工具事件走 `emit_safe`(tool_execute_node.py:30-41),UI/观测失败不打断工具执行;`_emit_tool_event` 对旧接口做了兼容判断。
3. LLM 调用有 `asyncio.timeout` 超时保护(llm_call_node.py:99-101),配合错误处理器职责链,避免任务永久挂起。
4. 压缩策略采用可插拔策略模式(`strategy.py` + 4 个策略 + `CompactionResult.to_state_update`),带事件上报与 token baseline 失效处理,测试覆盖 4 条策略路径。
5. 事件服务用 per-task 锁 + chunk 缓冲 + 文件回放(补发)设计合理;单元测试覆盖了 flush 时机与非 chunk 事件冲刷缓冲。
6. 状态读写通过分组访问器(`state_groups.py`)收敛字段,`FileBackedSaver` 有完整的 save→load→resume round-trip 测试,`checkpoint_serializer` 与 resume_meta 设计意图清晰。
7. 生命周期 4 分支(正常/中断/取消/失败)拆分为独立服务并有针对性测试,取消/失败分支对 null repo/emitter 做了防御。

---

## 六、总体结论(5 行内)

Agent Loop 主路径(LLM→工具→循环)结构清晰、分层到位,但**中断/恢复与重启恢复两条链路的正确性隐患最集中**:确认中断导致整批工具重复执行(H1)、重启恢复配置残缺必失败(H2)、SSE 重连可并发恢复同一任务(H3),这三者直接威胁工具副作用与状态一致性,建议优先修复。其次,error 残留误标失败(H4)、取消挂起任务无效(H5)、事件服务内存泄漏(H6)属高频触发。其余为资源生命周期、seq 持久化与压缩轮次完整性等中低危问题,测试对 interrupt/resume 真实图执行(e2e)基本空白,以上 H1/H2/H3/H4 均建议补「真实 LangGraph + checkpointer」的集成测试验证。
