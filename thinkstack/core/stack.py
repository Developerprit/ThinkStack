"""ThinkStack 主入口类：生命周期管理与组件编排。

公开接口：ThinkStack
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from pydantic import BaseModel, Field

from thinkstack.config import Config
from thinkstack.core.agent import (
    STAGE_AFTER_ACTION,
    STAGE_AFTER_OBSERVE,
    STAGE_AFTER_THINK,
    STAGE_BEFORE_ACTION,
    STAGE_BEFORE_OBSERVE,
    STAGE_BEFORE_THINK,
    Agent,
    AgentResult,
    iter_agent_loop,
    run_agent_loop,
)
from thinkstack.core.markdown import markdown_to_html
from thinkstack.core.memory import (
    InMemoryLongTermMemory,
    JsonFileLongTermMemory,
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
from thinkstack.core.tool import FunctionTool, Tool, ToolRegistry, ToolResult
from thinkstack.errors import SchedulerError, ThinkStackError
from thinkstack.expand.api import ExtensionRegistry
from thinkstack.expand.handle import ExtensionHandle
from thinkstack.expand.hooks import ExpandHook
from thinkstack.logging_utils import setup_logger

# 生命周期阶段名 → 扩展点映射（供 hook_runner 使用）
_STAGE_TO_HOOK: dict[str, ExpandHook] = {
    STAGE_BEFORE_THINK: ExpandHook.HOOK_BEFORE_THINK,
    STAGE_AFTER_THINK: ExpandHook.HOOK_AFTER_THINK,
    STAGE_BEFORE_ACTION: ExpandHook.HOOK_BEFORE_ACTION,
    STAGE_AFTER_ACTION: ExpandHook.HOOK_AFTER_ACTION,
    STAGE_BEFORE_OBSERVE: ExpandHook.HOOK_BEFORE_OBSERVE,
    STAGE_AFTER_OBSERVE: ExpandHook.HOOK_AFTER_OBSERVE,
}


class MarkdownInput(BaseModel):
    """markdown 工具入参。"""

    text: str = Field(description="要转换的 Markdown 文本")


class ThinkStack:
    """ThinkStack Agent 框架主入口。

    聚合工具注册表、三类记忆、调度器、Agent 注册表、扩展注册表与执行循环，
    对外提供统一的生命周期管理（__init__ / start / shutdown）。
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config: Config = config or Config()
        self._registry = ExtensionRegistry()
        self.tools = ToolRegistry()
        self.logger = setup_logger("thinkstack", self.config.log)

        self.short_term_memory = ShortTermMemory(capacity=self.config.memory.short_term_capacity)
        self.working_memory = WorkingMemory()
        self.long_term_memory: LongTermMemory = self._build_long_term_memory()

        self.scheduler: Scheduler = self._build_scheduler()
        self.custom_schedulers: list[Scheduler] = []
        self.custom_agents: dict[str, Any] = {}

        # 内置 markdown 工具：把 LLM 输出的 Markdown 渲染为 HTML
        self.register_tool(
            FunctionTool(
                name="markdown",
                description="将 Markdown 文本渲染为 HTML",
                input_schema=MarkdownInput,
                func=lambda text: markdown_to_html(text),
            )
        )

        self._started = False

    # ------------------------------------------------------------------ 生命周期

    def start(self) -> None:
        """启动框架：应用组件扩展（自定义工具/记忆/调度器/Agent）。"""
        self._started = True
        self._apply_component_extensions()

    def shutdown(self) -> None:
        """关闭框架：持久化长期记忆并标记停止。"""
        if not self._started:
            return
        try:
            self.long_term_memory.save()
        except Exception as exc:
            self.logger.warning("长期记忆持久化失败：%s", exc)
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

    def get_memory(self, kind: str) -> Any:
        """按类别返回记忆后端：long / short / working。"""
        mapping = {
            "long": self.long_term_memory,
            "short": self.short_term_memory,
            "working": self.working_memory,
        }
        if kind not in mapping:
            raise ThinkStackError(f"未知记忆类别 {kind!r}，可选：long / short / working")
        return mapping[kind]

    # ------------------------------------------------------------------ 调度

    def submit_task(self, task: Task) -> None:
        """提交任务到当前调度器。"""
        self.scheduler.submit(task)

    def run_tasks(self) -> list[TaskResult]:
        """执行当前调度器中的全部任务并返回结果。"""
        return self.scheduler.run_all()

    # ------------------------------------------------------------------ Agent

    def register_agent(self, name: str, agent: Any) -> None:
        """注册自定义 Agent（可传 Agent 实例或 Agent 子类）。"""
        if isinstance(agent, type) and issubclass(agent, Agent):
            self.custom_agents[name] = agent
        elif isinstance(agent, Agent):
            self.custom_agents[name] = agent
        else:
            raise ThinkStackError("register_agent() 仅接受 Agent 实例或 Agent 子类")

    def resolve_agent(self, name: str) -> Optional[Agent]:
        """按名称解析 Agent 实例，不存在返回 None。"""
        entry = self.custom_agents.get(name)
        if entry is None:
            return None
        if isinstance(entry, type):
            return entry()
        return entry

    def list_agents(self) -> list[str]:
        """列出全部已注册自定义 Agent 名称。"""
        return list(self.custom_agents.keys())

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

    def get_extension(self, name: str) -> ExtensionHandle:
        """按名称获取扩展句柄。"""
        return self._registry.get(name)

    # ------------------------------------------------------------------ 执行循环

    def _run_hook(self, stage: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """生命周期钩子回调：把阶段名映射为扩展点并触发。"""
        point = _STAGE_TO_HOOK.get(stage)
        if point is None:
            return ctx
        return self._registry.trigger_lifecycle(point, ctx)

    def run_agent(
        self, agent: Agent, task_input: Any, max_iterations: Optional[int] = None
    ) -> AgentResult:
        """执行 Agent「思考→行动→观察」循环，并在各阶段触发扩展钩子。"""
        max_iter = self.config.max_iterations if max_iterations is None else max_iterations
        setattr(agent, "_stack", self)
        return self._run_agent_impl(agent, task_input, max_iter)

    def _run_agent_impl(self, agent: Agent, task_input: Any, max_iter: int) -> AgentResult:
        return run_agent_loop(
            agent, task_input, max_iter, hook_runner=self._run_hook, stack=self
        )

    def run_agent_stream(
        self, agent: Agent, task_input: Any, max_iterations: Optional[int] = None
    ) -> Iterator[dict[str, Any]]:
        """流式执行 Agent 循环，逐次产出每一步结果（供 SSE 使用）。"""
        max_iter = self.config.max_iterations if max_iterations is None else max_iterations
        setattr(agent, "_stack", self)
        yield from iter_agent_loop(
            agent, task_input, max_iter, hook_runner=self._run_hook, stack=self
        )

    # ------------------------------------------------------------------ 内部

    def _build_long_term_memory(self) -> LongTermMemory:
        """根据配置构建长期记忆后端。"""
        backend = self.config.memory.long_term_backend
        if backend == "json_file":
            path = self.config.memory.persist_path or "thinkstack_memory.json"
            return JsonFileLongTermMemory(path=path)
        return InMemoryLongTermMemory()

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
        """应用组件扩展：自定义工具/记忆/调度器/Agent 接入（幂等）。"""
        for tool in self._registry.collect_components(ExpandHook.HOOK_CUSTOM_TOOL):
            try:
                self.tools.register(tool)
            except Exception as exc:
                self.logger.debug("自定义工具注册失败：%s", exc)
                continue

        memories = self._registry.collect_components(ExpandHook.HOOK_CUSTOM_MEMORY)
        for first in memories:
            if isinstance(first, LongTermMemory):
                self.long_term_memory = first
                break

        # 全量重建，避免 start() 后再次 register_extension 时重复累积同一实例
        self.custom_schedulers = [
            scheduler
            for scheduler in self._registry.collect_components(ExpandHook.HOOK_CUSTOM_SCHEDULER)
            if isinstance(scheduler, Scheduler)
        ]

        for component in self._registry.collect_components(ExpandHook.HOOK_CUSTOM_AGENT):
            try:
                if isinstance(component, type) and issubclass(component, Agent):
                    self.register_agent(component.name, component)
                elif isinstance(component, Agent):
                    self.register_agent(component.name, component)
            except Exception as exc:
                self.logger.debug("自定义 Agent 注册失败：%s", exc)
                continue
