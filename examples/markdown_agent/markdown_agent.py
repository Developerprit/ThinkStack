"""示例扩展 D：自定义 Agent（Markdown 渲染 Agent）。

演示 HOOK_CUSTOM_AGENT 扩展点：把自定义 Agent 类无缝接入框架，
任何人都可基于此编写自己的 Agent 应用。本示例把输入的 Markdown 渲染为 HTML。

公开接口：MarkdownRenderAgent, register_markdown_agent
"""

from __future__ import annotations

from typing import Any

from thinkstack import Agent, ExpandHook, expand_hook, markdown_to_html


class MarkdownRenderAgent(Agent):
    """把 Markdown 输入渲染为 HTML 的自定义 Agent。"""

    name = "markdown-render-agent"

    def think(self, context: dict[str, Any]) -> str:
        return str(context.get("input", ""))

    def act(self, thought: str) -> Any:
        return thought

    def observe(self, action: Any) -> Any:
        source = str(action)
        return {"markdown": source, "html": markdown_to_html(source)}


@expand_hook(ExpandHook.HOOK_CUSTOM_AGENT)
def register_markdown_agent() -> type:
    """向框架注册自定义 Agent 类。"""
    return MarkdownRenderAgent
