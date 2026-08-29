"""Agent 抽象基类：实现「思考→行动→观察」循环。

公开接口：AgentResult, Agent, run_agent_loop, iter_agent_loop
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator, Optional

from pydantic import BaseModel, Field

from thinkstack.core.reasoner import EchoReasoner, Reasoner
from thinkstack.errors import AgentError

# 生命周期钩子阶段名（与 thinkstack.expand.ExpandHook 对应，由上层映射为具体扩展点）
STAGE_BEFORE_THINK = "before_think"
STAGE_AFTER_THINK = "after_think"
STAGE_BEFORE_ACTION = "before_action"
STAGE_AFTER_ACTION = "after_action"
STAGE_BEFORE_OBSERVE = "before_observe"
STAGE_AFTER_OBSERVE = "after_observe"


class AgentResult(BaseModel):
    """Agent 执行结果封装。"""

    success: bool = Field(description="是否成功完成")
    output: Any = Field(default=None, description="最终输出")
    iterations: int = Field(default=0, description="实际迭代次数")
    history: list[dict[str, Any]] = Field(default_factory=list, description="循环过程记录")


class Agent(ABC):
    """Agent 抽象基类。

    子类需覆写 think()、act()、observe() 三个抽象方法；
    run() 提供「思考→行动→观察」的标准循环，可复用或覆写。
    """

    name: str = "abstract-agent"

    def __init__(self, name: Optional[str] = None, reasoner: Optional[Reasoner] = None) -> None:
        self.name = name or self.__class__.name
        self.reasoner: Reasoner = reasoner or EchoReasoner()

    @abstractmethod
    def think(self, context: dict[str, Any]) -> str:
        """思考：根据上下文产生思考结果（可委托 reasoner）。"""
        raise NotImplementedError

    @abstractmethod
    def act(self, thought: str) -> Any:
        """行动：根据思考结果执行动作（如调用工具）。"""
        raise NotImplementedError

    @abstractmethod
    def observe(self, action: Any) -> Any:
        """观察：对行动结果进行观察与归纳。"""
        raise NotImplementedError

    def should_stop(self, observation: Any) -> bool:
        """判断是否应终止循环，默认永不提前终止。"""
        return False

    def run(self, task_input: Any, max_iterations: int = 10) -> AgentResult:
        """执行标准「思考→行动→观察」循环（不触发框架钩子）。"""
        return run_agent_loop(self, task_input, max_iterations)


def _validate_max_iterations(max_iterations: int) -> int:
    """校验最大迭代次数为正整数，非法则抛 AgentError。"""
    if (
        not isinstance(max_iterations, int)
        or isinstance(max_iterations, bool)
        or max_iterations < 1
    ):
        raise AgentError("max_iterations 必须为正整数")
    return max_iterations


def iter_agent_loop(
    agent: Agent,
    task_input: Any,
    max_iterations: int,
    *,
    hook_runner: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
    stack: Any = None,
) -> Iterator[dict[str, Any]]:
    """生成器：逐次产出「思考→行动→观察」每一步的结果。

    统一循环的唯一实现，`Agent.run()` 与 `ThinkStack.run_agent()` 均基于它，
    避免两套循环逻辑漂移。hook_runner 为可选的钩子触发回调
    （签名 `(stage: str, ctx: dict) -> dict`），用于在生命周期各阶段注入扩展钩子。
    """
    max_iter = _validate_max_iterations(max_iterations)
    ctx: dict[str, Any] = {"input": task_input}
    if stack is not None:
        ctx["stack"] = stack
        # 原生 Agent Skill：把已加载 skill 的摘要注入上下文（渐进式披露，
        # Agent 需要完整指令时再通过内置 skill 工具按名称获取）
        skill_context = getattr(stack, "skill_context", None)
        if callable(skill_context):
            ctx["skills"] = skill_context()

    for i in range(1, max_iter + 1):
        if hook_runner is not None:
            ctx = hook_runner(STAGE_BEFORE_THINK, ctx)
        ctx["thought"] = agent.think(ctx)
        if hook_runner is not None:
            ctx = hook_runner(STAGE_AFTER_THINK, ctx)

        if hook_runner is not None:
            ctx = hook_runner(STAGE_BEFORE_ACTION, ctx)
        ctx["action"] = agent.act(ctx["thought"])
        if hook_runner is not None:
            ctx = hook_runner(STAGE_AFTER_ACTION, ctx)

        if hook_runner is not None:
            ctx = hook_runner(STAGE_BEFORE_OBSERVE, ctx)
        ctx["observation"] = agent.observe(ctx["action"])
        if hook_runner is not None:
            ctx = hook_runner(STAGE_AFTER_OBSERVE, ctx)

        step = {
            "iteration": i,
            "thought": ctx["thought"],
            "action": ctx["action"],
            "observation": ctx["observation"],
        }
        yield step
        if agent.should_stop(ctx["observation"]):
            break


def run_agent_loop(
    agent: Agent,
    task_input: Any,
    max_iterations: int,
    *,
    hook_runner: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
    stack: Any = None,
) -> AgentResult:
    """执行标准「思考→行动→观察」循环并返回 AgentResult。"""
    history: list[dict[str, Any]] = []
    output: Any = None
    for step in iter_agent_loop(
        agent, task_input, max_iterations, hook_runner=hook_runner, stack=stack
    ):
        history.append(step)
        output = step["observation"]
    return AgentResult(success=True, output=output, iterations=len(history), history=history)
