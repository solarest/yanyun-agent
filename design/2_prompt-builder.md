# 1.2 Prompt Builder 技术方案

> **一句话总结**: Prompt Builder 是纯领域层模块，负责将 Agent 7 文件静态内容与运行时动态上下文按 11 层 Schema 组装为 LLM system_message，通过条件注入机制按需装配 8 大行为准则、工具清单、技能指令等，并提供 PromptContextInterface SPI 接口管理对话历史裁剪与消息数组构建。

> 最后更新: 2026-06-07 (对照实际代码更新)
>
> 实际代码路径:
> - `backend/src/domain/agent_loop/prompt_assemble_service.py` -- PromptAssembleService (组装逻辑真实位置)
> - `backend/src/domain/services/prompt_assemble_service.py` -- Shim re-export (from agent_loop)
> - `backend/src/domain/value_objects/prompt_template.py` -- PromptTemplate (frozen dataclass)
> - `backend/src/domain/value_objects/prompt_assembly_result.py` -- PromptAssemblyResult (frozen dataclass)
> - `backend/src/domain/entities/tool/definition.py` -- ToolDef (shim re-export from domain/tools)
> - `backend/src/domain/tools/entity.py` -- ToolDef (真实定义)
> - `backend/src/domain/skills/entity.py` -- SkillDef (真实定义)
> - `backend/src/domain/entities/conversation.py` -- ConversationMessage, MessageGroup, ToolCall
> - `backend/src/domain/interfaces/prompt_context_interface.py` -- PromptContextInterface (SPI)
> - `backend/src/domain/agent_loop/token_utils.py` -- count_tokens() (真实定义)

## 1. 范围

本模块负责 Prompt 的分层构建和组装，提供纯领域层的对象定义和接口：
- Prompt 完整分层 Schema 定义（11 层结构，含缓存边界）
- 各层内容的对象定义和组装规则
- 上下文扩展接口（供 agent-loop 模块注入动态内容）

**不包含**：
- 数据库存储和 Repository 实现
- 对外 RESTful API
- Tools/Skills 的具体实现（由对应模块负责）
- 运行时上下文注入（由 agent-loop 模块负责）

## 2. 概要设计

### 2.1 设计理念

Prompt Builder 是一个**纯领域模块**，负责定义 Prompt 的完整结构和组装规则。核心职责：
1. 定义 Prompt 的分层 Schema（静态结构）
2. 提供各层内容的对象模型
3. 按规则组装完整 Prompt
4. 提供扩展接口供其他模块注入动态内容

### 2.2 Prompt 完整分层 Schema（11 层）

```text
完整 Prompt = 
  [Layer 1]   IDENTITY              静态前缀 - Agent 身份声明
  [Layer 2]   AGENTS.md             静态前缀 - 用户自定义指令
  [Layer 3]   Base SystemPrompt     静态前缀 - 用户自定义系统提示词
              ── CACHE BOUNDARY ──  缓存边界线（以上可缓存复用）
  [Layer 4]   Universal Behavior    动态 - 8 大行为准则（条件注入）
  [Layer 5]   Tooling Section       动态 - 工具清单和描述
  [Layer 6]   Workspace Section     动态 - 工作目录路径
  [Layer 7]   Memory Section        条件 - 记忆系统读写规则
  [Layer 8]   Skill Instructions    条件 - 已加载的 Skill 指令
  [Layer 9]   Environment           动态 - 平台/日期/时区
              ── STATIC SUFFIX ──   静态后缀线（以下可缓存复用）
  [Layer 10]  SOUL.md               静态后缀 - 行为灵魂文件
  [Layer 11]  USER.md / MEMORY.md   静态后缀 - 用户记忆文件
```

**缓存策略：**
- **静态前缀**（Layer 1-3）：跨请求缓存，复用率高
- **动态中间层**（Layer 4-9）：每次请求重新组装
- **静态后缀**（Layer 10-11）：与用户对话靠近，上下文注意力窗口控制好

### 2.3 分层架构

```text
┌─────────────────────────────────────────────────┐
│  agent-loop 模块（调用方）                        │
│  - 提供 Tools 定义列表                            │
│  - 提供 Skills 定义列表                           │
│  - 注入 Workspace/Environment 上下文              │
│  - 注入 Memory 上下文（如启用）                   │
│  - 管理对话历史（消息数组）                       │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  PromptContextInterface（上下文组装接口）          │
│  - build_messages()      构建 LLM API 消息数组   │
│  - truncate_history()    裁剪对话历史            │
│  - group_messages()      消息分组（裁剪原子单位）│
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  PromptAssembleService（组装服务）                │
│  - 从 PromptTemplate 读取 Agent 7 文件静态内容    │
│  - 合并 Tools/Skills 定义                        │
│  - 按条件注入 Universal Behavior                 │
│  - 按层拼接 11 层 → system_message               │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  领域实体（Domain Entities）                      │
│  - PromptTemplate（模板主体，对齐 Agent 7 文件）  │
│  - ToolDef（工具定义）                           │
│  - SkillDef（技能定义）                          │
│  - OutputSchema（输出格式）                       │
│  - ConversationMessage（对话消息）                │
│  - MessageGroup（消息组，裁剪原子单位）           │
└─────────────────────────────────────────────────┘
```

## 3. 详细设计

### 3.1 领域实体

#### 3.1.1 PromptTemplate（Prompt 模板）

> **与 Agent 定义的关系**：PromptTemplate 的字段直接对应 Agent 实体的 OpenClaw 7 文件结构
> （参见 [1_agent-design.md](./1_agent-design.md) 中的 Agent 领域实体定义）。
> 通过 `from_agent()` 工厂方法从 Agent 实体构造。
>
> **实现注记**: 实际代码中 PromptTemplate 是 `@dataclass(frozen=True)` 的**值对象**（非实体），
> 位于 `backend/src/domain/value_objects/prompt_template.py`。组装逻辑中的 `get_static_prefix()` /
> `get_static_suffix()` 已迁移为 `PromptAssembleService` 的私有方法。Token 计数统一使用
> `src.domain.services.token_utils.count_tokens()`。

**类设计：** `PromptTemplate` 是一个不可变值对象（frozen dataclass），作为 Agent 7 文件静态内容的纯数据载体。字段直接对应 Agent 实体的 7 个 OpenClaw 配置文件：

- **`identity_md`** -- Layer 1 IDENTITY：身份定义与系统边界约束
- **`agents_md`** -- Layer 2 AGENTS.md：调度规则与标准作业程序
- **`bootstrap_md`** -- Layer 3 BOOTSTRAP.md：初始化序列与核心系统提示词
- **`soul_md`** -- Layer 10 SOUL.md：响应语气、行为特征及输出格式
- **`user_md`** -- Layer 11 USER.md：用户画像数据与交互限制
- **`memory_md`** -- Layer 7 / Layer 11 MEMORY.md：记忆系统读写规则及长期记忆上下文（双用途字段）
- **`tools_md`** -- TOOLS.md：工具授权注册表及调用参数约束（注入到 Layer 4 tool_usage 准则，不直接映射到某一层）

**工厂方法：** `from_agent(agent)` 类方法是 Agent 定义域与 Prompt 构建域的唯一桥接点，从 Agent 实体提取 7 文件内容构造 PromptTemplate 实例。

**组装逻辑迁移：** 静态前缀/后缀的拼接方法（`get_static_prefix()`、`get_static_suffix()`）已迁移至 `PromptAssembleService` 的私有方法中。Token 计数统一使用 `src.domain.services.token_utils.count_tokens()`。

#### 3.1.2 ToolDef（工具定义）

**类设计：** `ToolDef` 是工具定义的领域实体，描述一个可被 Agent 调用的外部工具。包含以下核心元素：

- **`name`** / **`description`** -- 工具名称与功能描述，用于 LLM 理解何时使用
- **`parameters`** -- `ToolParameter` 列表，每个参数包含 name、type（string/number/boolean/object/array）、description、required 标记及可选枚举值
- **`returns`** -- 返回值描述
- **`category`** -- 工具分类（web_search、file、clarify、plan、mcp、custom）

**LLM 接口适配：** 提供两个关键方法：
- `to_prompt_section()` -- 生成 Layer 5 中的简短工具名称标记（如 `- web_search`），详细参数不放入 system_message
- `to_llm_schema()` -- 生成符合 OpenAI Chat Completions API 的 `tools` 参数格式，包含完整的 function 定义和 parameters JSON Schema，通过 `bind_tools()` 机制传递给 LLM

#### 3.1.3 SkillDef（技能定义）

**类设计：** `SkillDef` 是技能定义的领域实体，描述预定义的复杂任务执行流程。支持两种内容模式：

- **结构化模式：** 通过 `steps`（`SkillStep` 列表，每个步骤含 name、description、tool_name）和 `trigger_keywords` 定义
- **原文模式：** 通过 `content` 字段存储完整 SKILL.md 正文；若 content 非空，`to_prompt_section()` 直接返回原文，跳过结构化生成

**持久化字段：** `id`（主键）、`file_path`（磁盘路径）、`enabled`（启用状态）等持久化属性支持存储管理。

**Prompt 生成：** `to_prompt_section()` 方法根据内容模式选择输出策略：原文模式直接返回 content，结构化模式生成包含触发词和步骤列表的摘要段落。

#### 3.1.4 OutputSchema（输出格式）

**类设计：** `OutputSchema` 定义 LLM 输出的 JSON Schema 格式。核心字段：

- **`json_schema`** -- JSON Schema 字典，定义输出结构约束
- **`validate_schema()`** -- 校验 Schema 格式合法性（检查 type 或 $schema 字段）
- **`to_json_string()`** -- 序列化为 JSON 字符串，在 Prompt Assembly 时注入到 Output Format 层

当提供 OutputSchema 时，PromptAssembleService 在输出格式层追加 JSON Schema 描述，指导 LLM 生成符合期望结构的响应。

#### 3.1.5 ConversationMessage（对话消息）

**类设计：** `ConversationMessage` 表示对话历史中的一条消息，支持多种 LLM API 角色。核心字段：

- **`role`** -- 消息角色（system、user、assistant、tool）
- **`content`** -- 消息文本内容
- **`tool_calls`** -- `ToolCall` 列表（仅 assistant 角色使用），每个 ToolCall 含 id、name、arguments、result、status
- **`tool_call_id`** -- 关联的工具调用 ID（仅 tool 角色使用）

**API 适配：** `to_api_message()` 方法根据角色类型将领域实体转换为 LLM API 兼容的消息字典。assistant 角色的 tool_calls 字段转换为 OpenAI 格式的 `{"type": "function", "function": {...}}` 结构。这确保消息可直接用于 LLM API 调用。

**辅助实体 `ToolCall`：** 记录单次工具调用的完整生命周期，包含调用参数、返回结果、执行状态（pending/success/error）和错误信息。

#### 3.1.6 MessageGroup（消息组）

**类设计：** `MessageGroup` 是上下文裁剪的原子单位，将对话历史消息分组为逻辑单元以确保裁剪时不会拆散完整的工具调用轮次。

- **`type`** -- 分组类型：`dialogue`（一轮普通对话 [user, assistant]）或 `tool_call_round`（一个完整的工具调用轮次 [assistant(tool_calls), tool(result) x N]）
- **`messages`** -- 组内消息列表
- **`token_count`** -- 组内所有消息的 Token 总数，通过 `compute_token_count()` 计算

**设计约束：** 裁剪时若需移除某个 `assistant(tool_calls)` 消息，必须同时移除其关联的所有 `tool` 结果消息，否则 LLM API 因消息配对不完整而报错。

**工具调用轮次的消息结构**：

一个完整的工具调用轮次（`tool_call_round`）包含以下消息序列：

```text
┌─────────────────────────────────────────────┐
│ ToolCallRound（原子单位，裁剪时不可拆散）     │
├─────────────────────────────────────────────┤
│ 1. assistant 消息（带 tool_calls 字段）       │
│ 2. tool 消息 × N（每个 tool_call 一个结果）   │
└─────────────────────────────────────────────┘
```

**约束**：裁剪时若需要移除某个 `assistant(tool_calls)` 消息，必须同时移除其关联的所有 `tool` 结果消息。否则 LLM API 会因为消息配对不完整而报错。

### 3.2 领域服务 - Prompt 组装

#### 3.2.1 PromptAssemblyResult（组装结果值对象）

**类设计：** `PromptAssemblyResult` 是 `PromptAssembleService.assemble()` 的返回值（值对象），包含：

- **`system_message`** -- 11 层拼接后的系统消息文本，直接用于 `{"role": "system", "content": ...}`
- **`static_prefix_tokens`** -- Layer 1-3 的 Token 数（用于 Prompt Cache 命中标记）
- **`total_token_estimate`** -- 系统消息的总 Token 预估（不含对话历史）
- **`layers`** -- 各层元信息字典，用于调试和可观测性（如 tools_count、skills_count、memory_enabled 等）

#### 3.2.2 PromptAssembleService（组装服务）

**服务设计：** `PromptAssembleService` 是 Prompt 组装的领域服务，负责将 11 层 Prompt 组件组装为 `system_message` 字符串。纯领域逻辑，不涉及存储或外部依赖。

**核心方法 `assemble()`：** 接收 `PromptTemplate`（从 Agent 7 文件构造）、ToolDef 列表、SkillDef 列表、workspace 路径、environment 字典等参数，按 11 层结构顺序拼接：

1. **静态前缀（Layer 1-3）：** 从 template 提取 BOOTSTRAP -> IDENTITY -> AGENTS，调用 `count_tokens()` 记录前缀 Token 数
2. **Cache Boundary 标记**
3. **Layer 4 Universal Behavior：** 委托 `_build_universal_behavior()` 按条件注入 8 大行为准则
4. **Layer 5 Available Tools：** 遍历 ToolDef 列表，调用 `to_prompt_section()` 生成简短名称列表
5. **Layer 6 Workspace：** 注入工作目录路径
6. **Layer 7 Memory System：** 条件注入（仅 memory_enabled 为 True 时）
7. **Layer 8 Skill Instructions：** 委托 `_build_skill_instructions()` 生成 `<active_skills>` 标签包裹的技能指令
8. **Layer 9 Environment：** 注入平台、日期、时区等环境上下文
9. **Static Suffix 标记**
10. **静态后缀（Layer 10-11）：** 从 template 提取 SOUL -> USER -> MEMORY
11. **可选附加层：** output_schema（输出格式约束）、task（当前任务描述）

**关键设计原则：**
- `tools_md` 的授权约束仅注入到 Layer 4 tool_usage 准则末尾，Layer 5 完全由运行时 ToolDef 列表动态生成
- system_message 不包含对话历史；历史由 `PromptContextInterface` 独立管理
- 直接字符串拼接，不使用模板占位符替换机制

### 3.3 上下文组装接口 — 消息数组模式

> **设计变更说明**：从字符串占位符替换模式改为 LLM API 消息数组模式。
> system_message 由 PromptAssembleService 构建，对话历史由本接口管理，
> 最终合并为 `[{"role": "system", ...}, {"role": "user", ...}, ...]` 的消息数组。

**接口设计：** `PromptContextInterface` 是抽象基类（ABC），定义对话历史管理的 SPI 契约。负责将 system_message 和对话历史合并为 LLM API 的 messages 数组。由 agent-loop 模块实现。

**三个抽象方法：**

1. **`build_messages(system_message, history, max_tokens)`** -- 构建最终 LLM API messages 数组
   - 将 system_message 包装为 `{"role": "system", "content": ...}`
   - 计算可用 Token 预算（= max_tokens - system_message_tokens）
   - 调用 `truncate_history()` 裁剪历史
   - 将保留的 ConversationMessage 列表转换为 API 兼容的消息字典格式

2. **`truncate_history(history, available_tokens)`** -- 裁剪对话历史
   - 以 MessageGroup 为原子单位，确保不拆散工具调用轮次
   - 裁剪策略：保护最近一轮对话和最近的工具调用轮次，从较早的消息开始裁剪
   - 算法：先分组，从末尾向前累计 Token，接近预算时停止

3. **`group_messages(messages)`** -- 将消息列表分组为 MessageGroup 列表
   - dialogue 组：连续的 [user, assistant]（assistant 无 tool_calls）
   - tool_call_round 组：[assistant(有 tool_calls), tool(result) x N]
   - 单独消息形成独立组

**最终 LLM API 调用格式示例**：


### 3.4 集成示例

**集成流程设计：** agent-loop 模块调用 Prompt Builder 的完整流程分为三步：

1. **Agent -> PromptTemplate：** 通过 `PromptTemplate.from_agent(agent)` 从 Agent 实体桥接到 Prompt 构建域，复制 7 文件内容
2. **PromptTemplate -> system_message：** 通过 `PromptAssembleService.assemble(template, tools, skills, workspace, environment, ...)` 组装 11 层系统消息
3. **system_message + history -> messages：** 通过 `PromptContextInterface.build_messages(system_message, history, max_tokens)` 合并为 LLM API 兼容的消息数组

最终 messages 数组包含一个 system 角色消息（11 层内容）后跟裁剪后的对话历史，可直接传递给 LLM API（如 `llm.astream(messages)`）。

### 3.5 Prompt 分层 Schema 示例（11 层结构）

以下是基于完整 Prompt Schema 的分层示例，展示各层的结构和注入时机：

```text
┌─────────────────────────────────────────────────────────┐
│ [Layer 1]  IDENTITY           静态前缀 - Agent 身份声明     │
│ [Layer 2]  AGENTS.md          静态前缀 - 用户自定义指令     │
│ [Layer 3]  Base SystemPrompt  静态前缀 - 初始化与系统提示词 │
│            CACHE BOUNDARY ────────────────────── 缓存边界线  │
│ [Layer 4]  Universal Behavior 动态 - 8 大行为准则（条件注入）│
│            ├─ tone_and_style        (总是)                │
│            ├─ professional_objectivity (总是)             │
│            ├─ proactiveness         (总是)                │
│            ├─ task_management       (有 task_* 工具)      │
│            ├─ delegation_strategy   (有 sessions_* 工具)  │
│            ├─ tool_usage            (有可用工具+tools_md) │
│            ├─ memory_usage          (启用 Memory)         │
│            └─ skill_usage           (有已加载 Skill)      │
│ [Layer 5]  Tooling Section     动态 - 工具清单和描述         │
│ [Layer 6]  Workspace Section    动态 - 工作目录路径          │
│ [Layer 7]  Memory Section       条件 - 记忆系统读写规则      │
│ [Layer 8]  Skill Instructions  条件 - 已加载的 Skill 指令   │
│            (含 <active_skills> 标签包裹 + SKILL.md 正文)    │
│ [Layer 9]  Environment          动态 - 平台/日期/时区        │
│            STATIC SUFFIX ───────────────────── 静态后缀      │
│ [Layer 10] SOUL.md            静态后缀 - 行为灵魂文件        │
│ [Layer 11] USER.md / MEMORY.md 静态后缀 - 用户记忆文件       │
└─────────────────────────────────────────────────────────┘
```

#### Agent 7 文件到 Prompt 11 层映射

> **核心关系**：Agent 实体持有 7 个 OpenClaw 配置文件（定义域），
> PromptTemplate 通过 `from_agent()` 复制这些文件内容，
> PromptAssembleService 将其映射到 11 层 Schema 进行组装。

```text
Agent 7 文件             →  PromptTemplate 字段     →  11 层 Schema          →  注入类型
═════════════════════════════════════════════════════════════════════════════════════
identity_md  (IDENTITY)  →  identity_md             →  Layer 1 IDENTITY      →  静态前缀
agents_md    (AGENTS)    →  agents_md               →  Layer 2 AGENTS.md     →  静态前缀
bootstrap_md (BOOTSTRAP) →  bootstrap_md            →  Layer 3 BaseSysPrompt →  静态前缀
─── CACHE BOUNDARY ──────────────────────────────────────────────────────────────────
（无直接映射）             →  （无直接字段）           →  Layer 4 UnivBehavior   →  条件注入
tools_md     (TOOLS)     →  tools_md（约束部分）     →  Layer 4 tool_usage 补充→  条件注入
（运行时 ToolDef 列表）    →  assemble() tools 参数   →  Layer 5 Tooling       →  动态
（运行时注入）             →  assemble() workspace    →  Layer 6 Workspace     →  动态
memory_md    (MEMORY)    →  memory_md（读写规则）    →  Layer 7 Memory        →  条件
（运行时 SkillDef 列表）   →  assemble() skills 参数  →  Layer 8 Skills        →  条件
（运行时注入）             →  assemble() environment  →  Layer 9 Environment   →  动态
─── STATIC SUFFIX ───────────────────────────────────────────────────────────────────
soul_md      (SOUL)      →  soul_md                 →  Layer 10 SOUL.md      →  静态后缀
user_md      (USER)      →  user_md                 →  Layer 11 USER+MEMORY  →  静态后缀
memory_md    (MEMORY)    →  memory_md               →  Layer 11 USER+MEMORY  →  静态后缀
```

**分层说明：**

| 层级 | 名称 | 类型 | Agent 7 文件来源 | PromptTemplate 字段 | 注入时机 |
|------|------|------|-----------------|-------------------|---------|
| 1 | IDENTITY | 静态前缀 | `identity_md` | `identity_md` | `from_agent()` 时复制 |
| 2 | AGENTS.md | 静态前缀 | `agents_md` | `agents_md` | `from_agent()` 时复制 |
| 3 | Base SystemPrompt | 静态前缀 | `bootstrap_md` | `bootstrap_md` | `from_agent()` 时复制 |
| - | **CACHE BOUNDARY** | 边界 | - | - | 缓存边界线 |
| 4 | Universal Behavior | 条件 | `tools_md`(约束部分) | `tools_md` | `assemble()` 时条件注入 |
| 5 | Tooling Section | 动态 | - | `assemble(tools=...)` | 运行时 ToolDef 列表 |
| 6 | Workspace Section | 动态 | - | `assemble(workspace=...)` | 运行时注入 |
| 7 | Memory Section | 条件 | `memory_md` | `memory_md` | `assemble()` 时条件注入 |
| 8 | Skill Instructions | 条件 | - | `assemble(skills=...)` | 运行时 SkillDef 列表 |
| 9 | Environment | 动态 | - | `assemble(environment=...)` | 运行时注入 |
| - | **STATIC SUFFIX** | 边界 | - | - | 静态后缀线 |
| 10 | SOUL.md | 静态后缀 | `soul_md` | `soul_md` | `from_agent()` 时复制 |
| 11 | USER.md / MEMORY.md | 静态后缀 | `user_md` + `memory_md` | `user_md` + `memory_md` | `from_agent()` 时复制 |

**`tools_md` 的特殊处理**：

`tools_md`（Agent 的 TOOLS.md）是静态的工具授权声明，描述"允许使用哪些工具"及调用约束。它不直接映射到 Layer 5，而是：
1. **约束内容** → 注入到 Layer 4 的 `tool_usage` 行为准则中，作为工具使用规范的补充
2. **Layer 5** → 完全由运行时传入的 `ToolDef` 列表动态生成，与 `tools_md` 内容无关

**缓存边界说明：**

- **CACHE BOUNDARY 之上**（Layer 1-3）：静态前缀，可在多个请求间缓存复用
- **STATIC SUFFIX 之下**（Layer 10-11）：静态后缀，可在多个请求间缓存复用
- **中间部分**（Layer 4-9）：动态内容，每次请求需重新组装

**条件注入规则：**

Layer 4 Universal Behavior（8 大行为准则）采用条件注入机制，根据可用的 Tools、Skills、Memory 等动态装配。

### 规则结构设计

8 大行为准则采用类似项目规则的分层结构设计，分为两种类型：

```text
┌─────────────────────────────────────────────────┐
│           Universal Behavior                     │
├─────────────────────────────────────────────────┤
│  ┌─ Always-On Rules (3 条) ──────────────────┐  │
│  │  • tone_and_style        语气和风格        │  │
│  │  • professional_objectivity  专业客观性    │  │
│  │  • proactiveness         主动性           │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  ┌─ Conditional Rules (5 条) ─────────────────┐  │
│  │  • task_management       有 task_* 工具    │  │
│  │  • delegation_strategy   有 sessions_* 工具│  │
│  │  • tool_usage            有可用工具        │  │
│  │  • memory_usage          启用 Memory 系统  │  │
│  │  • skill_usage           有已加载 Skill    │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 8 大行为准则定义

| 序号 | 准则名称 | 类型 | 注入条件 | 依赖层 | Token 预估 |
|------|---------|------|---------|--------|-----------|
| 1 | tone_and_style | always_on | 始终注入 | 无 | ~150 |
| 2 | professional_objectivity | always_on | 始终注入 | 无 | ~120 |
| 3 | proactiveness | always_on | 始终注入 | 无 | ~130 |
| 4 | task_management | conditional | 有 `task_*` 工具 | Layer 5 | ~180 |
| 5 | delegation_strategy | conditional | 有 `sessions_*` 工具 | Layer 5 | ~200 |
| 6 | tool_usage | conditional | 有可用工具 | Layer 5 | ~160 |
| 7 | memory_usage | conditional | 启用 Memory | Layer 7 | ~140 |
| 8 | skill_usage | conditional | 有已加载 Skill | Layer 8 | ~170 |

### 条件注入决策流程

```text
开始组装 Layer 4
    │
    ├─→ [始终注入] tone_and_style
    ├─→ [始终注入] professional_objectivity
    ├─→ [始终注入] proactiveness
    │
    ├─→ 检查：是否存在 task_* 工具？
    │       ├─ 是 → 注入 task_management
    │       └─ 否 → 跳过
    │
    ├─→ 检查：是否存在 sessions_* 工具？
    │       ├─ 是 → 注入 delegation_strategy
    │       └─ 否 → 跳过
    │
    ├─→ 检查：是否存在可用工具？
    │       ├─ 是 → 注入 tool_usage
    │       └─ 否 → 跳过
    │
    ├─→ 检查：是否启用 Memory 系统？
    │       ├─ 是 → 注入 memory_usage
    │       └─ 否 → 跳过
    │
    └─→ 检查：是否有已加载 Skill？
            ├─ 是 → 注入 skill_usage
            └─ 否 → 跳过
```

### 条件注入决策表

| 场景 | 注入的准则 | 说明 |
|------|-----------|------|
| **基础场景**（无 Tools、Skills、Memory） | 1, 2, 3 | 仅注入 always_on 准则 |
| **有 Tools 无 Skills** | 1, 2, 3, 4*, 5*, 6 | *4, 5 取决于具体工具前缀 |
| **有 Skills 无 Tools** | 1, 2, 3, 8 | 包含 Skill 使用规范 |
| **有 Memory 无 Tools** | 1, 2, 3, 7 | 包含记忆使用规范 |
| **全量场景**（Tools + Skills + Memory） | 1, 2, 3, 4*, 5*, 6, 7, 8 | 所有准则按需注入 |

### 各准则设计说明

#### Always-On Rules（始终生效）

##### 1. tone_and_style（语气和风格）

**设计目的**：定义 Agent 的基础交互风格和沟通方式。

**核心规则**：
- 语言跟随：自动适配用户使用的语言
- 结论优先：先给答案再解释，提高效率
- 结构化输出：使用列表、表格等提高可读性
- 专业简洁：保持专业、友好语气，避免过度技术化

**提示词示例**：
```text
## Communication Style

- Respond in the same language as the user's input
- Maintain a professional, concise, and friendly tone
- Lead with conclusions, then provide detailed explanations
- Avoid overly technical jargon unless the user demonstrates expertise
- Use structured formatting (lists, tables, code blocks) for readability
```

---

##### 2. professional_objectivity（专业客观性）

**设计目的**：确保 Agent 提供客观、平衡、专业的建议。

**核心规则**：
- 平衡观点：不偏袒单一方案，指出优缺点
- 承认不确定性：避免编造信息
- 区分事实与建议：帮助用户判断
- 避免绝对化：使用"建议"而非"必须"

**提示词示例**：
```text
## Professional Objectivity

- Present balanced views with pros and cons of approaches
- Explicitly acknowledge uncertainty rather than guessing
- Distinguish between factual statements and recommendations
- Present multiple mainstream perspectives on contentious topics
- Avoid absolutist language ("must", "always"); use "recommend", "typically"
```

---

##### 3. proactiveness（主动性）

**设计目的**：指导 Agent 在适当时主动提供帮助和预警。

**核心规则**：
- 主动发现需求：识别用户未明确提及的相关需求
- 风险预警：主动提醒安全、性能等隐患
- 建议下一步：提供后续行动建议，但不强迫
- 边界控制：不过度推测，重大决策前确认

**提示词示例**：
```text
## Proactiveness

- Identify implicit but relevant needs and offer suggestions
- Proactively warn about potential issues (security risks, performance concerns)
- Suggest next steps without imposing them
- After task completion, ask if further assistance is needed
- Boundary: Don't over-speculate; confirm before major decisions
```

---

#### Conditional Rules（条件注入）

##### 4. task_management（任务管理）

**注入条件**：存在 `task_*` 前缀的工具（如 `task_create`、`task_update`）

**依赖层**：Layer 5 Tooling Section

**设计目的**：规范多步骤任务的跟踪和执行流程。

**核心规则**：
- 任务先行：多步骤任务先创建再执行
- 独立记录：每个子任务单独创建
- 及时更新：完成后更新状态
- 依赖管理：建立正确的任务依赖关系

**提示词示例**：
```text
## Task Management

You have access to task management tools. Follow these rules:

- Create tasks before executing multi-step workflows
- Create separate task records for each independent subtask
- Update task status promptly upon completion
- Establish correct dependencies between related tasks
- When users request progress updates, use task list tools to provide status reports
```

---

##### 5. delegation_strategy（委派策略）

**注入条件**：存在 `sessions_*` 前缀的工具（如 `sessions_create`、`sessions_run`）

**依赖层**：Layer 5 Tooling Section

**设计目的**：规范会话委派给子会话的执行策略。

**核心规则**：
- 独立可并行：委派独立、可并行的子任务
- 清晰描述：委派时提供明确的任务描述和预期输出
- 监控进度：必要时介入干预
- 防止递归：禁止在子会话中再次委派
- 简单直执行：简单任务直接执行，不委派

**提示词示例**：
```text
## Delegation Strategy

You have access to session delegation tools. Follow these rules:

- Delegate independent, parallelizable subtasks to sub-sessions
- Provide clear task descriptions and expected outputs when delegating
- Monitor delegated task progress and intervene when necessary
- Never delegate within sub-sessions (avoid infinite recursion)
- Don't delegate simple tasks (single-step, no dependencies); execute directly
```

---

##### 6. tool_usage（工具使用规范）

**注入条件**：存在任何可用工具（至少 1 个）

**依赖层**：Layer 5 Tooling Section

**设计目的**：规范工具的正确、安全、高效调用。

**核心规则**：
- 参数验证：调用前确认参数正确完整
- 错误处理：失败时分析错误并尝试修复
- 频率限制：不连续调用同一工具超过 3 次
- 危险确认：删除、覆盖等操作前确认
- 专用优先：优先使用专用工具而非通用工具

**提示词示例**：
```text
## Tool Usage Guidelines

You have access to external tools. Follow these rules:

- Verify parameters are correct and complete before calling tools
- When tool calls fail, analyze errors and attempt fixes or retries
- Don't call the same tool more than 3 times consecutively without changing parameters
- Confirm with users before dangerous operations (delete, overwrite, send)
- Prefer specialized tools over generic ones (e.g., `read_file` over `execute_command`)
```

---

##### 7. memory_usage（记忆使用规范）

**注入条件**：启用 Memory 系统

**依赖层**：Layer 7 Memory Section

**设计目的**：规范记忆系统的读写，保护用户隐私。

**核心规则**：
- 读取优先：对话开始读取相关记忆
- 重要写入：偏好、决策、待办及时写入
- 忽略临时：不存储临时性信息
- 冲突处理：当前信息优先，更新记忆
- 隐私保护：不记录敏感信息

**提示词示例**：
```text
## Memory System Usage

You have access to a memory system. Follow these rules:

- Read relevant memories at conversation start to understand user preferences and context
- Write important information (preferences, key decisions, action items) to memory promptly
- Don't store temporary or one-time information
- When memory conflicts with current context, prioritize current information and update memory
- Respect user privacy; never record sensitive information (passwords, keys, personal data)
```

---

##### 8. skill_usage（Skill 使用规范）

**注入条件**：有已加载的 Skill

**依赖层**：Layer 8 Skill Instructions

**设计目的**：规范专业技能的使用流程。

**核心规则**：
- 触发优先：匹配触发词时使用对应 Skill
- 严格执行：不跳过 Skill 定义的关键步骤
- 错误处理：按 Skill 定义的错误流程处理
- 最具体匹配：多匹配时选择最具体的 Skill
- 禁止修改：不自行修改 Skill 步骤或参数

**提示词示例**：
```text
## Skill Usage Guidelines

You have access to specialized skills. Follow these rules:

- When user requests match skill triggers, use the corresponding skill instead of handling manually
- Follow skill-defined steps strictly; don't skip critical steps
- Handle errors during skill execution according to the skill's error handling flow
- If multiple skills match, choose the most specific one
- Don't modify skill-defined steps or parameters on your own
```

---

### 实现要点

**条件注入算法设计：** `build_universal_behavior()` 的实现逻辑为：

1. 始终注入 3 条 always-on 准则（tone_and_style、professional_objectivity、proactiveness）
2. 遍历条件检查：
   - 存在 `task_*` 前缀工具 -> 注入 task_management
   - 存在 `sessions_*` 前缀工具 -> 注入 delegation_strategy
   - 存在任何可用工具 -> 注入 tool_usage（如 tools_md 非空则附加授权约束）
   - memory_enabled 为 True -> 注入 memory_usage
   - skills 列表非空 -> 注入 skill_usage
3. 各准则以 `

` 拼接为最终文本

8 大行为准则的文本内容预定义为类常量，避免运行时生成。

**实现要点**：
1. Always-On Rules 无条件加入
2. Conditional Rules 根据 AssemblyContext 中的工具/技能/记忆状态判断
3. 各准则提示词预定义为常量，避免运行时生成
4. 使用 `\n\n` 拼接多个准则

**规则内容**：

```markdown
## Proactiveness

- Identify implicit but relevant needs and offer suggestions
- Proactively warn about potential issues (security risks, performance concerns)
- Suggest next steps without imposing them
- After task completion, ask if further assistance is needed
- Boundary: Don't over-speculate; confirm before major decisions
```

**设计说明**：
- 主动发现需求：识别用户未明确提及的相关需求
- 风险预警：主动提醒安全、性能等隐患
- 边界控制：不过度推测，重大决策前确认

---

#### 4. task_management（任务管理）- conditional

**类型**：条件注入

**注入条件**：当可用工具列表中包含 `task_*` 前缀的工具时注入。

**依赖层**：Layer 5 Tooling Section

**描述**：规范 Agent 如何使用任务管理工具进行多步骤任务的跟踪和执行。

**规则内容**：

```markdown
## Task Management

You have access to task management tools. Follow these rules:

- Create tasks before executing multi-step workflows
- Create separate task records for each independent subtask
- Update task status promptly upon completion
- Establish correct dependencies between related tasks
- When users request progress updates, use task list tools to provide status reports
```

**注入判断逻辑**：
**注入条件：** 检查工具列表中是否存在名称以 `task_` 为前缀的工具。

---

#### 5. delegation_strategy（委派策略）- conditional

**类型**：条件注入

**注入条件**：当可用工具列表中包含 `sessions_*` 前缀的工具时注入。

**依赖层**：Layer 5 Tooling Section

**描述**：规范 Agent 如何将会话委派给子会话（sub-session）执行独立任务。

**规则内容**：

```markdown
## Delegation Strategy

You have access to session delegation tools. Follow these rules:

- Delegate independent, parallelizable subtasks to sub-sessions
- Provide clear task descriptions and expected outputs when delegating
- Monitor delegated task progress and intervene when necessary
- Never delegate within sub-sessions (avoid infinite recursion)
- Don't delegate simple tasks (single-step, no dependencies); execute directly
```

**注入判断逻辑**：
**注入条件：** 检查工具列表中是否存在名称以 `sessions_` 为前缀的工具。

---

#### 6. tool_usage（工具使用规范）- conditional

**类型**：条件注入

**注入条件**：当存在任何可用工具时注入（至少 1 个 ToolDef）。

**依赖层**：Layer 5 Tooling Section

**描述**：规范 Agent 如何正确、安全、高效地调用外部工具。

**规则内容**：

```markdown
## Tool Usage Guidelines

You have access to external tools. Follow these rules:

- Verify parameters are correct and complete before calling tools
- When tool calls fail, analyze errors and attempt fixes or retries
- Don't call the same tool more than 3 times consecutively without changing parameters
- Confirm with users before dangerous operations (delete, overwrite, send)
- Prefer specialized tools over generic ones (e.g., `read_file` over `execute_command`)
```

**注入判断逻辑**：
**注入条件：** 检查工具列表是否非空（存在至少一个可用工具）。

---

#### 7. memory_usage（记忆使用规范）- conditional

**类型**：条件注入

**注入条件**：当启用 Memory 系统时注入。

**依赖层**：Layer 7 Memory Section

**描述**：规范 Agent 如何读写记忆系统，保护用户隐私。

**规则内容**：

```markdown
## Memory System Usage

You have access to a memory system. Follow these rules:

- Read relevant memories at conversation start to understand user preferences and context
- Write important information (preferences, key decisions, action items) to memory promptly
- Don't store temporary or one-time information
- When memory conflicts with current context, prioritize current information and update memory
- Respect user privacy; never record sensitive information (passwords, keys, personal data)
```

**注入判断逻辑**：
**注入条件：** 检查 memory_enabled 布尔标志是否为 True。

---

#### 8. skill_usage（Skill 使用规范）- conditional

**类型**：条件注入

**注入条件**：当有已加载的 Skill 时注入。

**依赖层**：Layer 8 Skill Instructions

**描述**：规范 Agent 如何识别和使用已加载的专业技能。

**规则内容**：

```markdown
## Skill Usage Guidelines

You have access to specialized skills. Follow these rules:

- When user requests match skill triggers, use the corresponding skill instead of handling manually
- Follow skill-defined steps strictly; don't skip critical steps
- Handle errors during skill execution according to the skill's error handling flow
- If multiple skills match, choose the most specific one
- Don't modify skill-defined steps or parameters on your own
```

**注入判断逻辑**：
**注入条件：** 检查已加载的 Skill 列表是否非空。

---

### 条件注入决策表

| 场景 | 注入的准则 | 说明 |
|------|-----------|------|
| **基础场景**（无 Tools、无 Skills、无 Memory） | 1, 2, 3 | 仅注入总是生效的基础准则 |
| **有 Tools 无 Skills** | 1, 2, 3, 4*, 5*, 6 | *4, 5 取决于具体工具前缀 |
| **有 Skills 无 Tools** | 1, 2, 3, 8 | 包含 Skill 使用规范 |
| **有 Memory 无 Tools** | 1, 2, 3, 7 | 包含记忆使用规范 |
| **全量场景**（Tools + Skills + Memory） | 1, 2, 3, 4*, 5*, 6, 7, 8 | 所有准则按需注入 |

---

### 条件注入实现示例

**`_build_universal_behavior()` 方法设计：** 接收 tools 列表、skills 列表、memory_enabled 标志和 tools_md 授权约束，按以下顺序组装 8 大行为准则：

1. 始终追加 `_TONE_AND_STYLE`、`_PROFESSIONAL_OBJECTIVITY`、`_PROACTIVENESS` 常量
2. 条件注入 5 条 conditional 准则（见上述算法设计）
3. `tools_md` 非空时，在 tool_usage 准则末尾追加 "Tool Authorization Constraints" 子节

**`_build_skill_instructions()` 方法设计：** 将已加载的 Skill 列表包装在 `<active_skills>` XML 标签中，每个 Skill 以 `## {name}` 标题后跟 `to_prompt_section()` 内容。

**8 大行为准则常量：** 每条准则以 `_RULENAME` 格式定义为类级字符串常量，内容为 Markdown 格式的行为规范文本（在各准则设计说明中已展示）。

**实现注记**: 以下占位符模板示例为设计阶段的概念模型。
实际实现中，PromptAssembleService 采用直接字符串拼接方式构建 system_message，
不使用 `{{placeholder}}` 模板替换机制。保留此设计文档供架构参考。

**占位符模板示例（设计阶段，~~未实现~~）：**

```markdown
# IDENTITY

{{identity_md}}
<!-- Layer 1: IDENTITY.md Agent 身份声明 -->

# AGENTS

{{agents_md}}
<!-- Layer 2: AGENTS.md 用户自定义指令 -->

# Bootstrap

{{bootstrap_md}}
<!-- Layer 3: BOOTSTRAP.md 初始化与系统提示词 -->

── CACHE BOUNDARY ─────────────────────────────────────
<!-- 以上三层为静态前缀，可缓存复用 -->

# Universal Behavior

{{tone_and_style}}
{{professional_objectivity}}
{{proactiveness}}
{{task_management}}
<!-- 条件注入：有 task_* 工具时 -->
{{delegation_strategy}}
<!-- 条件注入：有 sessions_* 工具时 -->
{{tool_usage}}
<!-- 条件注入：有可用工具时；若 tools_md 非空，附加 Tool Authorization Constraints -->
{{memory_usage}}
<!-- 条件注入：启用 Memory 时 -->
{{skill_usage}}
<!-- 条件注入：有已加载 Skill 时 -->

# Available Tools

{{tools_section}}
<!-- Layer 5: 由运行时 ToolDef 列表动态生成（与 tools_md 无关） -->

# Workspace

Current working directory: {{workspace_path}}
<!-- Layer 6: 工作目录路径 -->

# Memory System

{{memory_md}}
<!-- Layer 7: MEMORY.md 记忆系统读写规则（memory_enabled 时注入） -->

# Active Skills

{{active_skills_section}}
<!-- Layer 8: <active_skills> 标签包裹的 Skill 指令 -->

# Environment

Platform: {{platform}}
Date: {{current_date}}
Timezone: {{timezone}}
<!-- Layer 9: 环境上下文 -->

── STATIC SUFFIX ──────────────────────────────────────
<!-- 以下两层为静态后缀，可缓存复用 -->

# SOUL

{{soul_md}}
<!-- Layer 10: SOUL.md 行为灵魂文件 -->

# USER / MEMORY

{{user_md}}
{{memory_md}}
<!-- Layer 11: USER.md + MEMORY.md 用户记忆文件 -->
```

**设计意图：**
- **三层缓存架构**：静态前缀（1-3）→ 动态中间层（4-9）→ 静态后缀（10-11）
- **条件注入**：Layer 4 的行为准则和 Layer 8 的技能指令根据工具/Skill 可用性动态注入
- **职责分离**：静态内容由 Agent 定义模块管理，动态内容由 PromptAssembleService 组装，运行时内容由 agent-loop 注入

### 3.6 完整 Prompt 示例

以下展示 `PromptAssembleService.assemble()` 的输出（`PromptAssemblyResult.system_message`）
以及 `PromptContextInterface.build_messages()` 最终构建的 messages 数组。

#### 3.6.1 system_message 内容（11 层拼接结果）

```text
# IDENTITY

You are CodeReview Assistant, a professional AI code review agent.
Version: 1.2.0
Capabilities: Code analysis, bug detection, style checking, security auditing

# AGENTS

## Custom Instructions

- Always check for OWASP Top 10 vulnerabilities
- Follow the team's Python coding standards (PEP 8 + type hints)

# Bootstrap

You are a professional code review specialist with 10+ years of experience in software engineering.

**Responsibilities:**
- Review code for bugs, security vulnerabilities, and style issues
- Provide constructive feedback with specific suggestions
- Explain the reasoning behind each recommendation

**Boundaries:**
- Do not rewrite entire files unless explicitly requested
- Focus on critical issues first, then minor improvements

── CACHE BOUNDARY ─────────────────────────────────────

# Universal Behavior

## Communication Style

- Respond in the same language as the user's input
- Maintain a professional, concise, and friendly tone
- Lead with conclusions, then provide detailed explanations
- Use structured formatting (lists, tables, code blocks) for readability

## Professional Objectivity

- Present balanced views with pros and cons of approaches
- Explicitly acknowledge uncertainty rather than guessing
- Distinguish between factual statements and recommendations

## Proactiveness

- Identify implicit but relevant needs and offer suggestions
- Proactively warn about potential issues (security risks, performance concerns)
- Boundary: Don't over-speculate; confirm before major decisions

## Tool Usage Guidelines

You have access to external tools. Follow these rules:

- Verify parameters are correct and complete before calling tools
- Confirm with users before dangerous operations (delete, overwrite, send)
- Prefer specialized tools over generic ones

### Tool Authorization Constraints

Only use read-only file operations unless explicitly authorized by the user.
Never execute shell commands that modify the filesystem.

# Available Tools

- read_file
- web_search

<!-- 实现注记: 实际代码中 Layer 5 输出简短名称列表，详细描述通过 bind_tools() 传递 -->
<!-- ~~原设计: <tools> XML 标签包裹的完整工具描述~~ -->

# Workspace

Current working directory: /Users/dev/my-project

# Active Skills

<active_skills>
## code_review
Systematic code review with multiple analysis phases.

**Triggers:** review, check code, audit

**Steps:**
1. **analyze** Analyze code structure and architecture
2. **check_security** (using `web_search`) Check for known security patterns and CVEs
3. **suggest_improvements** Provide specific improvement suggestions
</active_skills>

# Environment

Platform: darwin
Date: 2026-04-26
Timezone: Asia/Shanghai

── STATIC SUFFIX ──────────────────────────────────────

# SOUL

**Language Style:** Professional, concise, and friendly
**Personality:** Detail-oriented but pragmatic
**Interaction Preference:** Prioritize actionable feedback over theoretical discussions

# USER / MEMORY

**Preferences:**
- Preferred language: Chinese for explanations, English for code
- Code style: functional programming preferred
```

#### 3.6.2 最终 messages 数组（LLM API 请求格式）

**LLM API 调用格式说明：** `PromptContextInterface.build_messages()` 的输出是一个消息数组，格式为：

- 第一条为 `{"role": "system", "content": "<11 层 system_message 全文>"}`
- 后续为对话历史消息，按时间顺序排列
- assistant 消息的 tool_calls 字段为 `[{"id": "tc_001", "type": "function", "function": {"name": "...", "arguments": "..."}}]` 格式
- tool 消息通过 `tool_call_id` 与对应的 assistant 消息配对

工具调用轮次（`assistant(tool_calls)` + `tool(result) x N`）作为 MessageGroup 原子单位，裁剪时不可拆散。

**说明：**
- `system_message` 由 `PromptAssembleService.assemble()` 输出，作为 `{"role": "system"}` 的 content
- 对话历史由 `PromptContextInterface.build_messages()` 管理，裁剪后拼接到 system 消息之后
- 工具调用轮次（`assistant(tool_calls)` + `tool(result) × N`）作为 `MessageGroup` 原子单位，裁剪时不可拆散
- Layer 1-3（静态前缀）和 Layer 10-11（静态后缀）来自 `PromptTemplate`（通过 `from_agent()` 从 Agent 7 文件构造）
- Layer 4-9（动态中间层）由 `PromptAssembleService` 按条件组装

## 4. 测试计划

### 4.1 功能测试计划

#### 测试场景 1: 组装完整 system_message - 正常流程
- **前置条件**: 创建合法的 PromptTemplate（从 Agent 7 文件字段构造）、ToolDef、SkillDef 实例
- **测试步骤**:
  1. 创建 PromptTemplate，设置 identity_md、agents_md、bootstrap_md、soul_md、user_md
  2. 创建 2 个 ToolDef 和 1 个 SkillDef
  3. 调用 `PromptAssembleService.assemble(template, tools, skills, workspace="...", environment={...})`
  4. 检查返回的 `PromptAssemblyResult`
- **预期结果**: 
  - `result.system_message` 包含 11 层内容和缓存边界标记
  - 包含 `<tools>` 和 `</tools>` XML 标签包裹的工具定义
  - 包含 CACHE BOUNDARY 和 STATIC SUFFIX 标记
  - **不包含** `# Conversation History` 占位符（历史由 PromptContextInterface 管理）
  - `result.total_token_estimate > 0`
  - `result.static_prefix_tokens > 0`
- **验收标准**: 各层内容按 Agent 7 文件定义的顺序拼接

#### 测试场景 2: from_agent() 工厂方法 - 正常流程
- **前置条件**: 创建完整的 Agent 实体（含 7 个 OpenClaw 文件字段）
- **测试步骤**:
  1. 创建 Agent 实体，设置 identity_md、soul_md、agents_md、bootstrap_md、memory_md、tools_md、user_md
  2. 调用 `PromptTemplate.from_agent(agent)`
  3. 检查返回的 PromptTemplate
- **预期结果**: 
  - PromptTemplate 的各字段与 Agent 实体一一对应
  - `get_static_prefix()` 返回 BOOTSTRAP → IDENTITY → AGENTS 拼接结果
  - `get_static_suffix()` 返回 SOUL → USER → MEMORY 拼接结果
- **验收标准**: Agent 7 文件字段完整桥接到 PromptTemplate

#### 测试场景 3: 静态前缀/后缀组装 - 边界条件
- **前置条件**: 创建只有部分字段的 PromptTemplate
- **测试步骤**:
  1. 只设置 identity_md，其余 6 个文件字段为空
  2. 调用 `get_static_prefix()` 和 `get_static_suffix()`
- **预期结果**: 仅返回非空字段的拼接内容
- **验收标准**: 空字段不生成多余内容或分隔符

#### 测试场景 4: tools_md 特殊处理 - 条件注入
- **前置条件**: 创建含 tools_md 的 PromptTemplate 和 ToolDef 列表
- **测试步骤**:
  1. 设置 `tools_md = "Only use read-only file operations"`
  2. 提供可用工具列表 `tools=[ToolDef(name="read_file", ...)]`
  3. 调用 `assemble(template, tools=tools)`
  4. 检查 system_message 中 Layer 4 tool_usage 部分
- **预期结果**: 
  - Layer 4 Universal Behavior 中包含 "Tool Authorization Constraints"
  - tools_md 内容附加在 tool_usage 准则末尾
  - Layer 5 仍然由 ToolDef 列表动态生成，不包含 tools_md
- **验收标准**: tools_md 仅影响 Layer 4，不影响 Layer 5

#### 测试场景 5: 消息数组构建 - 多轮工具调用
- **前置条件**: 创建包含工具调用轮次的对话历史
- **测试步骤**:
  1. 构建对话历史：[user, assistant(tool_calls), tool, tool, assistant, user]
  2. 调用 `PromptContextInterface.build_messages(system_message, history, max_tokens)`
  3. 检查返回的 messages 数组
- **预期结果**: 
  - messages[0] 为 `{"role": "system", "content": system_message}`
  - 后续消息按正确顺序排列
  - 工具调用消息包含正确的 tool_calls 和 tool_call_id 配对
- **验收标准**: 输出符合 LLM API 消息数组协议

#### 测试场景 6: ToolCallRound 裁剪原子性
- **前置条件**: 创建超出 Token 预算的对话历史，含多个工具调用轮次
- **测试步骤**:
  1. 构建长对话历史（包含 3 个 tool_call_round 和 2 个 dialogue 组）
  2. 设置较小的 max_tokens 使裁剪必须发生
  3. 调用 `truncate_history(history, available_tokens)`
  4. 检查裁剪结果
- **预期结果**: 
  - 不存在孤立的 assistant(tool_calls) 消息（无对应 tool 结果）
  - 不存在孤立的 tool 消息（无对应 assistant(tool_calls)）
  - 保留最近的对话和工具调用轮次
- **验收标准**: 裁剪后的消息列表可直接用于 LLM API，无配对完整性错误

### 4.2 单元测试计划

#### 测试模块: PromptTemplate Entity

**PromptTemplate 测试策略：**

- **字段复制完整性：** 验证 `from_agent()` 工厂方法将 Agent 7 文件的全部字段正确复制到 PromptTemplate
- **静态前缀排序：** 验证 BOOTSTRAP -> IDENTITY -> AGENTS 的顺序正确
- **静态后缀排序：** 验证 SOUL -> USER -> MEMORY 的顺序正确
- **部分字段边界条件：** 验证仅设置部分字段时，空字段不产生多余内容或分隔符
- **Token 预估：** 验证非空内容的 Token 预估值大于 0

#### 测试模块: ConversationMessage Entity

**ConversationMessage 测试策略：**

- **角色映射：** 验证 user/assistant/tool 各角色的 `to_api_message()` 输出符合 LLM API 协议
- **工具调用转换：** 验证 assistant 消息的 tool_calls 正确转换为 OpenAI 格式的 `{"type": "function", "function": {...}}` 结构
- **tool_call_id 配对：** 验证 tool 角色消息正确携带 `tool_call_id` 字段

#### 测试模块: MessageGroup Entity

**MessageGroup 测试策略：**

- **dialogue 组：** 验证普通对话组（user + assistant）的 Token 计数和消息数量
- **tool_call_round 组：** 验证工具调用轮次组的原子性（assistant(tool_calls) + tool(result) 不可拆分）

#### 测试模块: PromptAssembleService

**PromptAssembleService 测试策略：**

- **完整组装流程：** 验证 `assemble()` 返回 `PromptAssemblyResult`，system_message 包含所有 11 层内容和缓存边界标记
- **tools_md 注入：** 验证 tools_md 内容注入到 Layer 4 tool_usage 的 "Tool Authorization Constraints" 子节
- **条件注入：** 验证 memory_enabled 参数正确控制 Layer 7 Memory Section 的注入（True 时包含，False 时不包含）
- **元信息：** 验证 layers 字典包含 tools_count、skills_count 等调试信息
- **不包含历史占位符：** 验证 system_message 不含对话历史相关内容

#### 测试模块: ToolDef Entity

**ToolDef 测试策略：**

- **to_prompt_section()：** 验证输出为 `- {name}` 格式的简短名称标记
- **to_llm_schema()：** 验证生成的 Schema 包含 `type: "function"`、function name、parameters properties 等完整字段

### 4.3 回归测试计划

#### 受影响的现有功能
- [ ] Agent 定义模块（1.1）: `PromptTemplate.from_agent()` 依赖 Agent 实体的 7 文件字段
- [ ] Tools 模块（1.4）: ToolDef 结构需与 Tools Hub 的工具注册格式对齐
- [ ] Skills 系统（1.4）: SkillDef 结构需与 Skills 定义对齐
- [ ] LLM 适配器模块（2）: `PromptAssemblyResult.system_message` 作为 `{"role": "system"}` 传递给 LLM
- [ ] agent-loop 模块: `PromptContextInterface` 实现需适配消息数组模式和 MessageGroup 裁剪

#### 回归测试用例
- **用例 1**: Agent 7 文件字段完整性 — 确保 from_agent() 不丢失任何字段
- **用例 2**: 消息配对完整性 — 确保裁剪后 tool_calls/tool 消息始终配对
- **用例 3**: 缓存边界正确性 — 确保 static_prefix_tokens 仅包含 Layer 1-3

#### 自动化验证
**自动化验证命令：** 使用 pytest 的 `-k` 过滤功能按模块名称筛选运行相关测试用例。

## 5. 验收标准

- [ ] 所有功能测试通过
- [ ] 所有单元测试通过
- [ ] 回归测试通过
- [ ] 测试覆盖率 ≥ 80%
- [ ] PromptTemplate 字段对齐 Agent 7 文件结构（identity_md、agents_md、bootstrap_md、soul_md、user_md、memory_md、tools_md）
- [ ] `from_agent()` 工厂方法正确桥接 Agent 实体到 PromptTemplate
- [ ] `get_static_prefix()` / `get_static_suffix()` 按正确顺序拼接
- [ ] PromptAssembleService 返回 `PromptAssemblyResult`（含 system_message 而非 full_prompt）
- [ ] system_message 不包含对话历史占位符（历史由 PromptContextInterface 管理）
- [ ] `tools_md` 仅注入到 Layer 4 tool_usage 准则，Layer 5 完全由 ToolDef 列表动态生成
- [ ] ToolDef 能正确生成为 XML 格式的工具描述
- [ ] SkillDef 能正确生成为 Prompt 段落
- [ ] ConversationMessage.to_api_message() 输出符合 LLM API 消息协议
- [ ] MessageGroup 裁剪时 ToolCallRound 原子性得到保证
- [ ] PromptContextInterface 以消息数组模式（build_messages / truncate_history / group_messages）定义清晰
- [ ] Token 预估值与实际消耗误差在合理范围内（±20%）
