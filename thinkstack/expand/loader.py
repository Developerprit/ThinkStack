"""扩展加载器：动态加载、签名校验与异常隔离。

公开接口：ExtensionLoader, LIFECYCLE_HOOKS, COMPONENT_HOOKS
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from types import ModuleType
from typing import Any, Callable

from thinkstack.errors import ExtensionLoadError, ExtensionValidationError
from thinkstack.expand.handle import ExtensionHandle
from thinkstack.expand.hooks import ExpandHook

# 钩子函数上的标记属性名
_HOOK_ATTR = "_thinkstack_hook"

# 生命周期钩子：围绕 Agent 循环，签名为 func(ctx: dict) -> dict
LIFECYCLE_HOOKS: frozenset[ExpandHook] = frozenset(
    {
        ExpandHook.HOOK_BEFORE_THINK,
        ExpandHook.HOOK_AFTER_THINK,
        ExpandHook.HOOK_BEFORE_ACTION,
        ExpandHook.HOOK_AFTER_ACTION,
        ExpandHook.HOOK_BEFORE_OBSERVE,
        ExpandHook.HOOK_AFTER_OBSERVE,
    }
)

# 组件钩子：注册自定义组件，签名为 func() -> Component（无必需参数）
COMPONENT_HOOKS: frozenset[ExpandHook] = frozenset(
    {
        ExpandHook.HOOK_CUSTOM_TOOL,
        ExpandHook.HOOK_CUSTOM_MEMORY,
        ExpandHook.HOOK_CUSTOM_SCHEDULER,
        ExpandHook.HOOK_CUSTOM_AGENT,
    }
)


def _count_required_params(func: Callable[..., Any]) -> int:
    """统计函数必需的位置参数数量。"""
    sig = inspect.signature(func)
    required = 0
    for param in sig.parameters.values():
        if param.default is inspect.Parameter.empty and param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            required += 1
    return required


def validate_hook_signature(func: Callable[..., Any], hook_point: ExpandHook) -> None:
    """校验钩子函数签名是否匹配钩子点约定，不符抛 ExtensionValidationError。"""
    if not callable(func):
        raise ExtensionValidationError(f"钩子 {hook_point.value} 挂载的对象不可调用")
    required = _count_required_params(func)
    if hook_point in LIFECYCLE_HOOKS and required != 1:
        raise ExtensionValidationError(
            f"生命周期钩子 {hook_point.value} 的函数 {func.__name__!r} "
            f"签名应为 func(ctx) -> dict，但检测到 {required} 个必需参数"
        )
    if hook_point in COMPONENT_HOOKS and required > 0:
        raise ExtensionValidationError(
            f"组件钩子 {hook_point.value} 的函数 {func.__name__!r} "
            f"签名应为 func() -> Component，但检测到 {required} 个必需参数"
        )


class ExtensionLoader:
    """扩展加载器。

    使用 importlib 安全加载扩展模块（严禁 eval/exec/__import__），
    扫描 @expand_hook 标记的函数并校验签名，单个扩展失败不影响框架。
    """

    def load(self, name: str, module_path: str) -> ExtensionHandle:
        """加载指定路径的扩展模块并返回句柄。

        任何加载/初始化异常都会被捕获并转换为 ExtensionLoadError。
        """
        if not module_path:
            raise ExtensionLoadError(f"扩展 {name!r} 未提供 module_path")
        try:
            spec = importlib.util.spec_from_file_location(name, module_path)
            if spec is None or spec.loader is None:
                raise ExtensionLoadError(f"无法为 {module_path!r} 生成加载规格")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except ExtensionLoadError:
            sys.modules.pop(name, None)
            raise
        except Exception as exc:
            sys.modules.pop(name, None)
            raise ExtensionLoadError(
                f"扩展 {name!r} 加载失败：{type(exc).__name__}: {exc}"
            ) from exc

        try:
            hooks = self._collect_hooks(module)
        except ExtensionValidationError:
            sys.modules.pop(name, None)
            raise
        except Exception as exc:
            sys.modules.pop(name, None)
            raise ExtensionLoadError(
                f"扩展 {name!r} 初始化失败：{type(exc).__name__}: {exc}"
            ) from exc

        return ExtensionHandle(name=name, module_path=module_path, module=module, hooks=hooks)

    def _collect_hooks(self, module: ModuleType) -> dict[str, list[Callable[..., Any]]]:
        """扫描模块中带 @expand_hook 标记的函数，按扩展点归组并校验签名。"""
        hooks: dict[str, list[Callable[..., Any]]] = {}
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            try:
                obj = getattr(module, attr_name)
            except Exception:
                continue
            if not callable(obj):
                continue
            hook_point = getattr(obj, _HOOK_ATTR, None)
            if hook_point is None or not isinstance(hook_point, ExpandHook):
                continue
            validate_hook_signature(obj, hook_point)
            hooks.setdefault(hook_point.value, []).append(obj)
        return hooks
