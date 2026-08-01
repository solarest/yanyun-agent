## Context

`AgentLoopRunner` 经过多轮迭代成为 614 行的"上帝编排器"：Prompt 组装、LLM 创建、工具注册表构建、event emitter 构建、历史加载、graph 执行、4 种异常分支全部集中在一个类中。`ContextCompactNode` (530行) 将 4 种压缩策略以私有方法形式内嵌，新增策略需要修改现有类。`LoopDetectNode` (442行) 的"检测→压缩"升级链缺乏理论支撑——模型陷入循环时压缩上下文并不能解决根本问题，且实际场景中 `max_turns` + 超时保护 + `ContextLimitErrorHandler` 已构成充分兜底。

本次重构目标：在**零行为变更**的前提下，通过策略模式、职责拆分、状态分组提升可读性和扩展性，同时删除 `LoopDetectNode` 简化 topology。

## Goals / Non-Goals

**Goals:**
- 将 4 种压缩策略从 `ContextCompactNode` 中解耦为可独立测试的策略类
- 将 `AgentLoopRunner` 拆分为依赖构建、编排、生命周期管理 3 个独立职责
- 提供 `AgentState` 分组访问器，降低 32 个平铺字段的认知负荷
- 删除 `LoopDetectNode` 及其相关路由、state 字段
- 每个新文件职责单一，便于测试和扩展

**Non-Goals:**
- 不改变压缩策略的行为逻辑（soft-prune 的裁剪规则、micro/emergency 的 keep_recent 数量均不变）
- 不改变 LLM 调用、工具执行、人在回路中断/恢复的行为
- 不引入新的外部依赖
- 不改变外部 API

## Decisions

### D1: 压缩策略 → ABC 抽象基类 + priority 排序

**选择**: 每个策略实现 `CompactionStrategy` ABC，声明 `priority: int`，`ContextCompactNode` 按优先级降序遍历策略链。

```python
class CompactionStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def priority(self) -> int: ...  # 3=Emergency > 2=Micro > 1=SoftPrune > 0=Skip
    
    @abstractmethod
    def should_apply(self, state, messages, current_tokens, max_tokens) -> bool: ...
    
    @abstractmethod
    async def apply(self, state, messages, config, context) -> CompactionResult: ...
```

**备选方案**：
- ABC → 更传统的 OOP 方式，显式接口契约，`isinstance` 检查友好
- Protocol → 更轻量但依赖 mypy 做静态检查，运行时无保障

**选择 ABC 的理由**：策略需要 `async apply()` 方法，ABC 提供 `@abstractmethod` 运行时检查；且 abc 是标准库，零额外依赖。

### D2: LoopDetectNode — 直接删除而非替换

**选择**: 删除整个节点及相关的 `route_after_loop_detect` 路由函数。

**理由**:
1. "检测到循环 → 压缩上下文"的升级逻辑缺乏理论支撑：模型陷入循环不是因为上下文太长，而是推理方向错误。压缩上下文不能解决方向性错误。
2. 压缩上下文本身是一个昂贵的操作（LLM 摘要调用），用在循环纠正上性价比极低。
3. 现有兜底机制已经充分：`max_turns` (默认100轮) 硬限制 + 300s 超时保护 + `ContextLimitErrorHandler` 上下文超限兜底。
4. 删除 442 行代码 + 简化 topology 的收益远大于保留。

**影响**: Graph 从 4 节点 3 条件路由 → 3 节点 2 条件路由。`route_after_llm` 中 tool_calls 直接路由到 `tool_execute`，不再经过 loop_detect。

### D3: AgentLoopRunner 拆分为 3 组件

**选择**: 拆分为 `AgentLoopContext`（依赖构建）、`AgentLoopLifecycle`（异常处理）、`AgentLoopRunner`（薄编排）。

```
AgentLoopRunner.run()
  │
  ├── AgentLoopContext.build_all(params) → (graph, config, initial_state)
  │     ├── SystemPromptBuilder.build(...) → str
  │     └── HistoryLoader.load(...) → list[BaseMessage]
  │
  ├── graph.ainvoke(initial_state, config)
  │
  └── AgentLoopLifecycle.handle_*(task, ...)
```

**备选方案**：
- 拆为 5 个组件（SystemPromptBuilder / HistoryLoader / LLMFactory / ConfigBuilder / Lifecycle）→ 粒度过细，文件数过多
- 保持一个大类 → 不改，否决

**选择 3 组件的理由**：`AgentLoopContext` 封装"运行前需要准备的一切"，`AgentLoopLifecycle` 封装"运行后需要处理的一切"，Runner 只做编排。这是自然的职责边界。

`SystemPromptBuilder` 和 `HistoryLoader` 放在 `AgentLoopContext` 内部作为组合子组件，而非顶层独立类——它们不直接被外部调用，不需要暴露为独立接口。

### D4: AgentState 分组 — 只读视角，不改 TypedDict

**选择**: 保持 `AgentState` TypedDict 结构不变，新增 4 个 dataclass 作为分组读写辅助。

```python
@dataclass
class ControlFields:
    """由 llm_call, tool_execute 写入"""
    current_turn: int; max_turns: int; phase: str
    should_end: bool; is_complete: bool
    
    @classmethod
    def from_state(cls, state: AgentState) -> "ControlFields": ...
    def to_update(self) -> dict: ...

@dataclass
class ContextFields:
    """由 context_compact, llm_call 写入"""
    max_tokens: int; estimate: int; baseline: int | None
    baseline_count: int; compaction_attempts: int
    emergency_requested: bool; last_strategy: str | None
    # ... from_state(), to_update()

@dataclass
class ToolFields: ...
@dataclass
class TaskFields: ...  # task_id, workspace, user_message, model, is_sub_agent, parent_task_id
```

**备选方案**：
- 嵌套 TypedDict（如 `AgentState.control.current_turn`）→ LangGraph 需要额外的 reducer 逻辑来处理嵌套字段的合并，复杂度显著增加
- 不做任何分组 → 32 个平铺字段继续平铺，不改

**选择分组 dataclass 的理由**：零 LangGraph 侵入，纯 Python dataclass。`from_state()` 做读，`to_update()` 做写。每个节点只 import 自己关心的分组即可。

### D5: AgentState 字段清理

删除与 `loop_detect` 耦合的字段：

| 删除字段 | 原因 |
|---------|------|
| `loop_detection_count` | loop_detect 节点删除 |
| `loop_detected` | 同上 |
| `loop_type` | 同上 |
| `stuck_detection_count` | 从未实际使用 |
| `stuck_detected` | 从未实际使用 |
| `empty_retry_count` | 仅 loop_detect 全局纠正预算使用 |
| `compression_strategy` | loop_detect 设置 summarize 触发压缩；现由 `emergency_compact_requested` 替代 |

### D6: 文件组织结构

```
infrastructure/agent/
  nodes/
    context_compact_node.py       # 薄编排 (~80行)
    compaction/                    # ★ 新增
      __init__.py                  # _default_strategies() 工厂
      strategy.py                  # CompactionStrategy ABC + CompactionResult
      skip.py                      # SkipStrategy (priority=0)
      soft_prune.py                # SoftPruneStrategy (priority=1)
      micro_compact.py             # MicroCompactStrategy (priority=2)
      emergency_compact.py         # EmergencyCompactStrategy (priority=3)
      summary_generator.py         # LLM 摘要生成器 (原 _generate_summary)
      compact_utils.py             # compact_messages() 共享函数 (原 _do_compact)

application/services/
  agent_loop_runner.py             # 薄编排 (~80行)
  agent_loop_context.py            # AgentLoopContext + 子组件
  agent_loop_lifecycle.py          # AgentLoopLifecycle

domain/aggregates/agent/
  state_groups.py                  # ControlFields / ContextFields / ToolFields / TaskFields
```

## Risks / Trade-offs

**Risk 1: 删除 LoopDetectNode 后模型可能更容易陷入无效循环**
- 缓解：`max_turns` 硬限制 + 300s 超时保护 + `ContextLimitErrorHandler` 三层兜底。且 loop_detect 的"压缩纠正"策略本身效果存疑。

**Risk 2: 策略模式的抽象开销**
- 缓解：策略对象在 `ContextCompactNode.__init__` 时创建一次，后续每轮 ReAct 复用，无运行时反射开销。每个策略类 30-80 行，代码量可控。

**Risk 3: AgentLoopContext 依赖注入复杂度**
- 缓解：`AgentLoopContext` 接收与当前 `AgentLoopRunner.__init__` 相同的依赖，`build_all()` 方法封装所有构建步骤，调用方只需传业务参数。

**Trade-off: 文件数 vs 单一职责**
- 新增约 12 个文件，每个 30-150 行。权衡：文件数增加 但 每个文件的认知负荷大幅下降。新开发者只需关注自己关心的策略文件，无需通读 530 行的 `ContextCompactNode`。

## Open Questions

1. `state_groups.py` 中的分组 dataclass 需要暴露 `to_update()` 方法——是否需要同时提供 `merge_update(base_dict)` 方法用于合并到现有 state dict？（当前设计只有等量覆盖的 `to_update()`）

2. `compact_utils.py` 中的 `compact_messages()` 共享函数——当前 `_do_compact` 对 micro 和 emergency 返回相同结构但有微小差异（`emergency_compact` 额外写入 `context_compaction_attempts` 和清零标志）。是否在 `CompactionResult` 上用可选字段承载这些差异？

3. 是否有现有的单元测试覆盖 `loop_detect_node`？需要确认测试一并清理。
