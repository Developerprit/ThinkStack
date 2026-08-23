"""任务调度器基类与三种策略实现。

公开接口：Task, TaskResult, Scheduler, SerialScheduler, ParallelScheduler, PriorityScheduler
"""

from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from thinkstack.errors import SchedulerError


class Task(BaseModel):
    """调度任务模型。"""

    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(description="任务名称")
    func: Any = Field(exclude=True, description="可调用对象")
    args: tuple = Field(default_factory=tuple, description="位置参数")
    kwargs: dict = Field(default_factory=dict, description="关键字参数")
    priority: int = Field(default=0, description="优先级（数值越小越优先）")

    def run(self) -> Any:
        """执行任务并返回结果。"""
        return self.func(*self.args, **self.kwargs)


class TaskResult(BaseModel):
    """任务执行结果。"""

    name: str = Field(description="任务名称")
    success: bool = Field(description="是否成功")
    data: Any = Field(default=None, description="执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")


class Scheduler(ABC):
    """调度器抽象基类。"""

    def __init__(self) -> None:
        self._tasks: list[Task] = []

    def submit(self, task: Task) -> None:
        """提交一个任务到调度队列。"""
        if not isinstance(task, Task):
            raise SchedulerError("submit() 仅接受 Task 实例")
        self._tasks.append(task)

    def clear(self) -> None:
        """清空待调度任务。"""
        self._tasks.clear()

    @property
    def pending_count(self) -> int:
        """当前待调度任务数量。"""
        return len(self._tasks)

    def _run_one(self, task: Task) -> TaskResult:
        """执行单个任务并统一封装结果。"""
        try:
            return TaskResult(name=task.name, success=True, data=task.run())
        except Exception as exc:
            return TaskResult(name=task.name, success=False, error=str(exc))

    @abstractmethod
    def run_all(self) -> list[TaskResult]:
        """按各自策略执行全部任务，返回结果列表。"""
        raise NotImplementedError


class SerialScheduler(Scheduler):
    """串行调度器：按提交顺序逐个执行。"""

    def run_all(self) -> list[TaskResult]:
        results: list[TaskResult] = []
        for task in list(self._tasks):
            results.append(self._run_one(task))
        self._tasks.clear()
        return results


class ParallelScheduler(Scheduler):
    """并行调度器：使用线程池并发执行任务。"""

    def __init__(self, max_workers: int = 4) -> None:
        super().__init__()
        if max_workers < 1:
            raise SchedulerError("max_workers 必须为正整数")
        self.max_workers = max_workers

    def run_all(self) -> list[TaskResult]:
        tasks = list(self._tasks)
        self._tasks.clear()
        if not tasks:
            return []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._run_one, t) for t in tasks]
            return [f.result() for f in futures]


class PriorityScheduler(Scheduler):
    """优先级调度器：数值越小优先级越高，使用最小堆分发。"""

    def run_all(self) -> list[TaskResult]:
        heap: list[tuple[int, int, Task]] = []
        for index, task in enumerate(self._tasks):
            heapq.heappush(heap, (task.priority, index, task))
        results: list[TaskResult] = []
        while heap:
            _, _, task = heapq.heappop(heap)
            results.append(self._run_one(task))
        self._tasks.clear()
        return results
