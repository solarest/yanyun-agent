"""测试 - 用户问题检测逻辑

验证 _is_user_question 函数能否正确识别 LLM 的询问/邀请用语
"""
import pytest
from src.application.use_cases.agent_workflow import _is_user_question


class TestIsUserQuestion:
    """测试用户问题检测"""

    def test_question_mark_ending(self):
        """以问号结尾应该被识别"""
        assert _is_user_question("What do you think?") is True
        assert _is_user_question("你觉得怎么样？") is True

    def test_exclamation_with_question_indicators(self):
        """感叹号结尾但包含询问用语应该被识别"""
        # 中文
        assert _is_user_question("如果您还想了解更多信息，请告诉我！") is True
        assert _is_user_question("是否还需要我做什么？") is True
        assert _is_user_question("还有其他需要了解的内容吗！") is True
        
        # 英文
        assert _is_user_question("Let me know if you need anything else!") is True
        assert _is_user_question("Please tell me if you have any questions!") is True

    def test_exclamation_without_question_indicators(self):
        """感叹号结尾但没有询问用语不应被识别"""
        assert _is_user_question("任务完成！") is False
        assert _is_user_question("I finished the task!") is False
        assert _is_user_question("这是一个重要的发现！") is False

    def test_plain_statement(self):
        """普通陈述句不应被识别"""
        assert _is_user_question("Here is the information you requested.") is False
        assert _is_user_question("这是你要的信息。") is False

    def test_empty_text(self):
        """空文本不应被识别"""
        assert _is_user_question("") is False
        assert _is_user_question("   ") is False

    def test_middle_question_mark(self):
        """中间的问号不应误判（只看最后一行）"""
        text = """这是分析结果。
你觉得怎么样？
让我继续说明。"""
        assert _is_user_question(text) is False

    def test_real_world_case(self):
        """真实案例：你的那个回复"""
        text = """## 深入分析：杭州智能交管机器人

### 背景信息
- **地点**：中国杭州市
- **技术应用**：AI交通管理机器人"杭警智行"

### 总结
杭州引入智能交管机器人"杭警智行"是智慧城市建设的一个重要里程碑。这些机器人通过先进的技术手段，有效提升了交通管理和执法效率，为市民提供了更加安全和便捷的出行环境。如果您对这一话题还有其他方面想要了解，请告诉我！"""
        
        assert _is_user_question(text) is True, (
            "Should detect '如果您对这一话题还有其他方面想要了解，请告诉我！' as a question"
        )

    def test_various_question_patterns(self):
        """测试各种询问模式"""
        # 是否类
        assert _is_user_question("是否满意这个结果？") is True
        assert _is_user_question("是否还需要更多信息！") is True
        
        # 还有类
        assert _is_user_question("还有其他问题吗？") is True
        assert _is_user_question("还有其他需要了解的内容！") is True
        
        # 想不想类
        assert _is_user_question("你还想了解什么？") is True
        assert _is_user_question("如果还想深入了解，请告诉我！") is True

    def test_case_insensitive(self):
        """应该忽略大小写"""
        assert _is_user_question("LET ME KNOW IF YOU NEED HELP!") is True
        assert _is_user_question("Please Tell Me If You Have Questions!") is True
