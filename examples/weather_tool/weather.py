"""示例扩展 A：天气查询工具。

演示工具注册、Pydantic 参数校验与调用。
通过 HOOK_CUSTOM_TOOL 扩展点向框架注册一个 weather 工具。

公开接口：WeatherInput, register_weather_tool
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from thinkstack import ExpandHook, FunctionTool, expand_hook

# 内置模拟天气数据
_WEATHER_DATA = {
    "北京": "晴，25°C，东风 2 级",
    "上海": "多云，28°C，东南风 3 级",
    "深圳": "阵雨，30°C，西南风 2 级",
    "广州": "雷阵雨，31°C，南风 3 级",
}


class WeatherInput(BaseModel):
    """天气查询入参。"""

    city: str = Field(description="城市名称，例如：北京")


def _query_weather(city: str) -> str:
    """查询城市天气（模拟实现）。"""
    return _WEATHER_DATA.get(city, f"{city} 暂无天气数据，请稍后重试")


@expand_hook(ExpandHook.HOOK_CUSTOM_TOOL)
def register_weather_tool() -> FunctionTool:
    """向框架注册 weather 工具。"""
    return FunctionTool(
        name="weather",
        description="查询指定城市的实时天气",
        input_schema=WeatherInput,
        func=_query_weather,
    )
