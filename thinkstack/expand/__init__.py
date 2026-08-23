"""ThinkStack 扩展接口层（Expand API Layer）。

公开接口：ExpandHook, expand_hook, register_extension, ExtensionHandle,
ExtensionRegistry, ExtensionLoader, get_default_registry
"""

from thinkstack.expand.api import (
    ExtensionRegistry,
    expand_hook,
    get_default_registry,
    register_extension,
)
from thinkstack.expand.handle import ExtensionHandle
from thinkstack.expand.hooks import ExpandHook
from thinkstack.expand.loader import ExtensionLoader

__all__ = [
    "ExpandHook",
    "expand_hook",
    "register_extension",
    "ExtensionHandle",
    "ExtensionRegistry",
    "ExtensionLoader",
    "get_default_registry",
]
