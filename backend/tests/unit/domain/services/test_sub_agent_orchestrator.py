"""单元测试 - SubAgentOrchestrator 领域服务"""

import pytest
from src.domain.services.sub_agent_orchestrator import (
    SubAgentOrchestrator,
    SUB_AGENT_EXCLUDED_TOOLS,
)
from src.infrastructure.tools.registry import ToolRegistry
from src.infrastructure.tools.decorator import tool, clear_collected_tools
from src.domain.entities.tool import ToolContext, ToolResult


@pytest.fixture(autouse=True)
def clear_tools():
    """每个测试前后清空工具收集器"""
    clear_collected_tools()
    yield
    clear_collected_tools()


class TestSubAgentOrchestrator:
    """SubAgentOrchestrator 测试"""

    def setup_method(self):
        self.orchestrator = SubAgentOrchestrator()

    def test_excluded_tools_constant(self):
        """验证排除工具常量"""
        assert "session_spawn" in SUB_AGENT_EXCLUDED_TOOLS
        assert "task_create" in SUB_AGENT_EXCLUDED_TOOLS
        assert "task_update" in SUB_AGENT_EXCLUDED_TOOLS
        assert len(SUB_AGENT_EXCLUDED_TOOLS) == 3

    def test_build_sub_agent_system_prompt(self):
        """测试构建 sub-agent system prompt"""
        parent_prompt = "You are a helpful assistant."
        description = "Analyze this data file."

        result = self.orchestrator.build_sub_agent_system_prompt(
            parent_prompt, description
        )

        assert parent_prompt in result
        assert description in result
        assert "Sub-Agent Task Instructions" in result
        assert "You are a sub-agent spawned by the main agent" in result
        assert "Your Task" in result

    def test_build_sub_agent_initial_state(self):
        """测试构建 sub-agent 初始状态"""
        state = self.orchestrator.build_sub_agent_initial_state(
            system_prompt="Test prompt",
            user_message="Test user message",
            description="Test description",
            task_id="sub-123",
            workspace="/tmp/workspace",
            parent_task_id="parent-456",
            max_turns=30,
        )

        assert state["task_id"] == "sub-123"
        assert state["workspace"] == "/tmp/workspace"
        # user_message 在 sub-agent 视角是任务描述
        assert state["user_message"] == "Test description"
        assert state["is_sub_agent"] is True
        assert state["parent_task_id"] == "parent-456"
        assert state["max_turns"] == 30
        assert state["system_prompt"] == "Test prompt"
        assert state["current_turn"] == 0
        assert state["should_end"] is False
        assert len(state["messages"]) == 2  # SystemMessage + HumanMessage

    def test_build_sub_agent_initial_state_with_custom_messages(self):
        """测试使用自定义消息列表构建初始状态"""
        from langchain_core.messages import HumanMessage, SystemMessage

        custom_messages = [
            SystemMessage(content="Custom system"),
            HumanMessage(content="Custom user"),
        ]

        state = self.orchestrator.build_sub_agent_initial_state(
            system_prompt="Test prompt",
            user_message="Test",
            description="Test",
            task_id="sub-123",
            workspace="/tmp",
            parent_task_id="parent-456",
            max_turns=30,
            messages=custom_messages,
        )

        assert state["messages"] == custom_messages
        assert state["task_start_message_count"] == 2

    def test_create_sub_agent_tool_registry_default(self):
        """测试创建 sub-agent 工具注册表（默认排除）"""
        # 在测试方法内部定义工具
        @tool(name="test_tool_a", description="Test tool A", category="test")
        async def test_tool_a(query: str, context: ToolContext = None) -> ToolResult:
            return ToolResult(output="A")

        @tool(name="test_tool_b", description="Test tool B", category="test")
        async def test_tool_b(query: str, context: ToolContext = None) -> ToolResult:
            return ToolResult(output="B")

        @tool(name="session_spawn", description="Spawn sub-agent", category="session")
        async def session_spawn_test(description: str, context: ToolContext = None) -> ToolResult:
            return ToolResult(output="spawned")

        parent_registry = ToolRegistry()
        parent_registry.auto_register_collected()

        sub_registry = self.orchestrator.create_sub_agent_tool_registry(parent_registry)

        # 验证排除的工具
        assert sub_registry.resolve("session_spawn") is None

        # 验证包含的工具
        assert sub_registry.resolve("test_tool_a") is not None
        assert sub_registry.resolve("test_tool_b") is not None

    def test_create_sub_agent_tool_registry_with_allowed_tools(self):
        """测试创建 sub-agent 工具注册表（指定允许列表）"""
        @tool(name="test_tool_a", description="Test tool A", category="test")
        async def test_tool_a(query: str, context: ToolContext = None) -> ToolResult:
            return ToolResult(output="A")

        @tool(name="test_tool_b", description="Test tool B", category="test")
        async def test_tool_b(query: str, context: ToolContext = None) -> ToolResult:
            return ToolResult(output="B")

        parent_registry = ToolRegistry()
        parent_registry.auto_register_collected()

        # 只允许 test_tool_a
        sub_registry = self.orchestrator.create_sub_agent_tool_registry(
            parent_registry,
            allowed_tools=["test_tool_a"],
        )

        assert sub_registry.resolve("test_tool_a") is not None
        assert sub_registry.resolve("test_tool_b") is None

    def test_create_sub_agent_tool_registry_empty(self):
        """测试创建空的 sub-agent 工具注册表"""
        @tool(name="test_tool_a", description="Test tool A", category="test")
        async def test_tool_a(query: str, context: ToolContext = None) -> ToolResult:
            return ToolResult(output="A")

        parent_registry = ToolRegistry()
        parent_registry.auto_register_collected()

        # 允许不存在的工具
        sub_registry = self.orchestrator.create_sub_agent_tool_registry(
            parent_registry,
            allowed_tools=["nonexistent_tool"],
        )

        assert sub_registry.tool_count == 0
