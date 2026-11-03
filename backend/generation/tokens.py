"""token 计量与上下文预算。

单独成模块的原因：provider 适配器和生成器都要用它，放在 generator 里会造成
`generator -> providers -> generator` 的循环导入。
"""
import tiktoken

# 上下文窗口与输出预算（Ollama options 与 openai 兼容后端的 max_tokens 共用）
NUM_CTX = 4096
NUM_PREDICT = 1024
# 输入预算 = 窗口 - 保留给输出，否则 prompt 与输出抢同一块 4096，尾部会被截
INPUT_TOKEN_BUDGET = NUM_CTX - NUM_PREDICT

_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """真实 token 计数。

    旧实现是 `len(text.split())`，实测误差：英文 −8.3%、中文 −97.6%、
    中英混 −72.0%（中文没有空格，整句只算 1 个 token）。
    """
    if not text:
        return 0
    return len(_ENC.encode(text))
