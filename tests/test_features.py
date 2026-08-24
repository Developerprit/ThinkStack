"""test_features.py —— 覆盖新增能力：Markdown 渲染、自定义 Agent、JSON 文件记忆、
流式循环、配置校验、REST 新端点。"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

from thinkstack import (
    Agent,
    Config,
    ConfigError,
    MarkdownAgent,
    ThinkStack,
    ThinkStackServer,
    markdown_to_html,
)

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
MARKDOWN_AGENT_PATH = os.path.join(EXAMPLES_DIR, "markdown_agent", "markdown_agent.py")


# ---------------------------------------------------------------- Markdown 渲染

def test_markdown_heading_bold_code():
    out = markdown_to_html("# 标题\n\n**加粗** 和 `代码`")
    assert "<h1>标题</h1>" in out
    assert "<strong>加粗</strong>" in out
    assert "<code>代码</code>" in out


def test_markdown_list_link_quote_table():
    md = "- 一\n- 二\n\n[链接](http://a.com)\n\n> 引用\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    out = markdown_to_html(md)
    assert "<li>一</li>" in out
    assert '<a href="http://a.com">链接</a>' in out
    assert "<blockquote>" in out
    assert "<table>" in out
    assert "<td>1</td>" in out
    assert "<td>---</td>" not in out  # 分隔行不应作为数据行


def test_markdown_escapes_raw_html():
    out = markdown_to_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_markdown_tool_and_agent():
    stack = ThinkStack()
    stack.start()
    result = stack.call_tool("markdown", text="**hi**")
    assert result.success and "<strong>hi</strong>" in result.data

    res = stack.run_agent(MarkdownAgent(), "# Hi", max_iterations=1)
    assert "<h1>Hi</h1>" in res.output["html"]


# ---------------------------------------------------------------- 自定义 Agent

def test_register_and_resolve_agent():
    class HelloAgent(Agent):
        name = "hello-agent"

        def think(self, context):
            return str(context.get("input", ""))

        def act(self, thought):
            return thought

        def observe(self, action):
            return {"greeting": f"hello {action}"}

    stack = ThinkStack()
    stack.register_agent("hello", HelloAgent)
    agent = stack.resolve_agent("hello")
    assert agent is not None
    res = stack.run_agent(agent, "world", max_iterations=1)
    assert res.output["greeting"] == "hello world"


def test_custom_agent_extension():
    stack = ThinkStack()
    stack.register_extension("markdown_agent", MARKDOWN_AGENT_PATH)
    stack.start()
    assert "markdown-render-agent" in stack.list_agents()
    agent = stack.resolve_agent("markdown-render-agent")
    res = stack.run_agent(agent, "# T", max_iterations=1)
    assert "<h1>T</h1>" in res.output["html"]


# ---------------------------------------------------------------- JSON 文件记忆

def test_json_file_long_term_memory(tmp_path):
    path = str(tmp_path / "mem.json")
    s1 = ThinkStack(
        Config.from_dict({"memory": {"long_term_backend": "json_file", "persist_path": path}})
    )
    s1.store_long_term("user", {"name": "陌老师"})
    s1.long_term_memory.save()

    s2 = ThinkStack(
        Config.from_dict({"memory": {"long_term_backend": "json_file", "persist_path": path}})
    )
    assert s2.retrieve_long_term("user") == {"name": "陌老师"}


# ---------------------------------------------------------------- 流式循环

def test_run_agent_stream():
    stack = ThinkStack()
    steps = list(stack.run_agent_stream(MarkdownAgent(), "# A", max_iterations=2))
    assert len(steps) == 2
    assert steps[0]["iteration"] == 1
    assert "<h1>A</h1>" in steps[0]["observation"]["html"]


# ---------------------------------------------------------------- 配置校验

def test_config_from_dict_invalid_raises():
    try:
        Config.from_dict({"memory": {"long_term_backend": "invalid_backend"}})
        assert False, "应抛出 ConfigError"
    except ConfigError:
        pass


# ---------------------------------------------------------------- REST 新端点

class _Server:
    """在临时端口启动 ThinkStackServer 的测试辅助。"""

    def __init__(self):
        self.stack = ThinkStack()
        self.stack.register_extension("markdown_agent", MARKDOWN_AGENT_PATH)
        self.stack.start()
        self.server = ThinkStackServer(self.stack, host="127.0.0.1", port=0)
        self.server.start(block=False)
        self.port = self.server._httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"

    def post(self, path: str, obj: dict) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(urllib.request.urlopen(req).read().decode())

    def get(self, path: str) -> dict:
        return json.loads(urllib.request.urlopen(self.base + path).read().decode())

    def close(self):
        self.server.shutdown()
        self.stack.shutdown()


def test_rest_memory_markdown_agents():
    s = _Server()
    try:
        # 记忆 CRUD
        assert s.post("/api/memory", {"action": "store", "kind": "working", "key": "n", "value": 7})["ok"] is True
        assert s.post("/api/memory", {"action": "retrieve", "kind": "working", "key": "n"})["value"] == 7
        # Markdown 渲染
        html = s.post("/api/markdown/render", {"text": "**x**"})["html"]
        assert "<strong>x</strong>" in html
        # 自定义 Agent 列表与运行
        assert "markdown-render-agent" in s.get("/api/agents")["custom"]
        res = s.post("/api/agent/run", {"agent": "markdown-render-agent", "input": "# H", "max_iterations": 1})
        assert "<h1>H</h1>" in res["output"]["html"]
    finally:
        s.close()


def test_rest_agent_stream_sse():
    s = _Server()
    try:
        req = urllib.request.Request(
            s.base + "/api/agent/run/stream",
            data=json.dumps({"agent": "echo", "input": "hi", "max_iterations": 2}).encode(),
            headers={"Content-Type": "application/json"},
        )
        body = urllib.request.urlopen(req).read().decode()
        # 2 个步骤事件 + 1 个 done 事件，每个都带 data: 字段
        assert '"iteration": 1' in body
        assert '"iteration": 2' in body
        assert "event: done" in body
    finally:
        s.close()
