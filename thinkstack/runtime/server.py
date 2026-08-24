"""ThinkStack HTTP REST API 服务器（默认 9635 端口）。

公开接口：ThinkStackServer, BUILTIN_AGENTS
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

from thinkstack.core.agents import EchoAgent, MarkdownAgent, ToolCallingAgent
from thinkstack.core.markdown import markdown_to_html
from thinkstack.core.stack import ThinkStack
from thinkstack.core.tool import ToolResult

# 内置 Agent 名称映射（供 /api/agent/run 选择，自定义 Agent 通过 stack.custom_agents 扩展）
BUILTIN_AGENTS: dict[str, type] = {
    "echo": EchoAgent,
    "tool-calling": ToolCallingAgent,
    "markdown": MarkdownAgent,
}


class ThinkStackServer:
    """围绕 ThinkStack 实例提供 JSON REST API 的 HTTP 服务器。

    默认监听 9635 端口，任何语言/HTTP 客户端均可接入。
    支持通过命令通道 `webrun <port>` 动态开启 Web 控制台。
    """

    def __init__(self, stack: ThinkStack, host: str = "0.0.0.0", port: int = 9635) -> None:
        self.stack = stack
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._consoles: dict[int, Any] = {}

    # ---------------------------------------------------------------- 生命周期

    def start(self, block: bool = False) -> None:
        """启动服务器；block=True 时阻塞，否则后台线程运行。"""
        server = self
        stack = self.stack

        class Handler(BaseHTTPRequestHandler):
            server_version = "ThinkStack/1.1"

            def _send(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> Optional[dict]:
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw.decode("utf-8"))
                except Exception:
                    return None

            def do_OPTIONS(self) -> None:  # CORS 预检
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self) -> None:
                self._route("GET")

            def do_POST(self) -> None:
                self._route("POST")

            def _resolve_agent(self, key: str):
                cls = BUILTIN_AGENTS.get(key)
                if cls is not None:
                    return cls()
                return stack.resolve_agent(key)

            def _route(self, method: str) -> None:
                path = urlparse(self.path).path
                try:
                    if method == "GET" and path == "/api/health":
                        return self._send(200, {"status": "ok", "running": stack.is_running})
                    if method == "GET" and path == "/api/info":
                        return self._send(200, server._info())
                    if method == "GET" and path == "/api/tools":
                        return self._send(200, {"tools": stack.list_tools()})
                    if method == "POST" and path == "/api/tools/call":
                        return self._handle_tool_call()
                    if method == "POST" and path == "/api/tools/acall":
                        return self._handle_tool_acall()
                    if method == "GET" and path == "/api/extensions":
                        return self._send(200, server._extensions_info())
                    if method == "POST" and path == "/api/extensions/register":
                        return self._handle_extension_register()
                    if method == "GET" and path == "/api/agents":
                        return self._send(200, server._agents_info())
                    if method == "GET" and path == "/api/memory":
                        return self._send(200, server._memory_info())
                    if method == "POST" and path == "/api/memory":
                        return self._handle_memory()
                    if method == "POST" and path == "/api/markdown/render":
                        return self._handle_markdown_render()
                    if method == "POST" and path == "/api/agent/run":
                        return self._handle_agent_run()
                    if method == "POST" and path == "/api/agent/run/stream":
                        return self._handle_agent_run_stream()
                    if method == "POST" and path == "/api/tasks/run":
                        return self._handle_tasks_run()
                    if method == "POST" and path == "/api/command":
                        return self._handle_command()

                    # 扩展生命周期：/api/extensions/{name}/{disable|enable|unload}
                    ext_m = _match_extension_action(path)
                    if method == "POST" and ext_m:
                        return self._handle_extension_action(*ext_m)

                    return self._send(404, {"error": "未找到该端点", "path": path})
                except Exception as exc:  # 兜底：任何内部异常转 JSON 错误
                    stack.logger.warning("请求处理异常：%s", exc)
                    return self._send(500, {"error": str(exc)})

            def _handle_tool_call(self) -> None:
                data = self._read_json() or {}
                name = data.get("name", "")
                args = data.get("args", {}) or {}
                result: ToolResult = stack.call_tool(name, **args)
                self._send(200, result.model_dump())

            def _handle_tool_acall(self) -> None:
                data = self._read_json() or {}
                name = data.get("name", "")
                args = data.get("args", {}) or {}
                result: ToolResult = asyncio.run(stack.acall_tool(name, **args))
                self._send(200, result.model_dump())

            def _handle_extension_register(self) -> None:
                data = self._read_json() or {}
                name = data.get("name", "")
                module_path = data.get("module_path", "")
                handle = stack.register_extension(name, module_path)
                self._send(200, {"name": handle.name, "is_active": handle.is_active})

            def _handle_extension_action(self, name: str, action: str) -> None:
                try:
                    handle = stack.get_extension(name)
                except Exception as exc:
                    return self._send(404, {"error": str(exc)})
                if action == "disable":
                    handle.disable()
                elif action == "enable":
                    handle.enable()
                elif action == "unload":
                    stack._registry.unload(name)
                else:
                    return self._send(400, {"error": f"未知扩展操作 {action!r}"})
                self._send(200, {"name": name, "is_active": handle.is_active})

            def _handle_memory(self) -> None:
                data = self._read_json() or {}
                action = data.get("action", "retrieve")
                kind = data.get("kind", "working")
                key = data.get("key", "")
                try:
                    mem = stack.get_memory(kind)
                except Exception as exc:
                    return self._send(400, {"error": str(exc)})
                if action == "store":
                    mem.store(key, data.get("value"))
                    return self._send(200, {"ok": True, "action": "store", "kind": kind, "key": key})
                if action == "retrieve":
                    value = mem.retrieve(key)
                    return self._send(200, {"ok": True, "action": "retrieve", "value": value})
                if action == "clear":
                    mem.clear()
                    return self._send(200, {"ok": True, "action": "clear", "kind": kind})
                return self._send(400, {"error": f"未知记忆操作 {action!r}"})

            def _handle_markdown_render(self) -> None:
                data = self._read_json()
                if data is None:
                    return self._send(400, {"error": "请求体不是合法 JSON"})
                text = data.get("text", "") if isinstance(data, dict) else str(data)
                return self._send(200, {"html": markdown_to_html(text)})

            def _handle_agent_run(self) -> None:
                data = self._read_json() or {}
                agent_key = data.get("agent", "echo")
                task_input = data.get("input", "")
                max_iterations = data.get("max_iterations")
                agent = self._resolve_agent(agent_key)
                if agent is None:
                    return self._send(400, {"error": f"未知 agent：{agent_key!r}"})
                result = stack.run_agent(agent, task_input, max_iterations)
                self._send(200, result.model_dump())

            def _handle_agent_run_stream(self) -> None:
                data = self._read_json() or {}
                agent_key = data.get("agent", "echo")
                task_input = data.get("input", "")
                max_iterations = data.get("max_iterations")
                agent = self._resolve_agent(agent_key)
                if agent is None:
                    return self._send(400, {"error": f"未知 agent：{agent_key!r}"})

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    for step in stack.run_agent_stream(agent, task_input, max_iterations):
                        payload = json.dumps(step, ensure_ascii=False, default=str)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    self.wfile.flush()
                except Exception as exc:
                    try:
                        err = json.dumps({"error": str(exc)}, ensure_ascii=False)
                        self.wfile.write(f"event: error\ndata: {err}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except Exception:
                        pass

            def _handle_tasks_run(self) -> None:
                results = stack.run_tasks()
                self._send(200, {"results": [r.model_dump() for r in results]})

            def _handle_command(self) -> None:
                data = self._read_json()
                if data is None:
                    return self._send(400, {"error": "请求体不是合法 JSON"})
                if isinstance(data, str):
                    command = data
                else:
                    command = str(data.get("command", ""))
                self._send(200, server.handle_command(command))

            def log_message(self, format: str, *args: Any) -> None:  # 静默日志
                pass

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        if block:
            self._httpd.serve_forever()
        else:
            thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            thread.start()

    def shutdown(self) -> None:
        """停止服务器。"""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        for console in list(self._consoles.values()):
            try:
                console.shutdown()
            except Exception:
                pass
        self._consoles.clear()

    # ---------------------------------------------------------------- 命令通道

    def handle_command(self, command: str) -> dict[str, Any]:
        """处理文本命令，当前支持：

        - `webrun <port>`：在指定端口开启 Web 控制台
        - `webrun stop <port>`：停止指定端口的 Web 控制台
        - `help`：查看可用命令
        """
        text = (command or "").strip()
        if not text:
            return {"ok": False, "error": "空命令"}

        parts = text.split()
        head = parts[0].lower()

        if head == "help":
            return {
                "ok": True,
                "commands": [
                    "webrun <port>       在指定端口开启 Web 控制台",
                    "webrun stop <port>  停止指定端口的 Web 控制台",
                    "help               查看可用命令",
                ],
            }

        if head == "webrun":
            if len(parts) >= 3 and parts[1].lower() == "stop":
                return self._stop_console(int(parts[2]))
            if len(parts) >= 2:
                try:
                    port = int(parts[1])
                except ValueError:
                    return {"ok": False, "error": f"无效端口：{parts[1]!r}"}
                return self._start_console(port)
            return {"ok": False, "error": "用法：webrun <port> 或 webrun stop <port>"}

        return {"ok": False, "error": f"未知命令 {head!r}，输入 help 查看可用命令"}

    def _start_console(self, port: int) -> dict[str, Any]:
        """在指定端口启动 Web 控制台。"""
        if port in self._consoles:
            return {"ok": True, "message": "控制台已在运行", "url": f"http://localhost:{port}/"}
        from thinkstack.runtime.webconsole import WebConsole

        console = WebConsole(self.stack, host=self.host, port=port)
        try:
            console.start()
        except OSError as exc:
            return {"ok": False, "error": f"端口 {port} 启动失败：{exc}"}
        self._consoles[port] = console
        return {
            "ok": True,
            "message": "Web 控制台已开启",
            "url": f"http://localhost:{port}/",
            "port": port,
        }

    def _stop_console(self, port: int) -> dict[str, Any]:
        """停止指定端口的 Web 控制台。"""
        console = self._consoles.pop(port, None)
        if console is None:
            return {"ok": False, "error": f"端口 {port} 上没有运行中的控制台"}
        console.shutdown()
        return {"ok": True, "message": f"端口 {port} 的控制台已停止"}

    # ---------------------------------------------------------------- 信息查询

    def _info(self) -> dict[str, Any]:
        return {
            "name": self.stack.config.name,
            "running": self.stack.is_running,
            "agent_name": self.stack.config.agent_name,
            "max_iterations": self.stack.config.max_iterations,
            "scheduler": self.stack.config.scheduler.strategy,
            "tool_count": len(self.stack.list_tools()),
            "extension_count": len(self.stack.list_extensions()),
            "agent_count": len(self.stack.list_agents()),
        }

    def _extensions_info(self) -> dict[str, Any]:
        return {
            "extensions": [
                {"name": h.name, "is_active": h.is_active, "hooks": h.hook_points}
                for h in self.stack.list_extensions()
            ]
        }

    def _agents_info(self) -> dict[str, Any]:
        return {
            "builtin": list(BUILTIN_AGENTS.keys()),
            "custom": self.stack.list_agents(),
        }

    def _memory_info(self) -> dict[str, Any]:
        return {
            "short_term": {
                "capacity": self.stack.short_term_memory.capacity,
                "size": len(self.stack.short_term_memory),
            },
            "working": {"size": len(self.stack.working_memory.snapshot())},
            "long_term_backend": type(self.stack.long_term_memory).__name__,
        }


def _match_extension_action(path: str) -> Optional[tuple[str, str]]:
    """匹配 /api/extensions/{name}/{action}，返回 (name, action) 或 None。"""
    prefix = "/api/extensions/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    parts = rest.split("/")
    if len(parts) != 2:
        return None
    name, action = parts
    if action not in ("disable", "enable", "unload"):
        return None
    if not name:
        return None
    return name, action
