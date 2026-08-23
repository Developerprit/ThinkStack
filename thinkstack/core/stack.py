"""ThinkStack 主入口类：生命周期管理与组件编排。

公开接口：ThinkStack
"""

from __future__ import annotations

from typing import Any, Optional

from thinkstack.config import Config
from thinkstack.core.agent import Agent, AgentResult
from thinkstack.core.memory import (
    InMemoryLongTermMemory,
    LongTermMemory,
    ShortTermMemory,
    WorkingMemory,
)
from thinkstack.core.scheduler import (
    ParallelScheduler,
    PriorityScheduler,
    Scheduler,
    SerialScheduler,
    Task,
    TaskResult,
)
from thinkstack.core.tool import Tool, ToolRegistry, ToolResult
from thinkstack.errors import SchedulerError, ThinkStackError
from thinkstack.expand.api import ExtensionRegistry
from thinkstack.expand.handle import ExtensionHandle
from thinkstack.expand.hooks import ExpandHook


class ThinkStack:
    """ThinkStack Agent 框架主入口。

    聚合工具注册表、三类记忆、调度器、扩展注册表与 Agent 执行循环，
    对外提供统一的生命周期管理（__init__ / start / shutdown）。
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config: Config = config or Config()
        self._registry = ExtensionRegistry()
        self.tools = ToolRegistry()

        self.short_term_memory = ShortTermMemory(capacity=self.config.memory.short_term_capacity)
        self.working_memory = WorkingMemory()
        self.long_term_memory: LongTermMemory = InMemoryLongTermMemory()

        self.scheduler: Scheduler = self._build_scheduler()
        self.custom_schedulers: list[Scheduler] = []

        self._started = False

    # ------------------------------------------------------------------ 生命周期

    def start(self) -> None:
        """启动框架：应用组件扩展（自定义工具/记忆/调度器）。"""
        self._started = True
        self._apply_component_extensions()

    def shutdown(self) -> None:
        """关闭框架：持久化长期记忆并标记停止。"""
        if not self._started:
            return
        try:
            self.long_term_memory.save()
        except Exception:
            pass
        self._started = False

    @property
    def is_running(self) -> bool:
        """框架是否处于运行状态。"""
        return self._started

    # ------------------------------------------------------------------ 工具

    def register_tool(self, tool: Tool) -> None:
        """注册一个工具到注册表。"""
        self.tools.register(tool)

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        """同步调用工具并返回结果封装。"""
        return self.tools.call(name, **kwargs)

    async def acall_tool(self, name: str, **kwargs: Any) -> ToolResult:
        """异步调用工具并返回结果封装。"""
        return await self.tools.acall(name, **kwargs)

    def list_tools(self) -> list[dict[str, Any]]:
        """列出全部已注册工具的基本信息。"""
        return self.tools.list_tools()

    # ------------------------------------------------------------------ 记忆

    def store_short_term(self, key: str, value: Any) -> None:
        """写入短期记忆。"""
        self.short_term_memory.store(key, value)

    def retrieve_short_term(self, key: str, default: Any = None) -> Any:
        """读取短期记忆。"""
        return self.short_term_memory.retrieve(key, default)

    def store_long_term(self, key: str, value: Any) -> None:
        """写入长期记忆。"""
        self.long_term_memory.store(key, value)

    def retrieve_long_term(self, key: str, default: Any = None) -> Any:
        """读取长期记忆。"""
        return self.long_term_memory.retrieve(key, default)

    def store_working(self, key: str, value: Any) -> None:
        """写入工作记忆。"""
        self.working_memory.store(key, value)

    def retrieve_working(self, key: str, default: Any = None) -> Any:
        """读取工作记忆。"""
        return self.working_memory.retrieve(key, default)

    # ------------------------------------------------------------------ 调度

    def submit_task(self, task: Task) -> None:
        """提交任务到当前调度器。"""
        self.scheduler.submit(task)

    def run_tasks(self) -> list[TaskResult]:
        """执行当前调度器中的全部任务并返回结果。"""
        return self.scheduler.run_all()

    # ------------------------------------------------------------------ 扩展

    def register_extension(self, name: str, module_path: str) -> ExtensionHandle:
        """动态加载并注册一个扩展，返回句柄。"""
        handle = self._registry.register(name, module_path)
        if self._started:
            self._apply_component_extensions()
        return handle

    def list_extensions(self) -> list[ExtensionHandle]:
        """列出全部已注册扩展。"""
        return self._registry.list_extensions()

    # ------------------------------------------------------------------ Agent

    def run_agent(
        self, agent: Agent, task_input: Any, max_iterations: Optional[int] = None
    ) -> AgentResult:
        """执行 Agent「思考→行动→观察」循环，并在各阶段触发扩展钩子。"""
        max_iter = max_iterations or self.config.max_iterations
        if max_iter < 1:
            raise ThinkStackError("max_iterations 必须为正整数")

        setattr(agent, "_stack", self)
        ctx: dict[str, Any] = {"input": task_input, "stack": self}
        history: list[dict[str, Any]] = []
        output: Any = None

        for i in range(1, max_iter + 1):
            ctx = self._registry.trigger_lifecycle(ExpandHook.HOOK_BEFORE_THINK, ctx)
            thought = agent.think(ctx)
            ctx["thought"] = thought
            ctx = self._registry.trigger_lifecycle(ExpandHook.HOOK_AFTER_THINK, ctx)

            ctx = self._registry.trigger_lifecycle(ExpandHook.HOOK_BEFORE_ACTION, ctx)
            action = agent.act(ctx["thought"])
            ctx["action"] = action
            ctx = self._registry.trigger_lifecycle(ExpandHook.HOOK_AFTER_ACTION, ctx)

            ctx = self._registry.trigger_lifecycle(ExpandHook.HOOK_BEFORE_OBSERVE, ctx)
            observation = agent.observe(ctx["action"])
            ctx["observation"] = observation
            ctx = self._registry.trigger_lifecycle(ExpandHook.HOOK_AFTER_OBSERVE, ctx)

            history.append(
                {
                    "iteration": i,
                    "thought": ctx["thought"],
                    "action": ctx["action"],
                    "observation": ctx["observation"],
                }
            )
            output = ctx["observation"]
            if agent.should_stop(ctx["observation"]):
                break

        return AgentResult(success=True, output=output, iterations=len(history), history=history)

    # ------------------------------------------------------------------ 内部

    def _build_scheduler(self) -> Scheduler:
        """根据配置构建调度器实例。"""
        strategy = self.config.scheduler.strategy
        if strategy == "serial":
            return SerialScheduler()
        if strategy == "parallel":
            return ParallelScheduler(max_workers=self.config.scheduler.max_workers)
        if strategy == "priority":
            return PriorityScheduler()
        raise SchedulerError(f"未知调度策略 {strategy!r}")

    def _apply_component_extensions(self) -> None:
        """应用组件扩展：自定义工具注册、自定义记忆/调度器接入。"""
        for tool in self._registry.collect_components(ExpandHook.HOOK_CUSTOM_TOOL):
            try:
                self.tools.register(tool)
            except Exception:
                continue
        memories = self._registry.collect_components(ExpandHook.HOOK_CUSTOM_MEMORY)
        if memories:
            first = memories[0]
            if isinstance(first, LongTermMemory):
                self.long_term_memory = first
        for scheduler in self._registry.collect_components(ExpandHook.HOOK_CUSTOM_SCHEDULER):
            if isinstance(scheduler, Scheduler):
                self.custom_schedulers.append(scheduler)
