"""记忆抽象接口与内置实现。

公开接口：Memory, ShortTermMemory, LongTermMemory, InMemoryLongTermMemory, WorkingMemory
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Optional

from thinkstack.errors import MemoryError


class Memory(ABC):
    """记忆顶层抽象接口。"""

    @abstractmethod
    def store(self, key: str, value: Any) -> None:
        """写入一条记忆。"""
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, key: str, default: Any = None) -> Any:
        """读取一条记忆，不存在时返回 default。"""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """清空全部记忆。"""
        raise NotImplementedError


class WorkingMemory(Memory):
    """工作记忆：会话内临时上下文，进程结束即丢失。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def store(self, key: str, value: Any) -> None:
        self._data[key] = value

    def retrieve(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self) -> None:
        self._data.clear()

    def snapshot(self) -> dict[str, Any]:
        """返回当前工作记忆的浅拷贝快照。"""
        return dict(self._data)


class ShortTermMemory(Memory):
    """短期记忆：会话级，按容量 FIFO 淘汰最旧条目。"""

    def __init__(self, capacity: int = 100) -> None:
        if capacity < 1:
            raise MemoryError("短期记忆容量 capacity 必须为正整数")
        self.capacity = capacity
        self._data: OrderedDict[str, Any] = OrderedDict()

    def store(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def retrieve(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class LongTermMemory(Memory):
    """长期记忆抽象基类：提供持久化能力。

    具体后端（如 SQLite、文件、向量库）需实现 save() / load()。
    """

    @abstractmethod
    def save(self) -> None:
        """将当前记忆持久化到后端存储。"""
        raise NotImplementedError

    @abstractmethod
    def load(self) -> None:
        """从后端存储恢复记忆。"""
        raise NotImplementedError


class InMemoryLongTermMemory(LongTermMemory):
    """长期记忆的内存实现：仅进程内有效，用作默认占位后端。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def store(self, key: str, value: Any) -> None:
        self._data[key] = value

    def retrieve(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self) -> None:
        self._data.clear()

    def save(self) -> None:
        # 内存后端无持久化动作，接口保留以保持统一。
        pass

    def load(self) -> None:
        # 内存后端无需加载动作。
        pass
