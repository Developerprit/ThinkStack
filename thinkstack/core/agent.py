"""Agent 抽象基类：实现「思考→行动→观察」循环。

公开接口：AgentResult, Agent
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

from thinkstack.core.reasoner import EchoReasoner, Reasoner
from thinkstack.errors import AgentError


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
        """执行标准「思考→行动→观察」循环。

        参数：
            task_input: 初始任务输入。
            max_iterations: 最大迭代次数（须为正整数）。

        返回：
            AgentResult 结果对象。
        """
        if max_iterations < 1:
            raise AgentError("max_iterations 必须为正整数")

        context: dict[str, Any] = {"input": task_input}
        history: list[dict[str, Any]] = []
        output: Any = None

        for i in range(1, max_iterations + 1):
            thought = self.think(context)
            action = self.act(thought)
            observation = self.observe(action)
            context["thought"] = thought
            context["action"] = action
            context["observation"] = observation
            history.append(
                {"iteration": i, "thought": thought, "action": action, "observation": observation}
            )
            output = observation
            if self.should_stop(observation):
                break

        return AgentResult(success=True, output=output, iterations=len(history), history=history)
