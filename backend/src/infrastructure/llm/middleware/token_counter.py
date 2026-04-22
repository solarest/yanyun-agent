"""基础设施层 - Token 计数器"""
import tiktoken


def count_tokens(messages: list[dict], model: str = "gpt-4") -> int:
    """计算消息的 Token 数量
    
    Args:
        messages: 消息列表
        model: 模型名称
        
    Returns:
        Token 数量
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # 未知模型，使用默认编码
        encoding = tiktoken.get_encoding("cl100k_base")
    
    # 基础 token 计数
    num_tokens = 0
    for message in messages:
        num_tokens += 4  # 每条消息的基础 token
        for key, value in message.items():
            if isinstance(value, str):
                num_tokens += len(encoding.encode(value))
    
    num_tokens += 2  # 助手回复的基础 token
    
    return num_tokens
