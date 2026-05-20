---
trigger: model_decision
description: 当进行 DDD 架构审查、重构、新增功能模块或修复架构违规时生效
---

# DDD 架构治理与实战规范

## 类型
模型决策

## 描述
基于实际项目治理经验总结的 DDD 架构规范、常见陷阱和最佳实践。包含依赖关系审计、分层职责判断、Entity-DTO 转换模式等实战指南。

## 规则内容

### 一、依赖关系审计规则

#### 1.1 依赖方向检查清单

在添加或修改代码时，**必须**检查以下依赖导入：

**领域层 (Domain) 禁止导入：**
```python
# ❌ 错误 - 领域层依赖应用层
from src.application.dtos.xxx import SomeDTO
from src.application.services.xxx import SomeService
from src.application.use_cases.xxx import SomeUseCase

# ❌ 错误 - 领域层依赖基础设施层
from src.infrastructure.repositories.xxx import SomeRepoImpl
from src.infrastructure.llm.xxx import SomeLLM
from src.infrastructure.tools.xxx import SomeTool

# ❌ 错误 - 领域层依赖表现层
from src.presentation.routes.xxx import some_router
from src.presentation.dependencies import get_something
```

**应用层 (Application) 禁止导入：**
```python
# ❌ 错误 - 应用层直接依赖基础设施层实现
from src.infrastructure.llm.model_factory import create_chat_model
from src.infrastructure.tools.registry import ToolRegistry
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node

# ✅ 正确 - 应用层依赖领域层接口
from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.repositories.agent_repository import IAgentRepository
```

**基础设施层 (Infrastructure) 禁止导入：**
```python
# ❌ 错误 - 基础设施层依赖应用层
from src.application.dtos.xxx import SomeDTO
from src.application.use_cases.xxx import SomeUseCase

# ✅ 正确 - 基础设施层依赖领域层
from src.domain.entities.xxx import SomeEntity
from src.domain.repositories.xxx import ISomeRepository
```

#### 1.2 自动化检查命令

```bash
# 检查领域层是否依赖其他层
cd backend && grep -r "from src\.\(application\|infrastructure\|presentation\)" src/domain/

# 检查应用层是否依赖基础设施层
cd backend && grep -r "from src\.infrastructure" src/application/

# 检查基础设施层是否依赖应用层
cd backend && grep -r "from src\.application" src/infrastructure/
```

### 二、分层职责判断指南

#### 2.1 领域层 (Domain) - 放什么？

**✅ 应该放在领域层：**
- 领域实体（Entity）- 业务概念的核心抽象
- Repository 接口 - 数据访问的抽象契约
- 领域服务 - 跨实体的业务规则
- 领域事件 - 业务状态变化的通知
- 值对象 - 不可变的领域概念
- 领域异常 - 业务规则违反

**❌ 不应该放在领域层：**
- DTO（数据传输对象）→ 应用层
- 数据库驱动/ORM → 基础设施层
- HTTP 框架代码 → 表现层
- 文件存储实现 → 基础设施层
- 外部 API 客户端 → 基础设施层

**判断标准：**
> 问自己：这个类是否包含业务规则？是否可能被替换的技术实现影响？
> - 如果是纯业务规则 → 领域层
> - 如果涉及技术实现 → 基础设施层

#### 2.2 应用层 (Application) - 放什么？

**✅ 应该放在应用层：**
- Use Cases - 业务流程编排
- DTOs - 数据传输对象
- Application Services - 跨用例的共享逻辑
- 实体与 DTO 的转换器（Mapper）
- 业务流程的协调逻辑

**❌ 不应该放在应用层：**
- 数据库查询实现 → 基础设施层
- LLM 调用实现 → 基础设施层
- 文件读写实现 → 基础设施层
- HTTP 请求处理 → 表现层

**判断标准：**
> 问自己：这个类是在编排业务流程，还是在实现技术细节？
> - 如果是编排流程 → 应用层
> - 如果是技术实现 → 基础设施层

#### 2.3 基础设施层 (Infrastructure) - 放什么？

**✅ 应该放在基础设施层：**
- Repository 实现 - 数据库访问的具体实现
- 外部服务客户端 - LLM、支付、邮件等
- 文件存储实现 - 本地磁盘、S3 等
- 消息队列实现
- 技术框架的集成代码

**❌ 不应该放在基础设施层：**
- 业务规则 → 领域层
- 业务流程编排 → 应用层
- DTO 定义 → 应用层

**判断标准：**
> 问自己：这个类是否依赖具体的技术框架或外部系统？
> - 如果是 → 基础设施层
> - 如果不是 → 考虑领域层或应用层

#### 2.4 表现层 (Presentation) - 放什么？

**✅ 应该放在表现层：**
- HTTP 路由定义
- 请求/响应处理
- 依赖注入配置（Composition Root）
- 中间件
- API 文档

**❌ 不应该放在表现层：**
- 业务逻辑 → 应用层
- 领域规则 → 领域层
- 数据访问 → 基础设施层

### 三、Entity-DTO 转换模式

#### 3.1 什么时候需要转换？

当 Repository 接口需要在领域层定义，但应用层需要使用 DTO 时，**必须**在应用层进行转换。

#### 3.2 转换模式实现

**步骤 1: 在领域层定义 Entity**
```python
# domain/entities/event.py
class Event:
    def __init__(self, event_type: str, payload: dict, sequence: int, task_id: str):
        self.event_type = event_type
        self.payload = payload
        self.sequence = sequence
        self.task_id = task_id
```

**步骤 2: 在领域层定义 Repository 接口**
```python
# domain/repositories/event_repository.py
from src.domain.entities.event import Event

class IEventRepository(ABC):
    @abstractmethod
    async def save(self, task_id: str, event: Event) -> None:
        pass
    
    @abstractmethod
    async def get_by_task_id(self, task_id: str) -> List[Event]:
        pass
```

**步骤 3: 在基础设施层实现 Repository**
```python
# infrastructure/repositories/sqlite_event_repo.py
from src.domain.entities.event import Event
from src.domain.repositories.event_repository import IEventRepository

class SQLiteEventRepository(IEventRepository):
    async def save(self, task_id: str, event: Event) -> None:
        # 将 Entity 转换为数据库模型
        model = EventModel(
            task_id=task_id,
            event_type=event.event_type,
            payload=event.payload,
            sequence=event.sequence,
        )
        self.session.add(model)
        await self.session.commit()
    
    async def get_by_task_id(self, task_id: str) -> List[Event]:
        # 将数据库模型转换为 Entity
        models = await self.session.execute(...)
        return [self._to_entity(m) for m in models]
    
    def _to_entity(self, model: EventModel) -> Event:
        return Event(
            event_type=model.event_type,
            payload=model.payload,
            sequence=model.sequence,
            task_id=model.task_id,
        )
```

**步骤 4: 在应用层创建 Mapper**
```python
# application/services/event_mapper.py
from src.domain.entities.event import Event
from src.application.dtos.event_dto import SSEEventDTO

class EventMapper:
    @staticmethod
    def to_dto(entity: Event) -> SSEEventDTO:
        return SSEEventDTO(
            id=str(entity.sequence),
            event_type=entity.event_type,
            data=entity.payload,
            timestamp=entity.timestamp.isoformat(),
        )
    
    @staticmethod
    def to_entity(dto: SSEEventDTO) -> Event:
        return Event(
            event_type=dto.event_type,
            payload=dto.data,
            sequence=int(dto.id),
            task_id=dto.data.get("taskId", ""),
        )
```

**步骤 5: 在应用层 Use Case 中使用**
```python
# application/use_cases/stream_event.py
from src.application.services.event_mapper import EventMapper

class StreamEventService:
    async def get_all_events(self, task_id: str) -> List[str]:
        async with self._event_repo_factory() as event_repo:
            # Repository 返回领域实体
            entities = await event_repo.get_by_task_id(task_id)
        
        # 在应用层转换为 DTO
        dtos = EventMapper.to_dto_list(entities)
        return [dto.model_dump_json() for dto in dtos]
```

#### 3.3 转换规则总结

| 转换方向 | 位置 | 说明 |
|---------|------|------|
| Entity → DTO | 应用层 | 用于对外输出（API 响应） |
| DTO → Entity | 应用层 | 用于接收输入（API 请求） |
| Entity → DB Model | 基础设施层 | 用于持久化 |
| DB Model → Entity | 基础设施层 | 用于读取数据 |

### 四、依赖注入最佳实践

#### 4.1 接口定义在领域层

```python
# domain/interfaces/llm_provider.py
class ILLMProvider(ABC):
    @abstractmethod
    def create_chat_model(self, model: str, temperature: float) -> ChatModel:
        pass
```

#### 4.2 实现在基础设施层

```python
# infrastructure/llm/llm_provider_impl.py
from src.domain.interfaces.llm_provider import ILLMProvider

class LLMProviderImpl(ILLMProvider):
    def create_chat_model(self, model: str, temperature: float) -> ChatModel:
        # 具体实现
        pass
```

#### 4.3 应用层依赖接口

```python
# application/use_cases/send_message.py
from src.domain.interfaces.llm_provider import ILLMProvider

class SendMessageUseCase:
    def __init__(self, llm_provider: ILLMProvider):
        self.llm_provider = llm_provider  # 依赖接口，不依赖实现
    
    async def execute(self, ...):
        llm = self.llm_provider.create_chat_model(...)
```

#### 4.4 表现层注入实现

```python
# presentation/dependencies.py
from src.domain.interfaces.llm_provider import ILLMProvider
from src.infrastructure.llm.llm_provider_impl import LLMProviderImpl

def get_llm_provider() -> ILLMProvider:
    return LLMProviderImpl()

def get_send_message_use_case(
    llm_provider: ILLMProvider = Depends(get_llm_provider),
) -> SendMessageUseCase:
    return SendMessageUseCase(llm_provider)
```

### 五、常见架构违规案例

#### 5.1 违规案例 1: 领域层使用 DTO

**问题代码：**
```python
# ❌ domain/repositories/event_repository.py
from src.application.dtos.event_dto import SSEEventDTO

class IEventRepository(ABC):
    async def save(self, task_id: str, event: SSEEventDTO) -> None:
        pass
```

**修复方案：**
```python
# ✅ domain/repositories/event_repository.py
from src.domain.entities.event import Event

class IEventRepository(ABC):
    async def save(self, task_id: str, event: Event) -> None:
        pass
```

#### 5.2 违规案例 2: 应用层直接导入基础设施

**问题代码：**
```python
# ❌ application/use_cases/send_message.py
from src.infrastructure.llm.model_factory import create_chat_model
from src.infrastructure.tools.registry import ToolRegistry

class SendMessageUseCase:
    def _build_llm(self, model: str):
        return create_chat_model(model=model)  # 直接调用基础设施
```

**修复方案：**
```python
# ✅ application/use_cases/send_message.py
from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.repositories.tool_registry import IToolRegistry

class SendMessageUseCase:
    def __init__(self, llm_provider: ILLMProvider):
        self.llm_provider = llm_provider
    
    def _build_llm(self, model: str):
        return self.llm_provider.create_chat_model(model=model)  # 通过接口调用
```

#### 5.3 违规案例 3: 基础设施层使用 DTO

**问题代码：**
```python
# ❌ infrastructure/repositories/sqlite_event_repo.py
from src.application.dtos.event_dto import SSEEventDTO

class SQLiteEventRepository(IEventRepository):
    async def get_by_task_id(self, task_id: str) -> List[SSEEventDTO]:
        return [self._to_dto(m) for m in models]
```

**修复方案：**
```python
# ✅ infrastructure/repositories/sqlite_event_repo.py
from src.domain.entities.event import Event

class SQLiteEventRepository(IEventRepository):
    async def get_by_task_id(self, task_id: str) -> List[Event]:
        return [self._to_entity(m) for m in models]
```

### 六、重构安全检查清单

在进行 DDD 架构重构时，**必须**遵循以下步骤：

#### 6.1 重构前

- [ ] 理解当前依赖关系（画出依赖图）
- [ ] 识别所有违规点（使用 grep 命令）
- [ ] 分析业务逻辑（确保不改变行为）
- [ ] 运行现有测试（确保测试通过）
- [ ] 制定重构计划（分阶段进行）

#### 6.2 重构中

- [ ] 小步重构（每次只改一个违规点）
- [ ] 保持测试通过（每步都运行测试）
- [ ] 使用搜索替换（避免手动错误）
- [ ] 记录变更（更新文档）

#### 6.3 重构后

- [ ] 运行所有测试（确保无回归）
- [ ] 运行代码检查（ruff check）
- [ ] 手动验证关键流程
- [ ] 更新架构文档
- [ ] 提交代码并写清楚 commit message

### 七、架构评分标准

使用以下标准评估项目的 DDD 合规性：

| 维度 | 5 星 ⭐⭐⭐⭐⭐ | 3 星 ⭐⭐⭐ | 1 星 ⭐ |
|------|--------------|----------|--------|
| **依赖方向** | 完全符合规则 | 有 1-2 个违规 | 多处严重违规 |
| **职责划分** | 清晰明确 | 大部分清晰 | 职责混乱 |
| **可测试性** | 易于 mock 和测试 | 部分难以测试 | 测试困难 |
| **可维护性** | 容易理解和修改 | 部分复杂 | 难以维护 |
| **可扩展性** | 容易替换实现 | 部分可扩展 | 紧耦合 |

### 八、持续治理机制

#### 8.1 代码审查要点

Pull Request 审查时检查：
- [ ] 新增的导入是否符合依赖规则？
- [ ] 新增的类是否放在正确的层？
- [ ] 是否有跨层依赖？
- [ ] 是否使用了接口而非具体实现？

#### 8.2 定期审计

建议每月执行一次架构审计：
```bash
# 运行依赖检查
cd backend && ./scripts/check-ddd-violations.sh

# 生成架构报告
cd backend && uv run pytest tests/ --arch-report
```

#### 8.3 技术债务管理

发现架构违规时：
1. 记录为技术债务（TODO/FIXME）
2. 评估影响范围和优先级
3. 制定修复计划
4. 在下个迭代中修复

### 九、实战经验总结

#### 9.1 何时应该使用接口？

**必须使用接口的场景：**
- 外部服务集成（LLM、支付、邮件等）
- 数据访问（Repository 模式）
- 文件存储（本地、S3 等可替换）
- 消息队列（不同实现可切换）

**可以不使用接口的场景：**
- 纯工具函数（无状态）
- 值对象（不可变数据）
- 简单的 DTO 转换

#### 9.2 何时应该在应用层添加 Service？

**添加 Application Service 的时机：**
- 多个 Use Case 需要共享逻辑
- 需要编排多个 Repository 操作
- 需要复杂的数据转换
- 需要跨实体的业务协调

**不应该添加的情况：**
- 只有一个 Use Case 使用
- 纯技术实现（应该在基础设施层）
- 业务规则（应该在领域层）

#### 9.3 如何判断是否过度设计？

**过度设计的信号：**
- 接口只有一个实现且不太可能替换
- 抽象层增加但没有带来灵活性
- 代码复杂度增加但可维护性下降
- 团队成员难以理解架构

**适度的设计：**
- 接口为已知的变化点提供扩展点
- 抽象层清晰地隔离了变化
- 代码复杂度换取了长期的灵活性
- 团队成员能快速理解并上手

### 十、参考资源

- [DDD Architecture Rules](ddd-architecture.md) - 基础架构规则
- [Project Conventions](project-conventions.md) - 项目通用约定
- [Python Backend Rules](python-backend.md) - Python 后端规范
- DDD_ARCHITECTURE_AUDIT.md - 项目架构审计报告

---

**创建时间**: 2026-05-10  
**基于经验**: DDD 分层治理实战（Event 实体迁移、LLM Provider 接口抽象）  
**维护者**: 项目架构团队
