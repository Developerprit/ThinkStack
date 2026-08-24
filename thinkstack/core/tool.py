"""工具注册表与调用机制。

公开接口：ToolResult, Tool, FunctionTool, ToolRegistry, tool, EmptyInput
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from thinkstack.errors import ToolError


class EmptyInput(BaseModel):
    """空输入模型，用于无参数工具。"""

    model_config = {"extra": "forbid"}


class ToolResult(BaseModel):
    """工具调用结果封装。"""

    success: bool = Field(description="调用是否成功")
    data: Any = Field(default=None, description="返回数据")
    error: Optional[str] = Field(default=None, description="错误信息（失败时非空）")

    @classmethod
    def ok(cls, data: Any = None) -> "ToolResult":
        """构造成功结果。"""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        """构造失败结果。"""
        return cls(success=False, error=error)


class Tool(ABC):
    """工具抽象基类。

    子类需提供：name、description、input_schema（Pydantic 模型），
    并实现 run()（同步）或 arun()（异步）方法。
    """

    name: str = ""
    description: str = ""
    input_schema: type[BaseModel] = EmptyInput
    is_async: bool = False

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """同步执行工具逻辑，返回任意可序列化结果。"""
        raise NotImplementedError

    async def arun(self, **kwargs: Any) -> Any:
        """异步执行工具逻辑，默认委托给同步 run()。"""
        return self.run(**kwargs)

    def validate_args(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """使用 input_schema 对入参做 Pydantic 校验，返回规范化后的字典。"""
        try:
            model = self.input_schema(**kwargs)
        except Exception as exc:  # Pydantic 校验异常统一转 ToolError
            raise ToolError(f"工具 {self.name!r} 参数校验失败：{exc}") from exc
        return model.model_dump()


class FunctionTool(Tool):
    """函数型工具：把普通同步/异步函数包装为 Tool。"""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        input_schema: type[BaseModel] = EmptyInput,
        is_async: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.is_async = is_async
        self._func = func

    def run(self, **kwargs: Any) -> Any:
        if self.is_async:
            raise ToolError(f"异步工具 {self.name!r} 请通过 await 调用")
        return self._func(**kwargs)

    async def arun(self, **kwargs: Any) -> Any:
        if not self.is_async:
            return self._func(**kwargs)
        return await self._func(**kwargs)


class ToolRegistry:
    """工具注册表：负责工具注册、查询与调用。

    支持同步/异步工具统一入口，自动做参数校验与结果封装。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具，名称重复时抛 ToolError。"""
        if not isinstance(tool, Tool):
            raise ToolError("register() 仅接受 Tool 实例")
        if not tool.name:
            raise ToolError("工具必须提供非空 name")
        if tool.name in self._tools:
            raise ToolError(f"工具 {tool.name!r} 已注册，名称不可重复")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """按名称获取工具，不存在则抛 ToolError。"""
        try:
            return self._tools[name]
        except KeyError:
            raise ToolError(f"工具 {name!r} 未注册") from None

    def list_tools(self) -> list[dict[str, Any]]:
        """返回全部工具的基本信息列表。"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "is_async": t.is_async,
                "schema": t.input_schema.model_json_schema(),
            }
            for t in self._tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        """同步调用工具，自动校验参数并封装结果。"""
        try:
            tool = self.get(name)
            validated = tool.validate_args(kwargs)
            data = tool.run(**validated)
            return ToolResult.ok(data)
        except Exception as exc:
            return ToolResult.fail(str(exc))

    async def acall(self, name: str, **kwargs: Any) -> ToolResult:
        """异步调用工具，自动校验参数并封装结果。"""
        try:
            tool = self.get(name)
            validated = tool.validate_args(kwargs)
            data = await tool.arun(**validated)
            return ToolResult.ok(data)
        except Exception as exc:
            return ToolResult.fail(str(exc))


def tool(
    name: Optional[str] = None,
    description: str = "",
    input_schema: type[BaseModel] = EmptyInput,
    is_async: bool = False,
) -> Callable[[Callable[..., Any]], FunctionTool]:
    """将普通函数包装为 FunctionTool 的装饰器。

    用法：
        @tool(name="weather", description="查询天气", input_schema=WeatherInput)
        def weather(city: str) -> str:
            ...
    """

    def decorator(func: Callable[..., Any]) -> FunctionTool:
        func_name = name or func.__name__
        return FunctionTool(
            name=func_name,
            description=description,
            func=func,
            input_schema=input_schema,
            is_async=is_async,
        )

    return decorator
