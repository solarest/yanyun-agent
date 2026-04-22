"""测试 - Token 计数器"""
import pytest

from src.infrastructure.llm.middleware.token_counter import count_tokens


def test_count_tokens_with_gpt4():
    """测试 GPT-4 的 Token 计数"""
    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello, how are you?"},
    ]
    
    count = count_tokens(messages, model="gpt-4")
    
    # 应该返回正数
    assert count > 0


def test_count_tokens_with_unknown_model():
    """测试未知模型的 Token 计数（回退到 cl100k_base）"""
    messages = [
        {"role": "user", "content": "Test message"},
    ]
    
    count = count_tokens(messages, model="unknown-model")
    
    # 应该返回正数
    assert count > 0


def test_count_tokens_empty_messages():
    """测试空消息列表"""
    count = count_tokens([], model="gpt-4")
    
    # 空列表应该返回基础 token 数
    assert count >= 0
