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
from thinkstack.errors import (
    SchedulerError,
    ThinkStackError,
    TS_CODE_BLACKHOLE,
    TS_CODE_EXT_API_ERROR,
    TS_CODE_EXT_ERROR,
    TS_CODE_OK,
    TS_CODE_TS_ERROR,
    TS_CODE_TS_LOST,
    ts_status,
)
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

    # ------------------------------------------------------------------ 架构自检

    def check_architecture(self) -> dict[str, Any]:
        """架构自检：逐层检查 Core / Expand API / Extension / Runtime 四层组件。

        任一层报错即返回对应 TS 状态码（状态码定义见 thinkstack.errors，
        原始清单见 E:/PC/error.txt）；全部通过返回 2000（TS ok :2000）。

        - Core Layer 组件缺失 → 3404 TS意外丢失；核心层异常 → 3005 TS错误
        - Expand API Layer 出错 → 1001 扩展API错误
        - Extension Layer 出错 → 1002 扩展错误
        - Runtime Layer 生命周期不一致 → 4000 消息发进了黑洞；异常 → 3005

        返回结构：
            {
                "ok": bool,        # 整体是否通过
                "ts_code": int,    # TS 状态码（2000 = 通过）
                "ts_status": str,  # "TS ok :2000" / "TS error :<code>"
                "message": str,    # 失败原因简述（通过时为 "OK"）
                "layers": {        # 各层检查明细
                    "core":      {"ok": bool, "checks": [str]},
                    "expand":    {"ok": bool, "checks": [str]},
                    "extension": {"ok": bool, "checks": [str]},
                    "runtime":   {"ok": bool, "checks": [str]},
                },
            }
        """
        layers: dict[str, Any] = {}

        def _record(name: str, ok: bool, checks: list[str]) -> None:
            layers[name] = {"ok": ok, "checks": checks}

        def _fail(code: int, message: str) -> dict[str, Any]:
            return {
                "ok": False,
                "ts_code": code,
                "ts_status": ts_status(code),
                "message": message,
                "layers": layers,
            }

        # ------------------------------- Core Layer -------------------------------
        core_checks: list[str] = []
        core_ok = True
        try:
            if self.config is None:
                core_ok, core_checks = False, ["config is missing"]
            else:
                core_checks.append("config valid")
            if core_ok:
                for attr, label in (
                    ("tools", "tool registry"),
                    ("short_term_memory", "short-term memory"),
                    ("working_memory", "working memory"),
                    ("long_term_memory", "long-term memory"),
                    ("scheduler", "scheduler"),
                ):
                    if getattr(self, attr, None) is None:
                        core_ok, core_checks = False, [f"{label} is missing"]
                        break
                    core_checks.append(f"{label} present")
            if core_ok and "markdown" not in self.tools:
                core_ok, core_checks = False, ["builtin 'markdown' tool is missing"]
        except Exception as exc:
            _record("core", False, [f"exception: {exc}"])
            return _fail(TS_CODE_TS_ERROR, f"核心层异常：{exc}")
        _record("core", core_ok, core_checks)
        if not core_ok:
            return _fail(TS_CODE_TS_LOST, "核心层组件缺失：" + "; ".join(core_checks))

        # ---------------------------- Expand API Layer ----------------------------
        expand_checks: list[str] = []
        expand_ok = True
        try:
            if self._registry is None:
                expand_ok, expand_checks = False, ["extension registry is missing"]
            else:
                expand_checks.append("extension registry present")
            if expand_ok:
                hook_count = len(ExpandHook)
                if hook_count != 10:
                    expand_ok, expand_checks = False, [f"expected 10 hook points, got {hook_count}"]
                else:
                    expand_checks.append("10 hook points defined")
            if expand_ok:
                for fn in ("register_extension", "get_extension", "list_extensions"):
                    if not callable(getattr(self, fn, None)):
                        expand_ok, expand_checks = False, [f"{fn}() not callable"]
                        break
                    expand_checks.append(f"{fn}() callable")
        except Exception as exc:
            _record("expand", False, [f"exception: {exc}"])
            return _fail(TS_CODE_EXT_API_ERROR, f"扩展API层异常：{exc}")
        _record("expand", expand_ok, expand_checks)
        if not expand_ok:
            return _fail(TS_CODE_EXT_API_ERROR, "扩展API错误：" + "; ".join(expand_checks))

        # ---------------------------- Extension Layer -----------------------------
        ext_checks: list[str] = []
        ext_ok = True
        try:
            handles = self.list_extensions()
            if not handles:
                ext_checks.append("no extensions registered")
            for handle in handles:
                if handle is None or not getattr(handle, "name", None):
                    ext_ok, ext_checks = False, ["extension handle invalid (no name)"]
                    break
                if not getattr(handle, "is_active", False):
                    ext_ok, ext_checks = False, [f"extension '{handle.name}' is inactive"]
                    break
                ext_checks.append(f"extension '{handle.name}' active")
        except Exception as exc:
            _record("extension", False, [f"exception: {exc}"])
            return _fail(TS_CODE_EXT_ERROR, f"扩展层异常：{exc}")
        _record("extension", ext_ok, ext_checks)
        if not ext_ok:
            return _fail(TS_CODE_EXT_ERROR, "扩展错误：" + "; ".join(ext_checks))

        # ------------------------------ Runtime Layer -----------------------------
        runtime_checks: list[str] = []
        runtime_ok = True
        try:
            if self._started != self.is_running:
                runtime_ok, runtime_checks = False, ["lifecycle state inconsistent"]
            else:
                runtime_checks.append("lifecycle state consistent")
            runtime_checks.append("running" if self.is_running else "not running")
        except Exception as exc:
            _record("runtime", False, [f"exception: {exc}"])
            return _fail(TS_CODE_TS_ERROR, f"运行时层异常：{exc}")
        _record("runtime", runtime_ok, runtime_checks)
        if not runtime_ok:
            return _fail(TS_CODE_BLACKHOLE, "消息发进了黑洞：" + "; ".join(runtime_checks))

        return {
            "ok": True,
            "ts_code": TS_CODE_OK,
            "ts_status": ts_status(TS_CODE_OK),
            "message": "OK",
            "layers": layers,
        }

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
