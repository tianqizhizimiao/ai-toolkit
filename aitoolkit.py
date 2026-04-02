"""
ai-toolkit - 通过 MCP 协议为 OpenCode 注入自定义 Python 工具

Usage:
    from aitoolkit import AIClient

    ai = AIClient(server="http://127.0.0.1:4096")

    @ai.tool()
    def add(a: int, b: int) -> int:
        \"\"\"计算两个整数相加\"\"\"
        return a + b

    ai.start()
    ai.chat("帮我算一下 37 加 58 等于多少", wait=True)
    print(ai.get_all())
"""

import json
import os
import sys
import socket
import threading
import time
import inspect
from typing import Dict, Any, Optional, Callable

import requests

# ======================
# Flask 工具服务器
# ======================
def _make_flask_app(tools: Dict[str, Callable]) -> Any:
    from flask import Flask, request, jsonify

    app = Flask(__name__)

    @app.route("/tools", methods=["GET"])
    def list_tools():
        result = []
        for name, func in tools.items():
            sig = inspect.signature(func)
            params_schema = {"type": "object", "properties": {}, "required": []}
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                ptype = param.annotation
                json_type = {"int": "integer", "float": "number", "bool": "boolean"}.get(ptype.__name__, "string")
                params_schema["properties"][pname] = {"type": json_type}
                if param.default == inspect.Parameter.empty:
                    params_schema["required"].append(pname)
            result.append({
                "name": name,
                "description": inspect.getdoc(func) or "",
                "parameters": params_schema
            })
        return jsonify(result)

    @app.route("/call/<name>", methods=["POST"])
    def call_tool(name):
        func = tools.get(name)
        if not func:
            return jsonify({"error": f"tool '{name}' not found"}), 404
        try:
            args = request.get_json(force=True) or {}
            result = func(**args)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


# ======================
# MCP Server 脚本模板
# ======================
MCP_SERVER_TEMPLATE = '''\
import sys
import json
import requests

FLASK_URL = "{flask_url}"

def recv_request():
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)

def send_response(result):
    sys.stdout.write(json.dumps(result) + "\\n")
    sys.stdout.flush()

def send_error(code, message):
    send_response({{"jsonrpc": "2.0", "id": None, "error": {{"code": code, "message": message}}}})

def handle_list_tools(req_id):
    resp = requests.get(FLASK_URL + "/tools")
    tools = resp.json()
    send_response({{
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {{
            "tools": [
                {{
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["parameters"]
                }}
                for t in tools
            ]
        }}
    }})

def handle_call_tool(req_id, tool_name, arguments):
    resp = requests.post(FLASK_URL + "/call/" + tool_name, json=arguments)
    data = resp.json()
    if "error" in data:
        send_response({{
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {{"code": -32603, "message": data["error"]}}
        }})
    else:
        result = data["result"]
        send_response({{
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {{
                "content": [{{"type": "text", "text": str(result)}}]
            }}
        }})

def main():
    send_response({{"jsonrpc": "2.0", "method": "initialized"}})
    while True:
        req = recv_request()
        if req is None:
            break
        method = req.get("method", "")
        req_id = req.get("id")
        if method == "initialize":
            send_response({{
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {{
                    "protocolVersion": "2024-11-05",
                    "capabilities": {{"tools": {{}}}},
                    "serverInfo": {{"name": "flask-tools", "version": "1.0.0"}}
                }}
            }})
        elif method == "tools/list":
            handle_list_tools(req_id)
        elif method == "tools/call":
            params = req.get("params", {{}})
            handle_call_tool(req_id, params.get("name"), params.get("arguments", {{}}))
        elif method == "ping":
            send_response({{"jsonrpc": "2.0", "id": req_id, "result": {{}}}})
        else:
            if req_id is not None:
                send_error(-32601, "Method not found: " + method)

if __name__ == "__main__":
    main()
'''


class AIClient:
    """OpenCode AI 客户端，支持通过 MCP 协议注入自定义工具。

    Args:
        server: OpenCode 服务地址，格式 "http://host:port"
        flask_port: Flask 工具服务器端口，0 表示自动分配

    Example:
        >>> ai = AIClient(server="http://127.0.0.1:4096")
        >>> @ai.tool()
        ... def add(a: int, b: int) -> int:
        ...     \"\"\"计算两个数相加\"\"\"
        ...     return a + b
        >>> ai.start()
        >>> ai.chat("37 加 58 等于多少", wait=True)
        >>> print(ai.get_all())
        37 + 58 = **95**
    """

    context: list = []

    def __init__(self, server: str = "http://127.0.0.1:4096", flask_port: int = 0):
        self.base_url = server.rstrip("/")
        self.session_id = None
        self.tools: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self.flask_port = flask_port
        self._flask_thread = None
        self._mcp_script_path = None
        self._started = False

        self.check_health()

    def tool(self, name: Optional[str] = None):
        """装饰器：注册 Python 函数为 AI 可调用的工具。

        Args:
            name: 工具名称，默认使用函数名

        Example:
            @ai.tool()
            def search(query: str) -> str:
                \"\"\"搜索知识库\"\"\"
                return db.search(query)

            @ai.tool(name="calc")
            def evaluate(expr: str) -> float:
                \"\"\"计算数学表达式\"\"\"
                return eval(expr)
        """
        def decorator(func: Callable):
            self.tools[name or func.__name__] = func
            return func
        return decorator

    def check_health(self):
        """检查 OpenCode 服务是否可达。"""
        requests.get(f"{self.base_url}/global/health").raise_for_status()

    def create_session(self, title: str = "AI Chat"):
        """创建或切换会话。

        Args:
            title: 会话标题
        """
        res = requests.post(f"{self.base_url}/session", json={"title": title})
        self.session_id = res.json()["id"]
        self.context = []

    def start(self, mcp_name: str = "custom-tools", flask_port: int = 0) -> Dict[str, Any]:
        """启动 Flask 工具服务器并注册 MCP 到 OpenCode。

        必须在发送聊天消息前调用此方法。

        Args:
            mcp_name: MCP 服务器名称
            flask_port: Flask 端口，0 表示自动分配

        Returns:
            MCP 注册结果

        Raises:
            RuntimeError: Flask 未安装
        """
        if self._started:
            return {"status": "already_started"}

        port = self._start_flask(flask_port)
        result = self._register_mcp(mcp_name, port)
        self._started = True
        return result

    def _start_flask(self, port: int = 0) -> int:
        if self.flask_port:
            return self.flask_port

        try:
            import flask  # noqa: F401
        except ImportError:
            raise RuntimeError("Flask 未安装，请运行: pip install flask")

        app = _make_flask_app(self.tools)
        if port == 0:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]

        self.flask_port = port

        def _run():
            app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

        self._flask_thread = threading.Thread(target=_run, daemon=True)
        self._flask_thread.start()
        time.sleep(0.5)
        return port

    def _register_mcp(self, name: str, port: int) -> Dict[str, Any]:
        flask_url = f"http://127.0.0.1:{port}"

        script = MCP_SERVER_TEMPLATE.format(flask_url=flask_url)
        main_file = getattr(sys.modules["__main__"], "__file__", None)
        script_dir = os.path.dirname(os.path.abspath(main_file)) if main_file else os.getcwd()
        self._mcp_script_path = os.path.join(script_dir, "_mcp_server.py")
        with open(self._mcp_script_path, "w", encoding="utf-8") as f:
            f.write(script)

        res = requests.post(
            f"{self.base_url}/mcp",
            json={
                "name": name,
                "config": {
                    "type": "local",
                    "command": [sys.executable, str(self._mcp_script_path)]
                }
            },
            params={"directory": os.path.expanduser("~")}
        )
        return res.json()

    def chat(self, prompt: str, wait: bool = False):
        """发送聊天消息。

        Args:
            prompt: 用户消息内容
            wait: 是否等待 AI 回复完成后再返回

        Returns:
            self，支持链式调用
        """
        if not self.session_id:
            self.create_session()

        self.context.append({"role": "user", "content": prompt})
        event = threading.Event()

        def _send():
            try:
                payload = {"parts": [{"type": "text", "text": prompt}]}
                resp = requests.post(
                    f"{self.base_url}/session/{self.session_id}/message",
                    json=payload,
                    timeout=120
                )
                resp_data = resp.json()
                parts = resp_data.get("parts", [])

                reply_text = ""
                for part in parts:
                    if part.get("type") == "text":
                        reply_text = part.get("text", "")
                        break

                self.context.append({"role": "assistant", "content": reply_text})
            except Exception as e:
                self.context.append({"role": "assistant", "content": f"[错误] {e}"})
            finally:
                event.set()

        t = threading.Thread(target=_send, daemon=True)
        t.start()
        if wait:
            event.wait()
        return self

    def get(self) -> str:
        """获取最新一条 AI 回复。"""
        if len(self.context) >= 2 and self.context[-1]["role"] == "assistant":
            return self.context[-1]["content"]
        return ""

    def get_all(self, timeout: int = 10) -> str:
        """等待并获取 AI 回复。

        Args:
            timeout: 超时时间（秒）

        Returns:
            AI 回复内容，超时返回 "[超时]"
        """
        start = time.time()
        while time.time() - start < timeout:
            if len(self.context) > 0 and self.context[-1]["role"] == "assistant":
                return self.get()
            time.sleep(0.2)
        return "[超时]"

    def read_file(self, path: str) -> str:
        """通过 OpenCode 读取文件内容。

        Args:
            path: 文件路径

        Returns:
            文件内容
        """
        res = requests.get(f"{self.base_url}/file/content", params={"path": path})
        return res.json().get("content", "")
