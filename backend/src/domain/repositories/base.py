"""领域层 - Repository 接口定义

这是 DDD 依赖倒置的核心:
- 领域层定义接口
- 基础设施层实现接口
- 应用层依赖接口,不依赖具体实现
"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List
from src.domain.entities.base import Entity

T = TypeVar('T', bound=Entity)


class Repository(ABC, Generic[T]):
    """通用 Repository 接口
    
    所有具体的 Repository 实现都应该遵循此接口
    """
    
    @abstractmethod
    def get_by_id(self, entity_id: str) -> Optional[T]:
        """根据 ID 获取实体"""
        pass
    
    @abstractmethod
    def add(self, entity: T) -> None:
        """添加新实体"""
        pass
    
    @abstractmethod
    def remove(self, entity_id: str) -> bool:
        """删除实体"""
        pass
    
    @abstractmethod
    def list_all(self) -> List[T]:
        """列出所有实体"""
        pass
