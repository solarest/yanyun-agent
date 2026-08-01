## 1. 基础设施: AgentState 分组访问器

- [x] 1.1 创建 `domain/aggregates/agent/state_groups.py`：定义 `ControlFields` / `ContextFields` / `ToolFields` / `TaskFields` 四个 dataclass，每个实现 `from_state(state) -> Self` 和 `to_update() -> dict`
- [x] 1.2 验证：在 Python REPL 中导入各组 dataclass，测试 `from_state()` 读取和 `to_update()` 写入

## 2. 基础设施: 压缩策略框架

- [x] 2.1 创建 `compaction/strategy.py`：定义 `CompactionStrategy` ABC（`name` / `priority` / `should_apply()` / `apply()`）和 `CompactionResult` dataclass（含 `to_state_update()`）
- [x] 2.2 创建 `compaction/summary_generator.py`：将 `ContextCompactNode._generate_summary()` 抽取为独立类 `SummaryGenerator`，保持原有 budget 控制逻辑 + LLM 失败降级行为不变
- [x] 2.3 创建 `compaction/compact_utils.py`：将 `ContextCompactNode._do_compact()` 抽取为独立函数 `compact_messages(messages, keep_recent, summary_budget, llm) -> CompactionResult`，保持 SystemMessage 保留 + RemoveMessage + 摘要注入逻辑不变
- [x] 2.4 创建 `compaction/skip.py`：实现 `SkipStrategy` (priority=0)，`should_apply()` 永远返回 `True`（兜底），`apply()` 不修改 messages
- [x] 2.5 创建 `compaction/soft_prune.py`：实现 `SoftPruneStrategy` (priority=1)，移植原有 `_soft_prune()` 逻辑（裁剪超长 ToolMessage，目标降到 25% 水线）
- [x] 2.6 创建 `compaction/micro_compact.py`：实现 `MicroCompactStrategy` (priority=2)，`should_apply()` 检查 `tokens > 60% * max`，`apply()` 委托 `compact_messages(keep_recent=10)`
- [x] 2.7 创建 `compaction/emergency_compact.py`：实现 `EmergencyCompactStrategy` (priority=3)，`should_apply()` 检查 `emergency_compact_requested`，`apply()` 委托 `compact_messages(keep_recent=3)` + 额外处理 `compaction_attempts` 递增和清零标志
- [x] 2.8 创建 `compaction/__init__.py`：导出所有策略类和 `_default_strategies()` 工厂函数

## 3. 重构 ContextCompactNode

- [x] 3.1 重写 `context_compact_node.py`：`execute()` 简化为遍历策略链 + 调用 `should_apply()` + `apply()` + emit event，删除原来的 4 个私有方法和 `_generate_summary` / `_do_compact`
- [x] 3.2 验证：单元级别确认策略链遍历逻辑正确（可用 mock strategy 验证优先级顺序）

## 4. 删除 LoopDetectNode

- [x] 4.1 确认 `loop_detect_node` 无外部引用（除 `workflow_builder.py` 和 `agent_routing.py` 外）
- [x] 4.2 删除 `infrastructure/agent/nodes/loop_detect_node.py` 文件
- [x] 4.3 删除 `domain/agent_loop/agent_routing.py` 中的 `route_after_loop_detect` 函数
- [x] 4.4 删除 `domain/services/agent_routing.py` 中的 re-export
- [x] 4.5 简化 `route_after_llm`：有 tool_calls 直接路由到 `"tool_execute"`（不再经过 `loop_detect`）
- [x] 4.6 清理关联的测试文件（如有）

## 5. 简化 WorkflowBuilder

- [x] 5.1 修改 `workflow_builder.py`：移除 `loop_detect` 节点注册和相关条件边，拓扑变为 3 节点（context_compact / llm_call / tool_execute）+ 2 条件路由
- [x] 5.2 更新 `workflow_builder.py` 中的 import（移除 `loop_detect_node` 和 `route_after_loop_detect`）

## 6. 清理 AgentState

- [x] 6.1 从 `agent_state.py` 中删除 7 个废弃字段：`loop_detection_count` / `loop_detected` / `loop_type` / `stuck_detection_count` / `stuck_detected` / `empty_retry_count` / `compression_strategy`
- [x] 6.2 检查所有节点文件中对上述字段的引用，一并清理
- [x] 6.3 更新 `AgentLoopRunner._build_initial_state()` 中初始 state 构建（移除删除的字段）

## 7. 拆分 AgentLoopRunner

- [x] 7.1 创建 `application/services/agent_loop_lifecycle.py`：`AgentLoopLifecycle` 类，封装 4 个异常处理分支（`handle_normal_completion` / `handle_interrupt` / `handle_cancellation` / `handle_failure`），逻辑与原 `AgentLoopRunner.run()` 中的 try/except 块完全一致
- [x] 7.2 创建 `application/services/agent_loop_context.py`：`AgentLoopContext` 类，组合 `SystemPromptBuilder` 和 `HistoryLoader` 子组件，封装 `_build_llm()` / `_build_tool_registry()` / `_build_event_emitter()` / `_build_initial_state()` / `_build_graph_config()` 工厂方法
- [x] 7.3 创建 `application/services/system_prompt_builder.py`：`SystemPromptBuilder` 类，封装 `PromptAssembleService` 调用 + sub-agent/team mode 分支（原 `_build_system_prompt()` 逻辑）
- [x] 7.4 创建 `application/services/history_loader.py`：`HistoryLoader` 类，封装 5 种模式的历史加载分支（normal / sub-agent / team-leader / team-member / fallback），原 `run()` 方法中步骤 B 的逻辑
- [x] 7.5 重写 `agent_loop_runner.py`：`run()` 方法简化为 `ctx.build_all()` → `graph.ainvoke()` → `lifecycle.handle_*()`，删除所有工厂方法和历史加载分支
- [x] 7.6 更新 `SendMessageUseCase` 中 `AgentLoopRunner` 的构造参数以匹配新的构造函数签名

## 8. 适配 llm_call_node

- [x] 8.1 检查 `llm_call_node.py` 中对 loop 相关 state 字段的引用（如 `empty_retry_count`），移除或替换
- [x] 8.2 将 `llm_call_node.py` 中的 state 字典读写改为使用 `ControlFields` / `ContextFields` / `ToolFields` 分组访问器

## 9. 适配 tool_execute_node

- [x] 9.1 将 `tool_execute_node.py` 中的 state 字典读写改为使用 `ToolFields` 分组访问器
- [x] 9.2 移除对 loop 相关字段的引用（如有）

## 10. 更新设计文档

- [x] 10.1 更新 `design/3_agent-loop-design.md`：反映新的 3 节点拓扑、策略模式架构、分组访问器、删除的 `LoopDetectNode`
- [x] 10.2 更新 `design/3_agent-loop-design.md` 中的 AgentState 字段列表

## 11. 验证与测试

- [x] 11.1 运行 `backend/.venv/bin/python -m pytest backend/tests/` 确保所有现有测试通过
- [x] 11.2 如有 `loop_detect` 相关测试，确认已清理且不影响其他测试
- [x] 11.3 手动启动 app 验证一次完整的 Agent 执行流程（发送消息 → LLM 调用 → 工具执行 → 完成）
- [x] 11.4 验证压缩策略切换：构造接近水线的上下文触发 soft_prune / micro_compact
