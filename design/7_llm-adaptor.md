# 7. LLM 适配器设计

> 最后更新: 2026-05-31 (对照实际代码更新)
>
> 对应 `0_outline.md` 第 2 章
>
> 实际代码路径:
> - `backend/src/domain/value_objects/llm_config.py` -- LLMConfig, LLMProvider 枚举
> - `backend/src/domain/interfaces/llm_provider.py` -- ILLMProvider 接口
> - `backend/src/domain/interfaces/llm_error_handler.py` -- ILLMErrorHandler, LLMErrorHandlerRegistry
> - `backend/src/infrastructure/llm/model_factory.py` -- create_chat_model(), _infer_provider()
> - `backend/src/infrastructure/llm/providers/registry.py` -- ProviderRegistry (单例)
> - `backend/src/infrastructure/llm/providers/base.py` -- ProviderAdapter 协议
> - `backend/src/infrastructure/llm/providers/openai_provider.py` -- OpenAICompatibleProvider
> - `backend/src/infrastructure/llm/providers/anthropic_provider.py` -- AnthropicProvider
> - `backend/src/infrastructure/llm/callback.py` -- LLMUsageCallbackHandler, LLMCallLogger
> - `backend/src/infrastructure/llm/middleware/cost_tracker.py` -- calculate_cost()
> - `backend/src/infrastructure/llm/config.py` -- LLMSettings
> - `backend/src/infrastructure/llm/llm_provider_impl.py` -- LLMProviderImpl (ILLMProvider 实现)
> - `backend/src/infrastructure/agent/error_handlers/` -- ContextLimitErrorHandler, TimeoutErrorHandler, DefaultErrorHandler

## 架构概述

统一的 LLM 调用接口，封装不同大模型厂商的 API。

## 目录结构

```
infrastructure/llm/
├── config.py              -- LLM 配置 (LLMSettings, 环境变量加载)
├── model_factory.py       -- 模型工厂 (create_chat_model, _infer_provider)
├── callback.py            -- 回调处理 (LLMUsageCallbackHandler, LLMCallLogger)
├── llm_provider_impl.py   -- ILLMProvider 接口实现
├── providers/
│   ├── base.py            -- 基础接口 (ProviderAdapter 协议)
│   ├── openai_provider.py     -- OpenAI 兼容提供商
│   ├── anthropic_provider.py  -- Anthropic 提供商
│   └── registry.py        -- 提供商注册表 (ProviderRegistry, 单例)
└── middleware/
    ├── ~~retry.py~~             -- ~~重试中间件~~ (未实现)
    ├── ~~token_counter.py~~     -- ~~Token 计数~~ (未实现，使用 count_tokens() 代替)
    └── cost_tracker.py      -- 成本追踪 (calculate_cost, MODEL_PRICING 全局表)

domain/
├── interfaces/
│   ├── llm_provider.py         -- ILLMProvider 接口 (SPI)
│   └── llm_error_handler.py    -- ILLMErrorHandler, LLMErrorHandlerRegistry
└── value_objects/
    └── llm_config.py           -- LLMConfig (frozen dataclass), LLMProvider 枚举
```

## 支持的提供商

### 适配器与底层 SDK

| 适配器 | 提供商 | 底层 SDK |
|--------|--------|----------|
| OpenAICompatibleProvider | OpenAI, Azure OpenAI, Ollama, Groq, DeepSeek, Qwen (通义千问), Zhipu (智谱) | `langchain_openai.ChatOpenAI` |
| OpenAICompatibleProvider | DeepSeek (特殊处理) | `langchain_deepseek.ChatDeepSeek` (原生 reasoning_content 提取) |
| AnthropicProvider | Anthropic (Claude) | `langchain_anthropic.ChatAnthropic` |

### 提供商支持的具体模型

**OpenAI-compatible (OpenAICompatibleProvider):**

| 提供商 | 模型名称 | SDK |
|--------|---------|-----|
| OpenAI | gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o, gpt-4o-mini | `ChatOpenAI` |
| DeepSeek | deepseek-chat, deepseek-v4-pro, deepseek-v4-flash | `ChatDeepSeek` |
| Qwen (通义千问) | qwen-turbo, qwen-plus, qwen-max | `ChatOpenAI` |
| Zhipu (智谱) | glm-4, glm-3-turbo | `ChatOpenAI` |
| Groq | llama3-70b-8192, llama3-8b-8192 (以及 mixtral 系列) | `ChatOpenAI` |
| Ollama | 用户自行部署的模型 | `ChatOpenAI` |
| Azure OpenAI | 用户配置的部署 | `ChatOpenAI` |

**Anthropic (AnthropicProvider):**

| 提供商 | 模型名称 | SDK |
|--------|---------|-----|
| Anthropic | claude-3-opus, claude-3-sonnet, claude-3-haiku, claude-3-5-sonnet | `ChatAnthropic` |

**API Base URL 映射** (OpenAICompatibleProvider):
- OpenAI: `LLMSettings.openai_api_base`
- DeepSeek: `https://api.deepseek.com/v1`
- Qwen (通义千问): `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Zhipu (智谱): `https://open.bigmodel.cn/api/paas/v4`
- Groq: `https://api.groq.com/openai/v1`
- Ollama: `{ollama_base_url}/v1`

## 核心功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 模型工厂 | **已实现** | `create_chat_model()` + `_infer_provider()` 自动推断提供商 |
| ~~模型路由~~ | **未实现** | 根据任务类型选择合适模型（无动态路由逻辑） |
| 调用优化 | 部分实现 | 流式处理，~~批量调用、缓存~~ |
| 计费监控 | **已实现** | Token 消耗和成本统计 (LLMUsageCallbackHandler + calculate_cost) |
| ~~结构化输出~~ | **未实现** | 强制 JSON 输出 (API 级别 `json_schema` 参数未使用) |
| ~~模型降级链~~ | **未实现** | 故障自动切换 |
| ~~Prompt 缓存~~ | **未实现** | 减少重复 Token 消耗 (CACHE BOUNDARY 标记存在于 Prompt Builder，但无实际缓存存储) |

## 详细定价表

代码中存在三处定价表，注意它们并不完全一致：

### 1. OPENAI_COMPATIBLE_PRICING (openai_provider.py:15-35)

用于 `OpenAICompatibleProvider.get_model_pricing()`，包含所有 OpenAI-compatible 模型定价（每 1K tokens，美元）:

| 模型 | 输入价格 | 输出价格 |
|------|---------|---------|
| gpt-4 | $0.03 | $0.06 |
| gpt-4-turbo | $0.01 | $0.03 |
| gpt-3.5-turbo | $0.0005 | $0.0015 |
| gpt-4o | $0.005 | $0.015 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| deepseek-chat | $0.00014 | $0.00028 |
| deepseek-v4-pro | $0.000435 | $0.00087 |
| deepseek-v4-flash | $0.00014 | $0.00028 |
| qwen-turbo | $0.00028 | $0.00083 |
| qwen-plus | $0.00056 | $0.00166 |
| qwen-max | $0.0028 | $0.0083 |
| glm-4 | $0.01 | $0.01 |
| glm-3-turbo | $0.001 | $0.001 |
| llama3-70b-8192 | $0.00059 | $0.00079 |
| llama3-8b-8192 | $0.00005 | $0.00008 |

### 2. ANTHROPIC_PRICING (anthropic_provider.py:11-16)

用于 `AnthropicProvider.get_model_pricing()`（每 1K tokens，美元）:

| 模型 | 输入价格 | 输出价格 |
|------|---------|---------|
| claude-3-opus | $0.015 | $0.075 |
| claude-3-sonnet | $0.003 | $0.015 |
| claude-3-haiku | $0.00025 | $0.00125 |
| claude-3-5-sonnet | $0.003 | $0.015 |

### 3. MODEL_PRICING (cost_tracker.py:8-20)

用于全局 `calculate_cost()` 函数，**仅包含 OpenAI 和 Anthropic 模型**，缺少 DeepSeek/Qwen/Zhipu/Groq 的定价:

| 模型 | 输入价格 | 输出价格 |
|------|---------|---------|
| gpt-4 | $0.03 | $0.06 |
| gpt-4-turbo | $0.01 | $0.03 |
| gpt-3.5-turbo | $0.0005 | $0.0015 |
| gpt-4o | $0.005 | $0.015 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| claude-3-opus | $0.015 | $0.075 |
| claude-3-sonnet | $0.003 | $0.015 |
| claude-3-haiku | $0.00025 | $0.00125 |
| claude-3-5-sonnet | $0.003 | $0.015 |

**已知 Gap**: `calculate_cost()` (被 `LLMUsageCallbackHandler` 调用) 只查 `MODEL_PRICING` 全局表。DeepSeek/Qwen/Zhipu/Groq 模型的成本会因为查不到定价而返回 `0.0`，尽管 `OPENAI_COMPATIBLE_PRICING` 中已有对应定价数据。

## 关键实现细节

### 1. 模型工厂: create_chat_model() + _infer_provider()

```python
def create_chat_model(model=None, temperature=0.7, provider=None) -> BaseChatModel:
    # 1. 若未指定，使用 LLMSettings 默认值
    # 2. 若 provider 为空，调用 _infer_provider(model) 自动推断
    # 3. 构建 LLMConfig -> ProviderRegistry -> ProviderAdapter.create_model()
    # 4. 挂载回调: LLMUsageCallbackHandler + LLMCallLogger (model_factory.py:88-90)
```

### 2. _infer_provider(): 模型名到提供商的自动映射

```python
def _infer_provider(model: str) -> str:
    model_lower = model.lower()
    if "claude" in model_lower:      return "anthropic"
    if model_lower.startswith("qwen"):    return "qwen"
    if model_lower.startswith("deepseek"): return "deepseek"
    if model_lower.startswith("glm"):     return "zhipu"
    if model_lower.startswith("llama") or model_lower.startswith("mixtral"):
        return "groq"
    return "openai"  # 默认兜底
```

### 3. ProviderRegistry: 单例注册表

- 注册两个适配器: `OpenAICompatibleProvider` + `AnthropicProvider`
- OpenAICompatibleProvider 通过 `SUPPORTED_PROVIDERS` 集合声明支持 7 种提供商
- AnthropicProvider 仅支持 `LLMProvider.ANTHROPIC`
- `get_adapter(config)` 遍历找到第一个 `supports()` 为 True 的适配器

### 4. LLMUsageCallbackHandler: Token 计数与成本追踪

- 通过 LangChain `on_llm_end` 回调提取 `token_usage`
- 累计 `total_prompt_tokens`, `total_completion_tokens`, `total_cost`
- 调用 `calculate_cost()` 计算成本（注意：该函数使用 `MODEL_PRICING` 全局表，缺少 DeepSeek/Qwen/Zhipu/Groq 定价）
- **已知 Gap**: 数据仅在回调实例内存中累积，未被任何外部模块读取或持久化。领域实体 `CostTracker` (frozen dataclass) 存在且提供 `add_tokens()` 方法，但 `LLMUsageCallbackHandler` 并未使用它，也未将数据回写到 Task 聚合根。

### 5. LLMCallLogger: 完整调用日志

- `on_chat_model_start`: 记录 [LLM-REQUEST] 完整入参 (invocation_params + messages + tools)
- `on_llm_end`: 记录 [LLM-RESPONSE] 出参 (generations + tool_calls + usage)
- `on_llm_error`: 记录 [LLM-ERROR] 错误信息
- 通过 `config.metadata` 携带 agent_id/task_id/turn 等业务上下文
- 日志记录到独立的 `llm.call` logger

### 6. LLMProviderImpl: ILLMProvider 接口实现

```python
class LLMProviderImpl(ILLMProvider):
    """委托给 infrastructure/llm/model_factory.py 的 create_chat_model()"""
    def create_chat_model(self, model=None, temperature=0.7, provider=None) -> BaseChatModel:
        return _create_chat_model(model=model, temperature=temperature, provider=provider)
```

纯委托模式，将领域层 SPI 接口桥接到基础设施层的工厂函数。

### 7. LLMErrorHandlerRegistry: 职责链模式错误处理

位于 `domain/interfaces/llm_error_handler.py`:

```python
class LLMErrorHandlerRegistry:
    """按注册顺序遍历 handlers，第一个 can_handle() 为 True 的 handler 处理错误"""
    def handle(self, error, state, context):
        for handler in self._handlers:
            if handler.can_handle(error):
                return handler.handle(error, state, context)
        raise error  # 都不匹配时 re-raise
```

已实现的 handler (位于 `infrastructure/agent/error_handlers/`):
- `context_limit.py` -- `ContextLimitErrorHandler`: 处理上下文超限错误
- `timeout.py` -- `TimeoutErrorHandler`: 处理超时错误
- `default_handler.py` -- `DefaultErrorHandler`: 兜底 handler (re-raise 给 BaseNode._handle_error)

### 8. LLMConfig: 领域值对象

```python
class LLMProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    ZHIPU = "zhipu"

@dataclass(frozen=True)
class LLMConfig:
    provider: LLMProvider
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: int = 60
    max_retries: int = 3
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    enable_thinking: bool = False      # 深度思考模式
    thinking_budget: Optional[int] = None  # 思考 token 预算
    extra: dict[str, Any] = field(default_factory=dict)
```

### 9. LLMSettings: 全局配置 (Pydantic BaseSettings)

从环境变量或 `.env` 文件加载，关键默认值：

| 配置项 | 环境变量 | 默认值 |
|--------|---------|--------|
| default_provider | `LLM_DEFAULT_PROVIDER` | `"openai"` |
| default_model | `LLM_DEFAULT_MODEL` | `"gpt-4"` |
| default_temperature | `LLM_DEFAULT_TEMPERATURE` | `0.7` |
| default_timeout | `LLM_DEFAULT_TIMEOUT` | `60` (秒) |
| default_max_retries | `LLM_DEFAULT_MAX_RETRIES` | `3` |
| default_max_tokens | `LLM_DEFAULT_MAX_TOKENS` | `100000` |
| default_enable_thinking | `LLM_ENABLE_THINKING` | `False` |
| default_thinking_budget | `LLM_DEFAULT_THINKING_BUDGET` | `4000` |
| openai_api_key | `OPENAI_API_KEY` | `None` (SecretStr) |
| openai_api_base | `OPENAI_API_BASE` | `None` |
| anthropic_api_key | `ANTHROPIC_API_KEY` | `None` (SecretStr) |
| ollama_base_url | `OLLAMA_BASE_URL` | `"http://localhost:11434"` |
| groq_api_key | `GROQ_API_KEY` | `None` (SecretStr) |
| deepseek_api_key | `DEEPSEEK_API_KEY` | `None` (SecretStr) |
| dashscope_api_key | `DASHSCOPE_API_KEY` | `None` (SecretStr) |
| zhipu_api_key | `ZHIPU_API_KEY` | `None` (SecretStr) |

**注意**: `default_max_tokens=100000`，这是一个非常高的默认值，适用于大多数现代模型的上下文窗口。关闭了 `populate_by_name=True`，允许同时通过字段名和环境变量别名访问。`extra="ignore"` 忽略未定义的环境变量。

### 10. 深度思考 (Thinking) 模式

- `LLMSettings.default_enable_thinking` + `LLMSettings.default_thinking_budget`
- DeepSeek: 通过 `extra_body["thinking"] = {"type": "enabled"}` 传递
- 其他 OpenAI 兼容提供商: 通过 `extra_body["enable_thinking"] = True`，可选 `extra_body["thinking_budget"]`
- Anthropic: 当前未实现 Thinking 模式参数传递

## 已知 Gap 汇总

| Gap | 位置 | 影响 |
|-----|------|------|
| `LLMUsageCallbackHandler` 数据未消费 | `callback.py` | Token/成本数据在内存中累积，从未被外部读取、持久化或回写到 Task 聚合根 |
| `MODEL_PRICING` 缺少 DeepSeek/Qwen/Zhipu/Groq | `cost_tracker.py` | `calculate_cost()` 对这些模型返回 `0.0`，尽管 `OPENAI_COMPATIBLE_PRICING` 已有定价 |
| 三处定价表互不统一 | 多处 | `OPENAI_COMPATIBLE_PRICING`、`ANTHROPIC_PRICING`、`MODEL_PRICING` 各管各的，`calculate_cost()` 实际只参考 `MODEL_PRICING` |
| ~~模型路由~~ | — | 无动态路由逻辑，始终使用默认模型 |
| ~~模型降级链~~ | — | 无自动 failover |
| ~~Prompt 缓存~~ | — | CACHE BOUNDARY 标记存在但无实际缓存存储 |
| ~~API 级别结构化输出~~ | — | `json_schema` 参数未使用 |

## 依赖规则

- 接口定义在 `domain/`:
  - `ILLMProvider` (`domain/interfaces/llm_provider.py`)
  - `ILLMErrorHandler` + `LLMErrorHandlerRegistry` (`domain/interfaces/llm_error_handler.py`)
- 实现在 `infrastructure/llm/`
- 配置通过 `LLMSettings` 注入 (环境变量 / .env 文件)
- 错误处理实现在 `infrastructure/agent/error_handlers/`
