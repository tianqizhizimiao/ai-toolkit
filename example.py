from aitoolkit import AIClient

ai = AIClient(server="http://127.0.0.1:4096")

@ai.tool()
def add(a: int, b: int) -> int:
    """计算两个整数相加"""
    return a + b

@ai.tool()
def get_weather(city: str) -> str:
    """查询指定城市的天气"""
    return f"{city} 今天晴天，25°C，适合出门"

@ai.tool()
def search_knowledge(query: str) -> str:
    """搜索内部知识库"""
    knowledge = {
        "python": "Python 是一种解释型、面向对象、动态数据类型的高级程序设计语言。",
        "flask": "Flask 是一个轻量级的 Python Web 框架，基于 Werkzeug 和 Jinja2。",
        "mcp": "MCP (Model Context Protocol) 是 Anthropic 提出的开放协议，用于 AI 模型与外部工具的标准化交互。"
    }
    for key, value in knowledge.items():
        if key in query.lower():
            return value
    return f"未找到与 '{query}' 相关的知识条目。"

ai.start()

print("=== 测试 1: 普通对话 ===")
ai.chat("你好，你是谁？", wait=True)
print("回复:", ai.get_all())

print("\n=== 测试 2: 工具调用 (加法) ===")
ai.chat("帮我算一下 37 加 58 等于多少", wait=True)
print("回复:", ai.get_all())

print("\n=== 测试 3: 工具调用 (天气) ===")
ai.chat("今天北京天气怎么样？", wait=True)
print("回复:", ai.get_all())

print("\n=== 测试 4: 工具调用 (知识库) ===")
ai.chat("Python 是什么？", wait=True)
print("回复:", ai.get_all())
