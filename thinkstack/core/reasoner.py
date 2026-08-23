"""推理后端抽象（模型无关）。

公开接口：Reasoner, EchoReasoner
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Reasoner(ABC):
    """推理后端抽象基类。

    ThinkStack 保持模型无关性，不绑定任何 AI 模型 SDK。Agent 的思考步骤
    通过本接口委托给具体推理实现（可为真模型、规则引擎或回显占位）。
    """

    name: str = "abstract-reasoner"

    @abstractmethod
    def reason(self, context: dict[str, Any], instruction: str = "") -> str:
        """根据上下文与指令产生一段推理结果文本。

        参数：
            context: 当前会话上下文（含记忆、工具结果等）。
            instruction: 可选的额外指令。

        返回：
            推理结果字符串。
        """
        raise NotImplementedError


class EchoReasoner(Reasoner):
    """回显推理器（开箱即用的占位实现）。

    不依赖任何模型，仅把输入上下文与指令拼接后原样回显，
    用于在未接入真实模型前跑通完整链路与单元测试。
    """

    name = "echo"

    def reason(self, context: dict[str, Any], instruction: str = "") -> str:
        parts: list[str] = []
        if instruction:
            parts.append(f"[指令] {instruction}")
        for key, value in context.items():
            parts.append(f"[{key}] {value}")
        if not parts:
            return "(空上下文)"
        return " | ".join(parts)
