"""ThinkStack 自定义异常体系。

公开接口：ThinkStackError, ExtensionLoadError, ExtensionValidationError,
ExtensionAccessError, ConfigError, ToolError, MemoryError, SchedulerError, AgentError
"""

from __future__ import annotations


class ThinkStackError(Exception):
    """ThinkStack 框架异常基类。

    所有框架抛出的异常均继承自本类，便于调用方统一捕获与处理。
    """

    def __init__(self, message: str, *, code: str = "THINKSTACK_ERROR") -> None:
        self.code = code
        super().__init__(message)


class ConfigError(ThinkStackError):
    """配置错误，例如缺少必要字段或字段取值非法。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIG_ERROR")


class ToolError(ThinkStackError):
    """工具注册或调用相关错误。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="TOOL_ERROR")


class MemoryError(ThinkStackError):
    """记忆读写相关错误。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="MEMORY_ERROR")


class SchedulerError(ThinkStackError):
    """调度器分发相关错误。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SCHEDULER_ERROR")


class AgentError(ThinkStackError):
    """Agent 执行循环相关错误。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="AGENT_ERROR")


class ExtensionLoadError(ThinkStackError):
    """扩展加载失败（模块不存在、语法错误、初始化异常等）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="EXTENSION_LOAD_ERROR")


class ExtensionValidationError(ThinkStackError):
    """扩展校验失败（函数签名与钩子约定不匹配等）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="EXTENSION_VALIDATION_ERROR")


class ExtensionAccessError(ThinkStackError):
    """扩展越权访问框架私有成员。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="EXTENSION_ACCESS_ERROR")
