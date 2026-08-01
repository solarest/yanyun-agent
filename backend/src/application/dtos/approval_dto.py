"""应用层 - 命令确认决策 DTO"""

from pydantic import BaseModel, Field

from src.infrastructure.tools.confirmation.contract import ApprovalDecision


class ApprovalDecisionDTO(BaseModel):
    """`POST /api/tasks/{task_id}/approvals` 请求体。"""

    toolCallId: str = Field(..., description="待确认的工具调用 ID")
    decision: ApprovalDecision = Field(
        ..., description="用户决策：allow_once | allow_all | deny"
    )
