"""领域层 - Token 估算工具"""


def count_tokens(text: str) -> int:
    """简单 Token 计数
    
    估算规则：
    - 中文字符：1.5 tokens/字符
    - 其他字符：0.25 tokens/字符
    
    Args:
        text: 要计算的文本
        
    Returns:
        预估的 token 数量
    """
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.25)
