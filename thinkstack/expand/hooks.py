"""扩展点枚举定义。

公开接口：ExpandHook
"""

from __future__ import annotations

from enum import Enum


class ExpandHook(str, Enum):
    """ThinkStack 扩展点枚举。

    扩展通过 @expand_hook 装饰器将函数挂载到以下某一扩展点，
    框架在对应生命周期节点按注册顺序触发。
    """

    HOOK_BEFORE_THINK = "hook_before_think"
    HOOK_AFTER_THINK = "hook_after_think"
    HOOK_BEFORE_ACTION = "hook_before_action"
    HOOK_AFTER_ACTION = "hook_after_action"
    HOOK_BEFORE_OBSERVE = "hook_before_observe"
    HOOK_AFTER_OBSERVE = "hook_after_observe"
    HOOK_CUSTOM_TOOL = "hook_custom_tool"
    HOOK_CUSTOM_MEMORY = "hook_custom_memory"
    HOOK_CUSTOM_SCHEDULER = "hook_custom_scheduler"
