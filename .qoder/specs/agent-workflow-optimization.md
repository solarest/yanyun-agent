# Agent Workflow Loop 优化方案

## Context

当前 agent-loop 工作流存在 16 个节点（9 核心 + 7 反馈/辅助），职责分散，权责混乱。主要问题：
1. `plan_prepare_node` 和 `plan_execute_node` 作为图节点存在，但 plan 本质是工具行为，不应侵入工作流拓扑
2. `complete_check_node` 独立存在，但任务完成判断应由 `observe_node` 统一处理
3. 7 个反馈注入节点各自为政，增加图的复杂度和维护成本
4. context_compact 仅支持裁剪，缺少 LLM 压缩能力

优化目标：将 16 个节点精简为 6 个核心节点，observe 成为中枢评估节点，plan 下沉为工具。

---

## 新图拓扑

### 节点清单（6 个）

| 节点 | 职责 |
|------|------|
| `llm_call` | 调用大模型，流式输出 |
| `tool_execute` | 并行执行工具调用 |
| `observe` | **中枢评估节点** - 评估工具结果/LLM输出质量，判断继续/结束，注入反馈 |
| `loop_detect` | 稳定性构件 - 检测重复错误模式，内部处理反馈注入与升级 |
| `stuck_detect` | 稳定性构件 - 检测无进展模式，内部处理反馈注入与升级 |
| `context_compact` | 上下文压缩 - 支持裁剪与LLM摘要两种策略 |

### 被移除节点（10 个）

| 节点 | 去向 |
|------|------|
| `plan_prepare` | 逻辑并入闭包工具 `plan_execute` |
| `plan_execute` | 逻辑并入闭包工具 `plan_execute` |
| `complete_check` | 逻辑并入 `observe_node` Mode C |
| `empty_feedback` | 逻辑并入 `observe_node` Mode C1 |
| `planning_feedback` | 逻辑并入 `observe_node` Mode C4 |
| `completion_feedback` | 逻辑并入 `observe_node` Mode C2 |
| `loop_feedback` | 逻辑并入 `loop_detect_node` 内部 |
| `stuck_feedback` | 逻辑并入 `stuck_detect_node` 内部 |
| `finalize_result` | 逻辑并入 `observe_node`（设置 final_result） |
| `terminate` | 逻辑并入 `observe_node` Mode A |

### 流程图

```
主流程（happy path）：
  llm_call → tool_execute → observe → llm_call

带稳定性构件的完整流程：

  ┌──────────────────────────────────────────────┐
  │                                              │
  ▼                                              │
llm_call ──→ route_after_llm                     │
  │              │                               │
  │   ┌──────────┴──────────┐                    │
  │   │has tool_calls       │no tool_calls       │
  │   ▼                     ▼                    │
  │ loop_detect          observe ──→ route       │
  │   │                     │         │          │
  │   ├─no loop→ tool_execute         │          │
  │   │            │                  │          │
  │   │            ▼                  │          │
  │   │          observe ──→ route    │          │
  │   │            │          │       │          │
  │   │  ┌─────────┤          │       │          │
  │   │  │continue │stuck?    │       │          │
  │   │  │         ▼          │       │          │
  │   │  │   stuck_detect     │       │          │
  │   │  │      │             │       │          │
  │   │  │      ├─ok────┐     │       │          │
  │   │  │      └─end→END│    │       │          │
  │   │  │              │     │       │          │
  │   │  ├──────────────┘     │       │          │
  │   │  └───────────→llm_call┘       │          │
  │   │                               │          │
  │   ├─loop(count<2)→feedback→───────┼──────────┘
  │   ├─loop(count=2)→context_compact─┘
  │   └─loop(count≥3)→END
  │
  └──should_end→END
```

### 路由函数定义

**`route_after_llm`** — 从 7 分支简化为 3 分支：

| 优先级 | 条件 | 目标 |
|--------|------|------|
| 1 | `should_end=True` | END |
| 2 | 有 `tool_calls` | `loop_detect` |
| 3 | 其他（无tool_calls / 空响应 / 规划 / 完成声明 / 提问 / 文本） | `observe` |

核心思想：路由只做"有没有工具调用"的二元判断，所有分类和评估交给 observe。

**`route_after_loop_detect`** — loop_detect 内部处理反馈，路由只做分发：

| 条件 | 目标 |
|------|------|
| `loop_detected=False` | `tool_execute` |
| `should_end=True`（count >= 3） | END |
| `loop_detection_count == 2` | `context_compact` |
| `loop_detection_count < 2`（已内部注入反馈） | `llm_call` |

**`route_after_tool_execute`** — 移除 plan 分支：

| 条件 | 目标 |
|------|------|
| `awaiting_user_input=True` | END |
| 其他 | `observe` |

**`route_after_observe`** — 中枢路由出口：

| `route_hint` 值 | 目标 |
|-----------------|------|
| `"llm_call"` | `llm_call` |
| `"stuck_detect"` | `stuck_detect` |
| `"loop_detect"` | `loop_detect` |
| `"complete"` | END（已设置 final_result/is_complete） |
| `"terminate"` | END（已设置 error/should_end） |

**`route_after_stuck_detect`**：

| 条件 | 目标 |
|------|------|
| `should_end=True` | END |
| 其他（已内部注入反馈） | `llm_call` |

**固定边**：`context_compact` → `llm_call`

---

## observe_node 增强设计

observe 从单纯的工具结果评估器，升级为 **中枢评估节点**，通过三种模式处理所有场景。

### 模式检测逻辑（顺序匹配）

1. **Mode A: 预算耗尽** — `current_turn >= max_turns` 且有 `pending_tool_calls`
2. **Mode B: 工具结果评估** — `last_executed_tool_call_ids` 非空
3. **Mode C: LLM 输出评估** — 其余所有情况

### Mode A: 预算耗尽处理

LLM 产生了 tool_calls 但 turn 预算已耗尽，无法继续执行。

```python
return {
    "error": "Max turns exceeded, cannot execute pending tool calls",
    "should_end": True,
    "route_hint": "terminate",
    "observe_mode": "budget_exceeded",
}
```

替代原 `terminate_node`。

### Mode B: 工具结果评估（保留现有逻辑，微调）

保持现有的质量判定、错误分类、反思注入逻辑，仅做以下调整：

- `route_hint="finalize"` 改为 `route_hint="terminate"`，同时设置 `error`/`should_end`/`final_result`
- 新增：当 `route_hint="terminate"` 时，从最后有意义的消息中提取 `final_result`（吸收 `finalize_result_node` 的逻辑）

### Mode C: LLM 输出评估（新增，吸收 5 个节点）

当 LLM 返回纯文本（无 tool_calls），按优先级链评估：

```
C1: 空响应检查
  ↓ 不匹配
C2: 完成声明检查
  ↓ 不匹配
C3: 用户提问检查
  ↓ 不匹配
C4: 纯规划检查
  ↓ 不匹配
C5: 实质性文本（默认）
```

**C1: 空响应**（吸收 `empty_feedback_node`）
- 检测：text.strip() 为空
- 处理：递增 `empty_retry_count`
  - 超过重试上限或预算耗尽 → 设置 error/should_end, `route_hint="terminate"`
  - 否则 → 注入纠正 HumanMessage, `route_hint="llm_call"`

**C2: 完成声明**（吸收 `complete_check_node` + `completion_feedback_node` + `finalize_result_node`）
- 检测：调用 `rule_based_completion_check(text)`
- 处理：
  - 规则判定 True → 实质性验证（长度 >= 10，含实质性指标词）
    - 通过 → 设置 `final_result`/`is_complete`, `route_hint="complete"`
    - 未通过 → 注入"请提供更多详情"反馈, `route_hint="llm_call"`
  - 规则判定 False/None → 继续下一个检查

**C3: 用户提问**（吸收 `finalize_result_node` 的提问场景）
- 检测：末行以 `?`/`？` 结尾，或含提问指标词
- 处理：设置 `final_result=text`, `is_complete=True`, `route_hint="complete"`

**C4: 纯规划**（吸收 `planning_feedback_node`）
- 检测：匹配 `_PLANNING_INDICATORS` 关键词
- 处理：递增 `planning_retry_count`
  - 超过重试上限或预算耗尽 → 设置 error/should_end, `route_hint="terminate"`
  - 否则 → 注入行动提示 HumanMessage, `route_hint="llm_call"`

**C5: 实质性文本**（默认路径）
- 检测：以上均不匹配
- 处理：`route_hint="stuck_detect"`（交给 stuck_detect 评估是否有进展）

---

## Plan 工具化设计

### 设计原则

- Plan 是工具，不是工作流节点
- Subagent 创建也是工具操作
- 主 agent 通过 LLM 判断何时调用 plan 工具

### Plan 运行态

1. 先澄清（通过 clarify 工具），再 plan
2. Plan 下的任务交给 subagent（工具调用）执行
3. Subagent system prompt 继承自主 agent
4. Subagent 执行完毕后上报结果给主 agent

### 实现方案：闭包工具工厂

在 `send_message.py` 中新增 `_create_plan_execute_tool()` 工厂方法，返回一个 `RegisteredTool`，其 `func` 是一个闭包，捕获运行时依赖：

```python
def _create_plan_execute_tool(self) -> RegisteredTool:
    """创建闭包式 plan_execute 工具，捕获运行时依赖"""
    async def plan_execute_func(input_data, context):
        # 1. 验证输入（goal, steps, execution_order）
        # 2. 构建 Plan 结构（原 plan_prepare_node 逻辑）
        # 3. 创建 PlanExecutor(max_parallel=5)
        # 4. 执行 executor.execute_plan()（使用 self._run_sub_agent）
        # 5. 返回 ToolResult(output=summary)
        ...
    return RegisteredTool(name="plan_execute", func=plan_execute_func, ...)
```

### tool_execute_node 简化

移除 plan_tool_names 优先级逻辑（当前 130-149 行），所有工具统一通过 pipeline 执行。Plan 工具自行处理子 agent 编排，对 tool_execute_node 透明。

---

## 稳定性构件增强

### loop_detect_node 增强

吸收 `loop_feedback_node` 的反馈注入逻辑，内部处理升级策略：

| 检测次数 | 行为 |
|---------|------|
| 1 | 注入警告 HumanMessage + `route_hint` 让路由回 `llm_call` |
| 2 | 设置 `compression_strategy="summarize"` + 路由到 `context_compact` |
| >= 3 | 设置 `error`/`should_end=True` → END |

同时增加预算耗尽检查。

### stuck_detect_node 增强

吸收 `stuck_feedback_node` 的反馈注入逻辑：

| 检测次数 | 行为 |
|---------|------|
| < 3 | 按 stuck_type 注入对应反馈 HumanMessage + 路由回 `llm_call` |
| >= 3 | 设置 `error`/`should_end=True` → END |

### context_compact_node 增强

新增 LLM 摘要压缩策略：

- 读取 `compression_strategy` 状态字段
- `"trim"`（默认）：现有裁剪逻辑（保留首条 + 尾部 N 条，RemoveMessage 中间部分）
- `"summarize"`：提取待移除消息 → 调用 LLM 生成摘要 → 注入摘要 HumanMessage → RemoveMessage 原消息

---

## AgentState 变更

### 移除字段

| 字段 | 原因 |
|------|------|
| `plan` | Plan 为工具内部状态，不需要图级别 state |
| `plan_results` | 同上，结果通过工具输出 → observe 流转 |

### 新增字段

| 字段 | 类型 | 用途 |
|------|------|------|
| `observe_mode` | `Optional[str]` | 调试/日志：observe 运行的模式（tool_result/llm_output/budget_exceeded） |
| `compression_strategy` | `Optional[str]` | context_compact 使用的压缩策略（trim/summarize） |

### 修改字段

| 字段 | 变更 |
|------|------|
| `route_hint` | 扩展有效值：新增 `"stuck_detect"`, `"complete"`, `"terminate"`；`"finalize"` 改名为 `"complete"` |

---

## 文件变更清单

### 重大变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/src/application/use_cases/agent_workflow.py` | **重写** | 移除 11 个节点定义和 7 个路由函数，重写为 6 节点 + 6 路由函数。~577 行 → ~200 行 |
| `backend/src/infrastructure/agent/nodes/observe_node.py` | **重大增强** | 新增 Mode A/C，吸收 5 个节点逻辑，成为中枢评估引擎。~500 行 → ~700 行 |
| `backend/src/application/use_cases/send_message.py` | **修改** | 新增 `_create_plan_execute_tool()` 工厂方法，更新 initial_state |

### 中等变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/src/infrastructure/agent/nodes/loop_detect_node.py` | **增强** | 吸收反馈注入和升级逻辑，增加预算检查 |
| `backend/src/infrastructure/agent/nodes/stuck_detect_node.py` | **增强** | 吸收反馈注入和升级逻辑，增加预算检查 |
| `backend/src/infrastructure/agent/nodes/context_compact_node.py` | **增强** | 新增 LLM 摘要压缩策略 |
| `backend/src/infrastructure/agent/nodes/tool_execute_node.py` | **简化** | 移除 plan_tool_names 优先级逻辑 |
| `backend/src/domain/entities/agent_state.py` | **修改** | 移除 plan/plan_results，新增 observe_mode/compression_strategy |

### 删除文件

| 文件 | 说明 |
|------|------|
| `backend/src/infrastructure/agent/nodes/complete_check_node.py` | 逻辑迁移至 observe_node（`rule_based_completion_check` 函数迁移前保留） |
| `backend/src/infrastructure/agent/nodes/plan_prepare_node.py` | 逻辑迁移至闭包工具 |
| `backend/src/infrastructure/agent/nodes/plan_execute_node.py` | 逻辑迁移至闭包工具 |

### 次要变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/src/infrastructure/tools/builtin/plan.py` | **修改** | 移除静态 `plan_execute` 工具定义，保留 `plan` 工具 |
| `backend/src/application/use_cases/plan_executor.py` | **保留** | PlanExecutor 被闭包工具调用，无需修改 |
| `docs/langgraph-workflow.md` | **重写** | 更新流程图、节点描述、路由逻辑 |
| 相关测试文件 | **重写** | 路由测试需全面更新 |

---

## 实施步骤

### Phase 1: 基础准备（向后兼容）

1. 创建工具模块 `_observe_utils.py`，迁移共享函数（`_is_planning_only`, `_is_user_question`, `rule_based_completion_check` 等）
2. 增强 `observe_node.py`，新增 Mode A/C 评估逻辑（新代码路径暂不被图触发）
3. 运行现有测试验证无回归

### Phase 2: 增强稳定性构件（向后兼容）

4. 增强 `loop_detect_node`：内部注入反馈 + 升级策略 + 预算检查
5. 增强 `stuck_detect_node`：内部注入反馈 + 升级策略 + 预算检查
6. 运行现有测试验证无回归

### Phase 3: 重连图（原子操作，breaking change）

7. 重写 `agent_workflow.py`：6 节点 + 6 路由函数
8. 简化 `tool_execute_node`：移除 plan 优先级逻辑
9. 更新 `AgentState`：移除 plan 字段，新增新字段
10. 更新 `send_message.py` 的 initial_state
11. 运行完整集成测试

### Phase 4: Plan 工具化

12. 在 `send_message.py` 创建 `_create_plan_execute_tool()` 闭包工具
13. 更新 `plan.py` builtin 工具（移除 plan_execute）
14. 删除 `plan_prepare_node.py`、`plan_execute_node.py`、`complete_check_node.py`
15. 端到端测试 plan 执行

### Phase 5: 增强 context_compact

16. 增强 `context_compact_node`：新增 LLM 摘要压缩策略
17. 通过 loop 检测触发验证摘要功能

### Phase 6: 收尾

18. 重写路由测试
19. 更新 `docs/langgraph-workflow.md`
20. 清理死代码和导入

---

## 验证方案

1. **单元测试**：各节点的模式分支覆盖（observe Mode A/B/C，loop_detect 各计数，stuck_detect 各计数）
2. **路由测试**：6 个路由函数的所有分支覆盖
3. **集成测试**：
   - Happy path: llm_call → tool_execute → observe → llm_call → observe(complete) → END
   - Empty response 恢复: llm_call → observe(C1) → llm_call → ...
   - Loop 检测与恢复: llm_call → loop_detect(detected) → llm_call/context_compact → ...
   - Stuck 检测与恢复: llm_call → observe(C5) → stuck_detect → llm_call → ...
   - Plan 工具执行: llm_call → tool_execute(plan_execute tool) → observe → llm_call → observe(complete) → END
   - 预算耗尽: llm_call → observe(Mode A) → END
4. **端到端测试**：启动完整 agent，执行实际任务验证全流程
