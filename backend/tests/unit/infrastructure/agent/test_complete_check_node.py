"""测试 - 完成检查节点（LLM + 规则混合判断）

验证 complete_check_node 的混合判断逻辑
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.infrastructure.agent.nodes.complete_check_node import (
    rule_based_completion_check,
    llm_based_completion_check,
    complete_check_node,
)


class TestRuleBasedCompletionCheck:
    """测试规则判断逻辑"""

    def test_strong_completion_phrases(self):
        """明确的完成声明应该返回 True"""
        # English
        assert rule_based_completion_check("Task complete!") is True
        assert rule_based_completion_check("I have completed the task.") is True
        assert rule_based_completion_check("The task is done.") is True
        
        # Chinese
        assert rule_based_completion_check("任务完成！") is True
        assert rule_based_completion_check("任务已完成。") is True
        assert rule_based_completion_check("全部完成！") is True

    def test_strong_incomplete_phrases(self):
        """明确的未完成信号应该返回 False"""
        # English
        assert rule_based_completion_check("I need to continue working.") is False
        assert rule_based_completion_check("Let me continue with the next step.") is False
        assert rule_based_completion_check("Next, I will analyze the data.") is False
        
        # Chinese
        assert rule_based_completion_check("我需要继续工作。") is False
        assert rule_based_completion_check("让我继续下一步。") is False
        assert rule_based_completion_check("接下来我将分析数据。") is False

    def test_mixed_signals_return_false(self):
        """同时有完成和未完成信号时应该返回 False（还在继续工作）"""
        text = """I have completed the analysis.
        Next, I need to write the report."""
        assert rule_based_completion_check(text) is False

    def test_ambiguous_return_none(self):
        """模糊的表述应该返回 None（需要 LLM 判断）"""
        text = "Here is what I found so far..."
        assert rule_based_completion_check(text) is None

    def test_question_ending_return_none(self):
        """询问用户应该返回 None（需要 LLM 判断）"""
        text = "I've gathered all the information. Do you need anything else?"
        assert rule_based_completion_check(text) is None

    def test_empty_text_return_none(self):
        """空文本应该返回 None"""
        assert rule_based_completion_check("") is None
        assert rule_based_completion_check("   ") is None


@pytest.mark.asyncio
class TestLLMBasedCompletionCheck:
    """测试 LLM 判断逻辑"""

    async def test_llm_returns_json(self):
        """LLM 返回 JSON 格式应该正确解析"""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"is_complete": true, "confidence": 0.9, "reason": "Clear completion statement"}'
        ))
        
        result = await llm_based_completion_check(
            text="I have completed the task successfully.",
            task_description="Analyze the data",
            llm=mock_llm,
        )
        
        assert result["is_complete"] is True
        assert result["confidence"] == 0.9
        assert "Clear completion statement" in result["reason"]

    async def test_llm_returns_incomplete(self):
        """LLM 判断为未完成"""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"is_complete": false, "confidence": 0.85, "reason": "Still planning, no action taken"}'
        ))
        
        result = await llm_based_completion_check(
            text="I will start by reading the files...",
            task_description="Analyze the data",
            llm=mock_llm,
        )
        
        assert result["is_complete"] is False
        assert result["confidence"] == 0.85

    async def test_llm_failure_fallback(self):
        """LLM 调用失败应该返回安全的默认值"""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("Network error"))
        
        result = await llm_based_completion_check(
            text="Some text",
            task_description="Some task",
            llm=mock_llm,
        )
        
        assert result["is_complete"] is False
        assert result["confidence"] == 0.0
        assert "failed" in result["reason"]

    async def test_llm_returns_text_without_json(self):
        """LLM 返回纯文本时应该尝试解析"""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content="Yes, the task is completed."
        ))
        
        result = await llm_based_completion_check(
            text="Done!",
            task_description="Test task",
            llm=mock_llm,
        )
        
        # 应该从文本中推断
        assert result["is_complete"] is True
        assert result["confidence"] == 0.5  # fallback confidence


@pytest.mark.asyncio
class TestCompleteCheckNode:
    """测试完整的 complete_check_node"""

    def make_state(self, messages=None, **kwargs):
        """创建测试 state"""
        state = {
            "messages": messages or [],
            "system_prompt": "Test system prompt",
        }
        state.update(kwargs)
        return state

    async def test_rule_based_strong_completion(self):
        """规则判断为明确完成时应该直接返回"""
        from langchain_core.messages import AIMessage
        
        state = self.make_state(
            messages=[AIMessage(content="任务完成！我已经分析了所有数据。")]
        )
        config = {"configurable": {"llm": None}}  # 不需要 LLM
        
        result = await complete_check_node(state, config)
        
        assert result["is_complete"] is True
        assert result["completion_check_method"] == "rule"
        assert result["completion_confidence"] == 1.0
        assert "final_result" in result

    async def test_rule_based_strong_incomplete(self):
        """规则判断为明确未完成时应该返回 False"""
        from langchain_core.messages import AIMessage
        
        state = self.make_state(
            messages=[AIMessage(content="我需要继续工作，下一步是分析数据。")]
        )
        config = {"configurable": {"llm": None}}
        
        result = await complete_check_node(state, config)
        
        assert result["is_complete"] is False
        assert result["completion_check_method"] == "rule"

    async def test_llm_fallback_when_rule_inconclusive(self):
        """规则不确定时应该调用 LLM"""
        from langchain_core.messages import AIMessage
        from unittest.mock import AsyncMock, MagicMock
        
        state = self.make_state(
            messages=[AIMessage(content="Here's what I found so far...")]
        )
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"is_complete": true, "confidence": 0.8, "reason": "Substantive results provided"}'
        ))
        
        config = {"configurable": {"llm": mock_llm}}
        
        result = await complete_check_node(state, config)
        
        # 应该调用 LLM
        mock_llm.ainvoke.assert_called_once()
        assert result["completion_check_method"] == "llm"
        assert result["is_complete"] is True

    async def test_empty_messages(self):
        """空消息列表应该返回未完成"""
        state = self.make_state(messages=[])
        config = {"configurable": {"llm": None}}
        
        result = await complete_check_node(state, config)
        
        assert result["is_complete"] is False

    async def test_empty_text(self):
        """空文本应该返回未完成"""
        from langchain_core.messages import AIMessage
        
        state = self.make_state(
            messages=[AIMessage(content="")]
        )
        config = {"configurable": {"llm": None}}
        
        result = await complete_check_node(state, config)
        
        assert result["is_complete"] is False

    async def test_llm_not_available(self):
        """LLM 不可用时应该降级到未完成"""
        from langchain_core.messages import AIMessage
        
        state = self.make_state(
            messages=[AIMessage(content="Here's what I found...")]
        )
        config = {"configurable": {}}  # 没有 llm
        
        result = await complete_check_node(state, config)
        
        assert result["is_complete"] is False
        assert result["completion_check_method"] == "fallback"

    async def test_real_world_case_your_response(self):
        """真实案例：你的那个回复应该被识别为完成"""
        from langchain_core.messages import AIMessage
        from unittest.mock import AsyncMock, MagicMock
        
        text = """## 深入分析：杭州智能交管机器人

### 背景信息
- **地点**：中国杭州市
- **技术应用**：AI交通管理机器人"杭警智行"

### 总结
杭州引入智能交管机器人"杭警智行"是智慧城市建设的一个重要里程碑。这些机器人通过先进的技术手段，有效提升了交通管理和执法效率，为市民提供了更加安全和便捷的出行环境。如果您对这一话题还有其他方面想要了解，请告诉我！"""
        
        state = self.make_state(
            messages=[AIMessage(content=text)]
        )
        
        # 模拟 LLM 判断为完成（因为提供了完整的结果并询问用户）
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"is_complete": true, "confidence": 0.85, "reason": "Provided complete analysis and asked if user needs more"}'
        ))
        
        config = {"configurable": {"llm": mock_llm}}
        
        result = await complete_check_node(state, config)
        
        # 规则应该无法判断（没有明确关键词），需要 LLM
        mock_llm.ainvoke.assert_called_once()
        assert result["completion_check_method"] == "llm"
