"""test_core.py —— 覆盖核心模块：Agent 循环、工具注册调用、记忆读写、调度器分发。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from thinkstack import (
    EchoAgent,
    FunctionTool,
    InMemoryLongTermMemory,
    ParallelScheduler,
    PriorityScheduler,
    SerialScheduler,
    ShortTermMemory,
    Task,
    ThinkStack,
    Tool,
    ToolResult,
    WorkingMemory,
    tool,
)


# ---------------------------------------------------------------- Agent 循环

def test_agent_run_loop():
    stack = ThinkStack()
    result = stack.run_agent(EchoAgent(), "你好", max_iterations=3)
    assert result.success is True
    assert result.iterations == 3
    assert len(result.history) == 3
    assert result.history[0]["iteration"] == 1


def test_agent_max_iterations_bound():
    stack = ThinkStack()
    result = stack.run_agent(EchoAgent(), "x", max_iterations=1)
    assert result.iterations == 1


# ---------------------------------------------------------------- 工具注册与调用

class AddInput(BaseModel):
    a: int = Field(description="加数 a")
    b: int = Field(description="加数 b")


def test_tool_register_and_call():
    stack = ThinkStack()
    stack.register_tool(
        FunctionTool(name="add", description="加法", input_schema=AddInput, func=lambda a, b: a + b)
    )
    result = stack.call_tool("add", a=1, b=2)
    assert result.success is True
    assert result.data == 3


def test_tool_validation_error():
    stack = ThinkStack()
    stack.register_tool(
        FunctionTool(name="add", description="加法", input_schema=AddInput, func=lambda a, b: a + b)
    )
    result = stack.call_tool("add", a=1)  # 缺少 b，应校验失败
    assert result.success is False
    assert result.error is not None


def test_tool_duplicate_name_rejected():
    stack = ThinkStack()
    stack.register_tool(FunctionTool(name="t", description="", func=lambda: 1))
    try:
        stack.register_tool(FunctionTool(name="t", description="", func=lambda: 2))
        assert False, "应抛出 ToolError"
    except Exception as exc:
        assert "已注册" in str(exc)


def test_tool_decorator():
    @tool(name="double", description="乘以二", input_schema=AddInput)
    def double(a: int, b: int) -> int:
        return (a + b) * 2

    stack = ThinkStack()
    stack.register_tool(double)
    result = stack.call_tool("double", a=2, b=3)
    assert result.data == 10


def test_tool_result_model():
    ok = ToolResult.ok(42)
    assert ok.success is True and ok.data == 42
    fail = ToolResult.fail("出错了")
    assert fail.success is False and fail.error == "出错了"


# ---------------------------------------------------------------- 记忆读写

def test_short_term_fifo_eviction():
    mem = ShortTermMemory(capacity=2)
    mem.store("a", 1)
    mem.store("b", 2)
    mem.store("c", 3)
    assert mem.retrieve("a") is None
    assert mem.retrieve("b") == 2
    assert mem.retrieve("c") == 3


def test_working_memory():
    mem = WorkingMemory()
    mem.store("k", "v")
    assert mem.retrieve("k") == "v"
    assert "k" in mem.snapshot()
    mem.clear()
    assert mem.retrieve("k") is None


def test_long_term_memory_inmemory():
    mem = InMemoryLongTermMemory()
    mem.store("user", {"name": "陌老师"})
    assert mem.retrieve("user") == {"name": "陌老师"}
    mem.save()  # 内存后端接口应可调用
    mem.load()


def test_stack_memory_convenience():
    stack = ThinkStack()
    stack.store_short_term("s", 1)
    stack.store_long_term("l", 2)
    stack.store_working("w", 3)
    assert stack.retrieve_short_term("s") == 1
    assert stack.retrieve_long_term("l") == 2
    assert stack.retrieve_working("w") == 3


# ---------------------------------------------------------------- 调度器分发

def test_serial_scheduler_order():
    sched = SerialScheduler()
    order: list[str] = []

    def make(name: str):
        def _f():
            order.append(name)
            return name

        return Task(name=name, func=_f)

    sched.submit(make("a"))
    sched.submit(make("b"))
    results = sched.run_all()
    assert order == ["a", "b"]
    assert all(r.success for r in results)


def test_parallel_scheduler_completes_all():
    sched = ParallelScheduler(max_workers=4)
    for i in range(10):
        sched.submit(Task(name=f"t{i}", func=lambda i=i: i * i))
    results = sched.run_all()
    assert len(results) == 10
    assert all(r.success for r in results)
    assert sorted(r.data for r in results) == [i * i for i in range(10)]


def test_priority_scheduler_order():
    sched = PriorityScheduler()
    order: list[str] = []

    def make(name: str, priority: int):
        def _f():
            order.append(name)
            return name

        return Task(name=name, func=_f, priority=priority)

    sched.submit(make("low", 10))
    sched.submit(make("high", 1))
    sched.submit(make("mid", 5))
    sched.run_all()
    assert order == ["high", "mid", "low"]


def test_stack_scheduler_config():
    stack = ThinkStack()
    stack.submit_task(Task(name="x", func=lambda: "ok"))
    results = stack.run_tasks()
    assert results[0].success and results[0].data == "ok"


# ---------------------------------------------------------------- 生命周期

def test_stack_lifecycle():
    stack = ThinkStack()
    assert stack.is_running is False
    stack.start()
    assert stack.is_running is True
    stack.shutdown()
    assert stack.is_running is False
