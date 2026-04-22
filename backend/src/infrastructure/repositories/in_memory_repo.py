"""基础设施层 - 内存 Repository 实现

这是一个简单的内存存储实现,用于演示:
1. 如何实现领域层定义的 Repository 接口
2. 依赖倒置原则(基础设施依赖领域接口)
"""

from typing import Optional, List
from src.domain.entities.base import Entity
from src.domain.repositories.base import Repository


class InMemoryRepository(Repository[Entity]):
    """内存中的 Repository 实现

    数据存储在字典中,适用于:
    - 演示 DDD 架构
    - 单元测试
    - 快速原型开发
    """

    def __init__(self):
        self._storage: dict[str, Entity] = {}

    def get_by_id(self, entity_id: str) -> Optional[Entity]:
        return self._storage.get(entity_id)

    def add(self, entity: Entity) -> None:
        self._storage[entity.id] = entity

    def remove(self, entity_id: str) -> bool:
        if entity_id in self._storage:
            del self._storage[entity_id]
            return True
        return False

    def list_all(self) -> List[Entity]:
        return list(self._storage.values())
