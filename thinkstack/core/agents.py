"""内置示例 Agent 实现。

公开接口：EchoAgent, ToolCallingAgent, MarkdownAgent
"""

from __future__ import annotations

from typing import Any, Optional

from thinkstack.core.agent import Agent
from thinkstack.core.markdown import markdown_to_html


class EchoAgent(Agent):
    """回显 Agent：思考后原样行动，用于跑通循环与演示。

    不依赖任何模型，think 委托 reasoner，act 原样返回思考结果。
    """

    name = "echo-agent"

    def think(self, context: dict[str, Any]) -> str:
        instruction = str(context.get("input", ""))
        return self.reasoner.reason({"input": instruction}, instruction)

    def act(self, thought: str) -> Any:
        return thought

    def observe(self, action: Any) -> Any:
        return {"result": action}


class ToolCallingAgent(Agent):
    """工具调用 Agent：支持从思考文本中解析工具调用指令。

    思考文本约定为 `tool:工具名 key=value ...` 形式；若无法解析则原样返回。
    通过上下文中的 "stack" 引用访问工具注册表。
    """

    name = "tool-calling-agent"

    def think(self, context: dict[str, Any]) -> str:
        # 工具调用 Agent 的输入本身即为 `tool:名称 参数` 指令，直接透传解析。
        return str(context.get("input", ""))

    def act(self, thought: str) -> Any:
        stack = getattr(self, "_stack", None)
        if stack is None or not thought.startswith("tool:"):
            return thought
        body = thought[len("tool:") :].strip()
        return {"type": "tool_call", "spec": body}

    def observe(self, action: Any) -> Any:
        if not isinstance(action, dict) or action.get("type") != "tool_call":
            return {"result": action}
        stack = getattr(self, "_stack", None)
        if stack is None:
            return {"result": action, "error": "无可用框架上下文"}
        # 解析 "tool:name key=value ..." 并执行
        parts = action["spec"].split()
        if not parts:
            return {"result": None, "error": "空工具指令"}
        tool_name = parts[0]
        kwargs: dict[str, Any] = {}
        for item in parts[1:]:
            if "=" in item:
                key, value = item.split("=", 1)
                kwargs[key] = value
        result = stack.call_tool(tool_name, **kwargs)
        return {"result": result.model_dump()}


class MarkdownAgent(Agent):
    """Markdown 渲染 Agent：把输入的 Markdown 文本渲染为 HTML。

    面向 LLM 输出多为 Markdown 的场景，think 透传输入，
    observe 使用内置 markdown_to_html 转换后返回 HTML。
    """

    name = "markdown-agent"

    def think(self, context: dict[str, Any]) -> str:
        return str(context.get("input", ""))

    def act(self, thought: str) -> Any:
        return thought

    def observe(self, action: Any) -> Any:
        source = str(action)
        return {"markdown": source, "html": markdown_to_html(source)}
