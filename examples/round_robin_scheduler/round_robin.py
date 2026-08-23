"""示例扩展 C：基于时间片轮转的调度器。

演示调度器接口（Scheduler）的完整实现与任务分发。
通过 HOOK_CUSTOM_SCHEDULER 扩展点向框架注册自定义调度策略。

时间片轮转（Round Robin）语义：
    - 普通任务（函数返回非迭代器）一次性执行完毕；
    - 步进任务（函数返回生成器/迭代器）被视为由多个时间片组成，
      调度器每轮按顺序从每个步进任务各取 quantum 个时间片，直至全部完成。

公开接口：RoundRobinScheduler, register_round_robin_scheduler
"""

from __future__ import annotations

from typing import Any

from thinkstack import ExpandHook, Scheduler, Task, TaskResult, expand_hook


class RoundRobinScheduler(Scheduler):
    """时间片轮转调度器。

    quantum 表示每轮每个任务消耗的时间片数量（默认 1）。
    """

    def __init__(self, quantum: int = 1) -> None:
        super().__init__()
        if quantum < 1:
            raise ValueError("quantum 必须为正整数")
        self.quantum = quantum

    def run_all(self) -> list[TaskResult]:
        """按时间片轮转策略执行全部任务。"""
        tasks = list(self._tasks)
        self._tasks.clear()

        results: list[TaskResult] = []
        steppers: list[dict[str, Any]] = []

        for task in tasks:
            try:
                out = task.func(*task.args, **task.kwargs)
            except Exception as exc:
                results.append(TaskResult(name=task.name, success=False, error=str(exc)))
                continue
            if hasattr(out, "__next__"):
                # 生成器任务：进入轮转队列
                steppers.append({"name": task.name, "gen": out, "collected": [], "done": False})
            else:
                # 普通任务：一次性完成
                results.append(TaskResult(name=task.name, success=True, data=out))

        # 轮转：每轮每个未完成任务各执行 quantum 个时间片
        while any(not item["done"] for item in steppers):
            for item in steppers:
                if item["done"]:
                    continue
                try:
                    for _ in range(self.quantum):
                        item["collected"].append(next(item["gen"]))
                except StopIteration:
                    item["done"] = True
                    results.append(
                        TaskResult(name=item["name"], success=True, data=item["collected"])
                    )

        return results


@expand_hook(ExpandHook.HOOK_CUSTOM_SCHEDULER)
def register_round_robin_scheduler() -> RoundRobinScheduler:
    """向框架注册时间片轮转调度器。"""
    return RoundRobinScheduler(quantum=1)


# 供演示使用的步进任务工厂：返回一个 3 步生成器，便于观察轮转交错顺序
def make_step_task(name: str, label: str):
    """构造一个步进任务函数（返回生成器）。"""

    def _generator() -> Any:
        for i in range(1, 4):
            yield f"{label}-step{i}"

    return Task(name=name, func=_generator)
