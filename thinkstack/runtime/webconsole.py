"""ThinkStack Web 控制台（通过 `webrun <port>` 命令动态开启）。

公开接口：WebConsole
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from thinkstack.core.stack import ThinkStack
from thinkstack.core.markdown import markdown_to_html
from thinkstack.core.tool import ToolResult
from thinkstack.runtime.server import BUILTIN_AGENTS

_HTML_PATH = os.path.join(os.path.dirname(__file__), "console.html")


class WebConsole:
    """独立的 Web 控制台服务器，内置浅色/深色可切换的管理界面。"""

    def __init__(self, stack: ThinkStack, host: str = "0.0.0.0", port: int = 8080) -> None:
        self.stack = stack
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None

    def start(self, block: bool = False) -> None:
        """启动控制台；block=True 时阻塞，否则后台线程运行。"""
        stack = self.stack

        class Handler(BaseHTTPRequestHandler):
            server_version = "ThinkStack-Console/1.0"

            def _send_json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self) -> None:
                with open(_HTML_PATH, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length <= 0:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    return {}

            def do_GET(self) -> None:
                from urllib.parse import urlparse

                path = urlparse(self.path).path
                if path == "/" or path == "/index.html":
                    return self._send_html()
                if path == "/api/info":
                    return self._send_json(200, self._info())
                if path == "/api/tools":
                    return self._send_json(200, {"tools": stack.list_tools()})
                if path == "/api/extensions":
                    return self._send_json(200, self._extensions())
                self._send_json(404, {"error": "未找到"})

            def do_POST(self) -> None:
                from urllib.parse import urlparse

                path = urlparse(self.path).path
                if path == "/api/agent/run":
                    data = self._read_json()
                    agent_cls = BUILTIN_AGENTS.get(data.get("agent", "echo"))
                    if agent_cls is None:
                        return self._send_json(400, {"error": "未知 agent"})
                    result = stack.run_agent(
                        agent_cls(), data.get("input", ""), data.get("max_iterations")
                    )
                    return self._send_json(200, result.model_dump())
                if path == "/api/tools/call":
                    data = self._read_json()
                    result: ToolResult = stack.call_tool(
                        data.get("name", ""), **(data.get("args", {}) or {})
                    )
                    return self._send_json(200, result.model_dump())
                if path == "/api/markdown/render":
                    data = self._read_json()
                    text = data.get("text", "") if isinstance(data, dict) else str(data)
                    return self._send_json(200, {"html": markdown_to_html(text)})
                self._send_json(404, {"error": "未找到"})

            def _info(self) -> dict[str, Any]:
                return {
                    "name": stack.config.name,
                    "running": stack.is_running,
                    "tool_count": len(stack.list_tools()),
                    "extension_count": len(stack.list_extensions()),
                    "scheduler": stack.config.scheduler.strategy,
                    "max_iterations": stack.config.max_iterations,
                }

            def _extensions(self) -> dict[str, Any]:
                return {
                    "extensions": [
                        {"name": h.name, "is_active": h.is_active, "hooks": h.hook_points}
                        for h in stack.list_extensions()
                    ]
                }

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        if block:
            self._httpd.serve_forever()
        else:
            thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            thread.start()

    def shutdown(self) -> None:
        """停止控制台。"""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
