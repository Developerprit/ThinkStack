"""扩展句柄：管理单个已加载扩展的生命周期。

公开接口：ExtensionHandle
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, Callable

from thinkstack.errors import ExtensionAccessError


class ExtensionHandle:
    """扩展句柄。

    由 register_extension() 加载成功后返回，提供 enable()/disable()/unload()
    以及只读属性 is_active，用于运行时管理扩展。
    """

    def __init__(
        self,
        name: str,
        module_path: str,
        module: ModuleType,
        hooks: dict[str, list[Callable[..., Any]]],
    ) -> None:
        self.name = name
        self.module_path = module_path
        self.module = module
        self._hooks = hooks
        self._active = True
        self._loaded = True

    @property
    def is_active(self) -> bool:
        """扩展是否处于激活状态（只读）。"""
        return self._active and self._loaded

    @property
    def hook_points(self) -> list[str]:
        """该扩展挂载的全部扩展点。"""
        return list(self._hooks.keys())

    def enable(self) -> None:
        """激活扩展（重新参与钩子触发）。"""
        if not self._loaded:
            raise ExtensionAccessError(f"扩展 {self.name!r} 已卸载，无法重新启用")
        self._active = True

    def disable(self) -> None:
        """停用扩展（保留加载，但不再触发其钩子）。"""
        self._active = False

    def unload(self) -> None:
        """卸载扩展：从 sys.modules 移除模块并释放引用。"""
        if not self._loaded:
            return
        self._active = False
        self._loaded = False
        self._hooks.clear()
        # 模块加载时以 name 为键写入 sys.modules，卸载需用 name 移除
        sys.modules.pop(self.name, None)
        self.module = None  # type: ignore[assignment]

    def get_hooks(self) -> dict[str, list[Callable[..., Any]]]:
        """返回扩展当前生效的钩子映射（停用后返回空）。"""
        if not self.is_active:
            return {}
        return self._hooks

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        state = "active" if self.is_active else ("disabled" if self._loaded else "unloaded")
        return f"<ExtensionHandle name={self.name!r} state={state}>"
