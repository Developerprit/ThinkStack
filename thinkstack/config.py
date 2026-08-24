"""ThinkStack 统一配置入口。

公开接口：Config, MemoryConfig, SchedulerConfig, ServerConfig, LogConfig
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from thinkstack.errors import ConfigError


class MemoryConfig(BaseModel):
    """记忆子系统配置。"""

    short_term_capacity: int = Field(default=100, ge=1, description="短期记忆最大条数")
    long_term_backend: Literal["in_memory", "json_file"] = Field(
        default="in_memory", description="长期记忆后端：in_memory / json_file"
    )
    persist_path: str = Field(default="", description="长期记忆持久化路径（json_file 后端使用）")


class SchedulerConfig(BaseModel):
    """调度器配置。"""

    strategy: Literal["serial", "parallel", "priority"] = Field(
        default="serial", description="调度策略：serial / parallel / priority"
    )
    max_workers: int = Field(default=4, ge=1, le=64, description="并行调度最大工作线程数")


class ServerConfig(BaseModel):
    """HTTP 服务器配置。"""

    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=9635, ge=1, le=65535, description="REST API 监听端口")
    enable_console_command: bool = Field(
        default=True, description="是否允许通过命令通道开启 Web 控制台"
    )


class LogConfig(BaseModel):
    """日志配置。"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="日志级别"
    )
    file: str = Field(default="", description="日志文件路径（为空则仅输出到控制台）")


class Config(BaseModel):
    """ThinkStack 顶层配置数据类。

    汇聚框架运行所需的全部可配置项，作为统一配置入口传入 ThinkStack 主类。
    """

    name: str = Field(default="ThinkStack", description="框架实例名称")
    agent_name: str = Field(default="default-agent", description="默认 Agent 名称")
    max_iterations: int = Field(
        default=10, ge=1, le=1000, description="Agent「思考→行动→观察」循环最大迭代次数"
    )
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    log: LogConfig = Field(default_factory=LogConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """从字典构造配置对象，非法字段将抛 ConfigError。"""
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"配置校验失败：{exc}") from exc
