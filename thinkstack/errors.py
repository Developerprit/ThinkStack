"""ThinkStack 自定义异常体系。

公开接口：ThinkStackError, ExtensionLoadError, ExtensionValidationError,
ExtensionAccessError, ConfigError, ToolError, MemoryError, SchedulerError, AgentError,
TSStatusError, ts_status, TS_CODE_* 状态码常量。
"""

from __future__ import annotations

# ---------------------------------------------------------------- TS 状态码
# 状态码定义见 E:/PC/error.txt：架构自检/错误处理统一以
# "TS error :<code>" / "TS ok :<code>" 形式对外返回。
TS_CODE_EXT_API_ERROR = 1001  # 扩展API错误（API本身错误）
TS_CODE_EXT_ERROR = 1002      # 扩展错误
TS_CODE_OK = 2000             # OK,没问题
TS_CODE_LLM_TOKEN_EXHAUSTED = 3001  # LLM的token用没了
TS_CODE_URL_404 = 3002        # URL 404
TS_CODE_MODEL_404 = 3003      # 模型ID 404
TS_CODE_KEY_ERROR = 3004      # key错误
TS_CODE_TS_ERROR = 3005       # TS错误
TS_CODE_TS_LOST = 3404        # TS意外丢失
TS_CODE_BLACKHOLE = 4000      # 消息发进了黑洞
TS_CODE_UNKNOWN = 8000        # 未知错误

# 状态码 → 中文描述（与 error.txt 保持一致）
TS_CODE_MESSAGES: dict[int, str] = {
    TS_CODE_EXT_API_ERROR: "扩展API错误（API本身错误）",
    TS_CODE_EXT_ERROR: "扩展错误",
    TS_CODE_OK: "OK,没问题",
    TS_CODE_LLM_TOKEN_EXHAUSTED: "LLM的token用没了",
    TS_CODE_URL_404: "URL 404",
    TS_CODE_MODEL_404: "模型ID 404",
    TS_CODE_KEY_ERROR: "key错误",
    TS_CODE_TS_ERROR: "TS错误",
    TS_CODE_TS_LOST: "TS意外丢失",
    TS_CODE_BLACKHOLE: "消息发进了黑洞",
    TS_CODE_UNKNOWN: "未知错误",
}


def ts_status(code: int) -> str:
    """生成 TS 状态字符串。

    - 通过（2000）：`TS ok :2000`
    - 失败（其余）：`TS error :<code>`

    例如 `ts_status(1002)` 返回 `"TS error :1002"`。
    """
    if code == TS_CODE_OK:
        return f"TS ok :{code}"
    return f"TS error :{code}"


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


class TSStatusError(ThinkStackError):
    """携带 TS 状态码的框架错误。

    架构自检或运行时错误可抛出本异常，调用方通过 `exc.ts_code`
    获取状态码，用 `ts_status(exc.ts_code)` 生成对外返回的
    "TS error :<code>" 字符串。
    """

    def __init__(self, message: str, *, ts_code: int = TS_CODE_TS_ERROR) -> None:
        self.ts_code = ts_code
        super().__init__(message, code=f"TS_{ts_code}")
