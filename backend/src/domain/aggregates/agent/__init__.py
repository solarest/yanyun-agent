"""Agent 聚合 — 以 Agent 为聚合根，管理 Agent 配置和运行状态。"""

from src.domain.aggregates.agent.agent import Agent, CONFIG_FILES, MAX_CONFIG_LENGTH, MAX_VIBES_COUNT
from src.domain.aggregates.agent.agent_state import AgentState

__all__ = ["Agent", "AgentState", "CONFIG_FILES", "MAX_CONFIG_LENGTH", "MAX_VIBES_COUNT"]
