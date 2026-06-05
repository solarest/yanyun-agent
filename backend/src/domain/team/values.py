"""领域层 - Team 值对象（枚举类型）"""

from enum import Enum


class TeamStatus(str, Enum):
    """团队执行状态"""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class TeamRole(str, Enum):
    """团队成员角色"""
    LEADER = "leader"
    MEMBER = "member"


class MessageType(str, Enum):
    """团队消息类型"""
    TASK_ASSIGN = "task_assign"    # Leader → Member: 指派任务
    TASK_REPORT = "task_report"    # Member → Leader: 上报结果
    TASK_UPDATE = "task_update"    # Leader: 更新任务列表
    SHUTDOWN = "shutdown"          # Leader → Member: 优雅关闭
    ACK = "ack"                    # 确认消息
