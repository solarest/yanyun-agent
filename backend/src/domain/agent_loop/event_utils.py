"""领域层 - Event 工具函数"""


def normalize_event_type(event_type: str) -> str:
    """规范化事件类型为内部冒号风格。"""
    return event_type.replace("-", ":")
