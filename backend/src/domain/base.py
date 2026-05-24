"""领域层 - Entity 基类"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Entity(ABC):
    """所有领域实体的抽象基类

    特性:
    - 每个实体都有唯一的 ID
    - 基于 ID 的相等性比较(而非属性值)
    """

    id: str = field(default_factory=lambda: str(uuid4()))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
