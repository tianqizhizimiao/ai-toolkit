# ai-toolkit

通过 MCP 协议为 [OpenCode](https://github.com/anomalyco/opencode) 注入自定义 Python 工具。

一个装饰器注册函数，AI 自动通过 MCP 协议调用你的代码。

## 特性

- 装饰器注册工具，自动暴露给 OpenCode AI
- 基于 Flask + MCP 协议，无需修改提示词
- 支持类型注解自动推导参数 schema
- 会话上下文自动持久化
- 异步聊天，同步等待可选

## 安装

```bash
pip install flask requests
```

确保 OpenCode 服务已启动：

```bash
opencode serve --port 4096
```

## 快速开始

```python
from aitoolkit import AIClient

# 1. 初始化客户端（传入 OpenCode 服务地址）
ai = AIClient(server="http://127.0.0.1:4096")

# 2. 用装饰器注册工具
@ai.tool()
def add(a: int, b: int) -> int:
    """计算两个整数相加"""
    return a + b

@ai.tool()
def get_weather(city: str) -> str:
    """查询指定城市的天气"""
    return f"{city} 今天晴天，25°C，适合出门"

# 3. 启动 Flask 服务器并注册 MCP
ai.start()

# 4. 开始聊天
ai.chat("帮我算一下 37 加 58 等于多少", wait=True)
print(ai.get_all())  # 输出: 37 + 58 = **95**

ai.chat("今天北京天气怎么样？", wait=True)
print(ai.get_all())  # 输出: 北京 今天晴天，25°C，适合出门
```

## 工作原理

```
@ai.tool() 装饰器
    ↓ 注册到 self.tools 字典
ai.start()
    ↓ 启动 Flask 服务器 (HTTP)
    ↓ 生成 MCP Server 脚本 (stdio)
    ↓ 注册到 OpenCode (/mcp 端点)
OpenCode AI → MCP (stdio) → Flask (HTTP) → 你的 Python 函数
```

## API 参考

### AIClient

```python
AIClient(
    server: str = "http://127.0.0.1:4096",  # OpenCode 服务地址
    flask_port: int = 0                      # Flask 端口，0=自动分配
)
```

上下文以类属性 `context: list` 存储，进程退出即清除，不做文件持久化。

#### `@ai.tool(name: str = None)`

装饰器，注册 Python 函数为 AI 可调用的工具。

```python
@ai.tool()
def my_func(a: int, b: str) -> str:
    """工具描述（必填，AI 通过描述决定何时调用）"""
    return f"{a} + {b}"

@ai.tool(name="custom_name")
def another_func(x: float) -> float:
    """自定义工具名"""
    return x * 2
```

**参数类型映射：**

| Python 类型 | JSON Schema 类型 |
|-------------|-----------------|
| `int`       | `integer`       |
| `float`     | `number`        |
| `bool`      | `boolean`       |
| `str` / 其他 | `string`        |

#### `ai.start(mcp_name: str = "custom-tools", flask_port: int = 0)`

启动 Flask 服务器并注册 MCP 到 OpenCode。必须在 `chat()` 之前调用。

#### `ai.chat(prompt: str, wait: bool = False)`

发送聊天消息。

```python
# 异步发送（不等待）
ai.chat("你好")

# 同步等待回复
ai.chat("你好", wait=True)
response = ai.get_all()
```

#### `ai.get_all(timeout: int = 10) -> str`

等待并获取 AI 回复。超时返回 `"[超时]"`。

#### `ai.get() -> str`

获取最新一条 AI 回复（不等待）。

#### `ai.read_file(path: str) -> str`

通过 OpenCode 读取文件内容。

#### `ai.create_session(title: str = "AI Chat")`

创建新会话。

## 高级用法

### 复杂工具

```python
import sqlite3

@ai.tool()
def query_db(sql: str) -> str:
    """执行 SQL 查询并返回结果"""
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    return "\n".join(str(row) for row in rows)

@ai.tool()
def search_web(query: str, limit: int = 5) -> str:
    """搜索网络并返回前 N 条结果"""
    import requests
    resp = requests.get(f"https://api.example.com/search", params={"q": query, "limit": limit})
    return resp.text
```

### 链式调用

```python
ai.chat("第一步").chat("第二步").chat("第三步", wait=True)
print(ai.get_all())
```

### 自定义 Flask 端口

```python
ai = AIClient(server="http://127.0.0.1:4096", flask_port=8888)
ai.start()  # Flask 固定在 8888 端口
```

### 远程 OpenCode 服务

```python
ai = AIClient(server="http://192.168.1.100:4096")
ai.start()
```

## 注意事项

1. **工具描述必填** — AI 通过 docstring 判断何时调用工具，请写清楚描述
2. **类型注解建议加上** — 用于自动生成 JSON Schema，AI 能正确传参
3. **先 start 再 chat** — 必须在发送消息前调用 `ai.start()`
4. **Flask 依赖** — 需要 `pip install flask requests`
5. **OpenCode 版本** — 需要支持 MCP 协议的 OpenCode 版本

## 项目结构

```
aitoolkit/
├── main.py          # 核心库（AIClient 类）
├── example.py       # 使用示例
└── README.md        # 本文档
```


