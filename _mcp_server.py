import sys
import json
import requests

FLASK_URL = "http://127.0.0.1:55154"

def recv_request():
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)

def send_response(result):
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()

def send_error(code, message):
    send_response({"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}})

def handle_list_tools(req_id):
    resp = requests.get(FLASK_URL + "/tools")
    tools = resp.json()
    send_response({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["parameters"]
                }
                for t in tools
            ]
        }
    })

def handle_call_tool(req_id, tool_name, arguments):
    resp = requests.post(FLASK_URL + "/call/" + tool_name, json=arguments)
    data = resp.json()
    if "error" in data:
        send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": data["error"]}
        })
    else:
        result = data["result"]
        send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": str(result)}]
            }
        })

def main():
    send_response({"jsonrpc": "2.0", "method": "initialized"})
    while True:
        req = recv_request()
        if req is None:
            break
        method = req.get("method", "")
        req_id = req.get("id")
        if method == "initialize":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "flask-tools", "version": "1.0.0"}
                }
            })
        elif method == "tools/list":
            handle_list_tools(req_id)
        elif method == "tools/call":
            params = req.get("params", {})
            handle_call_tool(req_id, params.get("name"), params.get("arguments", {}))
        elif method == "ping":
            send_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
        else:
            if req_id is not None:
                send_error(-32601, "Method not found: " + method)

if __name__ == "__main__":
    main()
