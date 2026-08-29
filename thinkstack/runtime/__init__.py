"""ThinkStack 运行时层（Runtime Layer）。

公开接口：ThinkStackServer, BUILTIN_AGENTS

v1.3.0 起框架不再自带 Web 控制台 —— Web UI 由各 Agent 应用自行铺设，
运行时层仅保留 JSON REST API。
"""

from thinkstack.runtime.server import BUILTIN_AGENTS, ThinkStackServer

__all__ = ["ThinkStackServer", "BUILTIN_AGENTS"]
