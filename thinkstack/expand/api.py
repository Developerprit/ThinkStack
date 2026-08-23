"""ThinkStack Expand API：扩展注册入口。

公开接口：expand_hook, register_extension, ExtensionRegistry, get_default_registry
"""

from __future__ import annotations

from typing import Callable

from thinkstack.errors import ExtensionLoadError
from thinkstack.expand.handle import ExtensionHandle
from thinkstack.expand.hooks import ExpandHook
from thinkstack.expand.loader import _HOOK_ATTR, ExtensionLoader

__all__ = [
    "expand_hook",
    "register_extension",
    "ExtensionRegistry",
    "get_default_registry",
]


def expand_hook(hook_point: ExpandHook) -> Callable[[Callable], Callable]:
    """将函数注册到指定扩展点的装饰器。

    用法：
        @expand_hook(ExpandHook.HOOK_BEFORE_THINK)
        def my_hook(ctx: dict) -> dict:
            ctx["my_flag"] = True
            return ctx

    被装饰函数会携带扩展点标记，供扩展加载器扫描识别。
    """

    def decorator(func: Callable) -> Callable:
        setattr(func, _HOOK_ATTR, hook_point)
        return func

    return decorator


class ExtensionRegistry:
    """扩展注册表：管理全部已加载扩展及其钩子。"""

    def __init__(self) -> None:
        self._loader = ExtensionLoader()
        self._extensions: dict[str, ExtensionHandle] = {}

    def register(self, name: str, module_path: str) -> ExtensionHandle:
        """动态加载扩展并返回句柄。

        名称重复时抛 ExtensionLoadError；加载失败仅影响该扩展。
        """
        if name in self._extensions:
            raise ExtensionLoadError(f"扩展 {name!r} 已注册，名称不可重复")
        handle = self._loader.load(name, module_path)
        self._extensions[name] = handle
        return handle

    def get(self, name: str) -> ExtensionHandle:
        """按名称获取扩展句柄，不存在抛 ExtensionLoadError。"""
        if name not in self._extensions:
            raise ExtensionLoadError(f"扩展 {name!r} 未注册")
        return self._extensions[name]

    def list_extensions(self) -> list[ExtensionHandle]:
        """返回全部扩展句柄列表。"""
        return list(self._extensions.values())

    def unload(self, name: str) -> None:
        """卸载并移除指定扩展。"""
        handle = self._extensions.pop(name, None)
        if handle is not None:
            handle.unload()

    def all_active_hooks(self) -> dict[str, list[Callable]]:
        """合并全部激活扩展的钩子，返回 {扩展点: [函数列表]}。"""
        merged: dict[str, list[Callable]] = {}
        for handle in self._extensions.values():
            for point, funcs in handle.get_hooks().items():
                merged.setdefault(point, []).extend(funcs)
        return merged

    def trigger_lifecycle(self, hook_point: ExpandHook, ctx: dict) -> dict:
        """触发生命周期钩子：按注册顺序逐个调用，单钩子异常被隔离。

        每个钩子签名约定为 func(ctx: dict) -> dict，可修改并返回上下文；
        返回 None 表示不修改上下文。
        """
        for func in self.all_active_hooks().get(hook_point.value, []):
            try:
                result = func(ctx)
                if result is not None:
                    ctx = result
            except Exception:
                # 单扩展异常不影响其他扩展与主流程，仅记录并继续。
                continue
        return ctx

    def collect_components(self, hook_point: ExpandHook) -> list:
        """触发组件钩子：收集各扩展返回的自定义组件实例。

        每个组件钩子签名约定为 func() -> Component；单钩子异常被隔离。
        """
        components: list = []
        for func in self.all_active_hooks().get(hook_point.value, []):
            try:
                component = func()
                if component is not None:
                    components.append(component)
            except Exception:
                continue
        return components


# 模块级默认注册表（供 register_extension 函数与独立使用场景）
_default_registry = ExtensionRegistry()


def register_extension(name: str, module_path: str) -> ExtensionHandle:
    """动态加载扩展并返回句柄（使用默认注册表）。"""
    return _default_registry.register(name, module_path)


def get_default_registry() -> ExtensionRegistry:
    """返回模块级默认注册表。"""
    return _default_registry
