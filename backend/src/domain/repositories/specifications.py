"""领域层 - Specification 模式

封装复杂查询条件为可组合、可复用的对象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class Specification(ABC):
    """规约基类

    将查询条件封装为对象，支持通过 & / | 进行组合。
    """

    @abstractmethod
    def to_expression(self, model_class: type) -> Any:
        """转换为 ORM 查询表达式

        Args:
            model_class: 目标 ORM 模型类（由基础设施层传入）

        Returns:
            SQLAlchemy BinaryExpression 或等效过滤条件
        """
        ...

    def __and__(self, other: Specification) -> AndSpecification:
        return AndSpecification(self, other)

    def __or__(self, other: Specification) -> OrSpecification:
        return OrSpecification(self, other)


@dataclass(frozen=True)
class AndSpecification(Specification):
    """AND 组合规约"""

    left: Specification
    right: Specification

    def to_expression(self, model_class: type) -> Any:
        from sqlalchemy import and_

        return and_(
            self.left.to_expression(model_class),
            self.right.to_expression(model_class),
        )


@dataclass(frozen=True)
class OrSpecification(Specification):
    """OR 组合规约"""

    left: Specification
    right: Specification

    def to_expression(self, model_class: type) -> Any:
        from sqlalchemy import or_

        return or_(
            self.left.to_expression(model_class),
            self.right.to_expression(model_class),
        )


@dataclass(frozen=True)
class TaskStatusSpecification(Specification):
    """按任务状态查询"""

    status: Any  # TaskStatus enum

    def to_expression(self, model_class: type) -> Any:
        return model_class.status == self.status.value


@dataclass(frozen=True)
class TaskTimeRangeSpecification(Specification):
    """按时间范围查询"""

    since: datetime
    until: datetime

    def to_expression(self, model_class: type) -> Any:
        return model_class.created_at.between(self.since, self.until)
