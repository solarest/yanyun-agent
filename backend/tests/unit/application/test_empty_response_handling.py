"""测试 - 空响应处理逻辑

验证 LLM 返回空内容但有 tool_calls 时不会被误判为空响应
"""
import pytest
from src.application.use_cases.agent_workflow import (
    route_after_llm,
    empty_feedback_node,
    _extract_tool_calls,
    _extract_text,
)


def make_state(**kwargs):
    """创建测试 state 的辅助函数"""
    state = {
        "messages": [],
        "current_turn": 0,
        "max_turns": 100,
        "empty_retry_count": 0,
    }
    state.update(kwargs)
    return state


class TestExtractToolCalls:
    """测试 tool_calls 提取逻辑"""

    def test_extract_from_dict_with_tool_calls(self):
        """从 dict 消息中提取 tool_calls"""
        msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call-1", "name": "search", "args": {"q": "test"}}
            ],
        }
        result = _extract_tool_calls(msg)
        assert len(result) == 1
        assert result[0]["name"] == "search"

    def test_extract_from_dict_without_tool_calls(self):
        """从没有 tool_calls 的 dict 消息中提取"""
        msg = {"role": "assistant", "content": "Hello"}
        result = _extract_tool_calls(msg)
        assert result == []

    def test_extract_from_object_with_tool_calls(self):
        """从对象消息中提取 tool_calls"""
        from langchain_core.messages import AIMessage

        msg = AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "search", "args": {"q": "test"}}]
        )
        result = _extract_tool_calls(msg)
        assert len(result) == 1

    def test_extract_from_object_without_tool_calls(self):
        """从没有 tool_calls 的对象消息中提取"""
        from langchain_core.messages import AIMessage

        msg = AIMessage(content="Hello")
        result = _extract_tool_calls(msg)
        assert result == []

    def test_extract_from_none_like(self):
        """从无效消息中提取"""
        result = _extract_tool_calls(None)
        assert result == []


class TestExtractText:
    """测试文本提取逻辑"""

    def test_extract_from_dict(self):
        """从 dict 消息中提取文本"""
        msg = {"role": "assistant", "content": "Hello world"}
        result = _extract_text(msg)
        assert result == "Hello world"

    def test_extract_from_dict_empty(self):
        """从空 dict 消息中提取文本"""
        msg = {"role": "assistant", "content": ""}
        result = _extract_text(msg)
        assert result == ""

    def test_extract_from_object(self):
        """从对象消息中提取文本"""
        from langchain_core.messages import AIMessage

        msg = AIMessage(content="Hello world")
        result = _extract_text(msg)
        assert result == "Hello world"

    def test_extract_from_invalid(self):
        """从无效消息中提取文本"""
        result = _extract_text(None)
        assert result == ""


class TestRouteAfterLLM:
    """测试 LLM 后路由逻辑"""

    def test_tool_calls_with_empty_content_goes_to_loop_detect(self):
        """LLM 返回 tool_calls 但 content 为空时，应进入 loop_detect 而非 empty_feedback"""
        state = make_state(
            messages=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call-1", "name": "search", "args": {"q": "test"}}
                    ],
                }
            ]
        )
        result = route_after_llm(state)
        assert result == "loop_detect", (
            "Should route to loop_detect when tool_calls present, "
            "even if content is empty"
        )

    def test_empty_content_without_tool_calls_goes_to_empty_feedback(self):
        """LLM 返回空内容且无 tool_calls 时，应进入 empty_feedback"""
        state = make_state(
            messages=[
                {"role": "assistant", "content": ""}
            ]
        )
        result = route_after_llm(state)
        assert result == "empty_feedback"

    def test_whitespace_only_goes_to_empty_feedback(self):
        """LLM 返回纯空白内容时，应进入 empty_feedback"""
        state = make_state(
            messages=[
                {"role": "assistant", "content": "   \n  \t  "}
            ]
        )
        result = route_after_llm(state)
        assert result == "empty_feedback"

    def test_normal_text_goes_to_stuck_detect(self):
        """LLM 返回正常文本时，应进入 stuck_detect"""
        state = make_state(
            messages=[
                {"role": "assistant", "content": "Let me analyze this problem..."}
            ]
        )
        result = route_after_llm(state)
        assert result == "stuck_detect"


@pytest.mark.asyncio
class TestEmptyFeedbackNode:
    """测试空响应反馈节点"""

    async def test_first_empty_response_injects_prompt(self):
        """首次空响应应注入提示消息"""
        state = make_state(
            messages=[{"role": "assistant", "content": ""}],
            empty_retry_count=0,
        )
        config = {"configurable": {}}
        
        result = await empty_feedback_node(state, config)
        
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["empty_retry_count"] == 1
        assert "error" not in result
        assert "should_end" not in result

    async def test_second_empty_response_injects_prompt(self):
        """第二次空响应应继续注入提示消息"""
        state = make_state(
            messages=[{"role": "assistant", "content": ""}],
            empty_retry_count=1,
        )
        config = {"configurable": {}}
        
        result = await empty_feedback_node(state, config)
        
        assert "messages" in result
        assert result["empty_retry_count"] == 2
        assert "error" not in result

    async def test_third_empty_response_terminates(self):
        """第三次空响应应终止并报错"""
        state = make_state(
            messages=[{"role": "assistant", "content": ""}],
            empty_retry_count=2,
        )
        config = {"configurable": {}}
        
        result = await empty_feedback_node(state, config)
        
        assert result["empty_retry_count"] == 3
        assert result["error"] == "Empty response persists after correction"
        assert result["should_end"] is True
