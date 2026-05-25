"""领域层 - Repository 接口定义

这是 DDD 依赖倒置的核心:
- 领域层定义接口
- 基础设施层实现接口
- 应用层依赖接口,不依赖具体实现

每个聚合根有独立的仓储接口（IAgentRepository、ITaskRepository 等），
避免泛型基类带来的不必要耦合。
"""
