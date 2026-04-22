"""应用层 - Ping Use Case

Use Case 编排业务流程,不包含具体的技术实现细节
"""

from datetime import datetime
from src.application.dtos.ping_dto import PingRequest, PingResponse
from src.domain.repositories.base import Repository
from src.domain.entities.base import Entity


class PingUseCase:
    """Ping 用例

    演示应用层如何编排领域对象和仓储
    """

    def __init__(self, repository: Repository[Entity]):
        self.repository = repository

    def execute(self, request: PingRequest) -> PingResponse:
        """执行 Ping 操作

        这是一个示例用例,展示:
        1. 接收 DTO
        2. 编排领域逻辑
        3. 返回 DTO
        """
        # 示例:查询仓储以演示依赖注入
        entities = self.repository.list_all()
        entity_count = len(entities)

        return PingResponse(
            status="ok",
            timestamp=datetime.now(),
            message=f"{request.message} - entity count: {entity_count}",
            server="ddd-python-backend",
        )
