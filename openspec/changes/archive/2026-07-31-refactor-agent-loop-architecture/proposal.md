## Why

Agent Loop 核心模块经过多轮迭代后积累了显著的技术债务：`AgentLoopRunner` (614行) 集编排、工厂、异常处理于一身；`ContextCompactNode` (530行) 将 4 种压缩策略内嵌在单个类的方法中；`LoopDetectNode` (442行) 的循环检测→压缩升级逻辑缺乏理论支撑。这些问题导致新增策略需要改动现有类，测试难以隔离，代码阅读成本高。现在进行重构，在功能不变的前提下提升可读性和扩展性。

## What Changes

- **删除** `LoopDetectNode` 节点及相关路由（`route_after_loop_detect`）：循环检测→上下文压缩的升级策略缺乏理论支撑，且实际场景中 LLM 自主循环更应由 `max_turns` + 超时保护 + 上下文超限兜底来应对
- **重构** `ContextCompactNode` 为策略模式：将 4 种压缩策略（skip / soft_prune / micro_compact / emergency_compact）抽取为独立的 `CompactionStrategy` 子类，节点退化为薄编排层
- **拆分** `AgentLoopRunner` 为 3 个独立组件：`SystemPromptBuilder`（Prompt 组装）、`AgentLoopContext`（依赖构建与 graph config 组装）、`AgentLoopLifecycle`（异常处理与生命周期）
- **新增** `AgentState` 分组访问器（`ControlFields` / `ContextFields` / `ToolFields` / `TaskFields`）：不改 TypedDict 结构，仅提供按职责分组的读写视角，降低 32 个平铺字段的认知负荷
- **清理** AgentState 中与 `loop_detect` 耦合的废弃字段（`loop_detection_count` / `loop_detected` / `loop_type` / `stuck_detection_count` / `stuck_detected` / `empty_retry_count` / `compression_strategy`）
- **简化** `workflow_builder.py`：Graph 拓扑从 4 节点 3 条件路由 → 3 节点 2 条件路由
- **更新** `design/3_agent-loop-design.md` 设计文档以同步架构变更

## Capabilities

### New Capabilities
- `compaction-strategy`: 可插拔的上下文压缩策略框架，支持按优先级注册新策略，每策略独立测试
- `state-accessors`: AgentState 分组访问器，按职责（控制流/上下文/工具/任务）提供结构化读写接口

### Modified Capabilities
<!-- 本次为纯架构重构，不改变任何现有 spec 级行为 -->

## Impact

**受影响的文件**：
- `backend/src/infrastructure/agent/nodes/loop_detect_node.py` — 删除
- `backend/src/infrastructure/agent/nodes/context_compact_node.py` — 重写为薄编排
- `backend/src/infrastructure/agent/nodes/compaction/` — 新增目录 (6 文件)
- `backend/src/infrastructure/agent/workflow_builder.py` — 简化拓扑
- `backend/src/domain/agent_loop/agent_routing.py` — 删除 `route_after_loop_detect`
- `backend/src/domain/services/agent_routing.py` — 删除 re-export
- `backend/src/domain/aggregates/agent/agent_state.py` — 删除 7 个废弃字段
- `backend/src/domain/aggregates/agent/state_groups.py` — 新增分组 dataclass
- `backend/src/application/services/agent_loop_runner.py` — 重写为薄编排 (~80行)
- `backend/src/application/services/agent_loop_context.py` — 新增依赖构建
- `backend/src/application/services/agent_loop_lifecycle.py` — 新增生命周期管理
- `backend/src/application/services/system_prompt_builder.py` — 新增
- `backend/src/application/services/history_loader.py` — 新增
- `backend/src/infrastructure/agent/nodes/llm_call_node.py` — 删除 loop 相关字段引用
- `backend/src/infrastructure/agent/graph_resume_manager.py` — 可能受 state 字段变更影响
- `design/3_agent-loop-design.md` — 更新设计文档

**破坏性变更**：无。所有改动为内部重构，不改变外部 API 和行为。
