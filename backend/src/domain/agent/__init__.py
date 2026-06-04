"""Agent 配置子域 - Agent 配置管理"""

from src.domain.agent.entity import Agent, CONFIG_FILES, MAX_CONFIG_LENGTH, MAX_VIBES_COUNT
from src.domain.agent.repository import IAgentRepository

__all__ = [
    "Agent",
    "CONFIG_FILES",
    "MAX_CONFIG_LENGTH",
    "MAX_VIBES_COUNT",
    "IAgentRepository",
]
