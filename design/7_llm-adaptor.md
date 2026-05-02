# 7. LLM 适配器设计

> 对应 `0_outline.md` 第 2 章

## 架构概述

统一的 LLM 调用接口，封装不同大模型厂商的 API。

## 目录结构

```
infrastructure/llm/
├── config.py              — LLM 配置
├── model_factory.py       — 模型工厂
├── callback.py            — 回调处理
├── providers/
│   ├── base.py            — 基础接口
│   ├── openai_provider.py     — OpenAI 提供商
│   ├── anthropic_provider.py  — Anthropic 提供商
│   └── registry.py        — 提供商注册表
└── middleware/
    ├── retry.py             — 重试中间件
    ├── token_counter.py     — Token 计数
    └── cost_tracker.py      — 成本追踪
```

## 核心功能

| 功能 | 说明 |
|------|------|
| 模型路由 | 根据任务类型选择合适模型 |
| 调用优化 | 批量调用、缓存、流式处理 |
| 计费监控 | Token 消耗和成本统计 |
| 结构化输出 | 强制 JSON 输出 |
| 模型降级链 | 故障自动切换 |
| Prompt 缓存 | 减少重复 Token 消耗 |

## 依赖规则

- 接口定义在 `domain/`（待补充）
- 实现在 `infrastructure/llm/`
- 配置通过 `LLMSettings` 注入
