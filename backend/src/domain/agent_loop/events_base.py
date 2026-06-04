"""领域事件基类 — 所有业务领域事件的抽象基类。"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class DomainEvent(ABC):
    """领域事件抽象基类

    表示领域中发生的有业务意义的状态变更。所有领域事件必须：
    - 是不可变的 (frozen=True)
    - 包含唯一标识符
    - 记录发生时间
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_on: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
