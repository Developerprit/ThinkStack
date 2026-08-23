"""test_expand.py —— 覆盖扩展加载成功/失败、钩子触发顺序、扩展隔离性与句柄生命周期。"""

from __future__ import annotations

import os

from thinkstack import (
    Agent,
    ExpandHook,
    ExtensionLoadError,
    ExtensionRegistry,
    ExtensionValidationError,
    Task,
    ThinkStack,
)

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
WEATHER_PATH = os.path.join(EXAMPLES_DIR, "weather_tool", "weather.py")
SQLITE_PATH = os.path.join(EXAMPLES_DIR, "sqlite_memory", "sqlite_memory.py")
ROUND_ROBIN_PATH = os.path.join(EXAMPLES_DIR, "round_robin_scheduler", "round_robin.py")

# 用于临时扩展模块的模板
HOOK_TRACE_EXT = '''\
from thinkstack import expand_hook, ExpandHook

@expand_hook(ExpandHook.HOOK_BEFORE_THINK)
def before_think(ctx):
    ctx.setdefault("_trace", []).append("before_think")
    return ctx

@expand_hook(ExpandHook.HOOK_AFTER_THINK)
def after_think(ctx):
    ctx.setdefault("_trace", []).append("after_think")
    return ctx

@expand_hook(ExpandHook.HOOK_BEFORE_ACTION)
def before_action(ctx):
    ctx.setdefault("_trace", []).append("before_action")
    return ctx

@expand_hook(ExpandHook.HOOK_AFTER_ACTION)
def after_action(ctx):
    ctx.setdefault("_trace", []).append("after_action")
    return ctx
'''

BAD_HOOK_EXT = '''\
from thinkstack import expand_hook, ExpandHook

@expand_hook(ExpandHook.HOOK_BEFORE_THINK)
def bad_hook(ctx):
    raise RuntimeError("故意抛出的异常")

@expand_hook(ExpandHook.HOOK_BEFORE_THINK)
def good_hook(ctx):
    ctx.setdefault("_trace", []).append("good_hook")
    return ctx
'''

BAD_SIGNATURE_EXT = '''\
from thinkstack import expand_hook, ExpandHook

@expand_hook(ExpandHook.HOOK_BEFORE_THINK)
def bad_signature(a, b):
    return a
'''


class TraceAgent(Agent):
    """读取上下文中 _trace 的测试 Agent。"""

    name = "trace-agent"

    def think(self, context):
        return list(context.get("_trace", []))

    def act(self, thought):
        return thought

    def observe(self, action):
        return action


# ---------------------------------------------------------------- 扩展加载

def test_register_extension_success():
    registry = ExtensionRegistry()
    handle = registry.register("weather", WEATHER_PATH)
    assert handle.is_active is True
    assert "hook_custom_tool" in handle.hook_points


def test_register_extension_failure():
    registry = ExtensionRegistry()
    try:
        registry.register("missing", "/nonexistent/path.py")
        assert False, "应抛出 ExtensionLoadError"
    except ExtensionLoadError:
        pass


def test_register_extension_duplicate_name():
    registry = ExtensionRegistry()
    registry.register("weather", WEATHER_PATH)
    try:
        registry.register("weather", WEATHER_PATH)
        assert False, "应抛出 ExtensionLoadError"
    except ExtensionLoadError:
        pass


# ---------------------------------------------------------------- 钩子触发顺序

def test_hook_trigger_order(tmp_path):
    ext = tmp_path / "order_ext.py"
    ext.write_text(HOOK_TRACE_EXT, encoding="utf-8")
    registry = ExtensionRegistry()
    registry.register("order_ext", str(ext))

    ctx: dict = {}
    for point in [
        ExpandHook.HOOK_BEFORE_THINK,
        ExpandHook.HOOK_AFTER_THINK,
        ExpandHook.HOOK_BEFORE_ACTION,
        ExpandHook.HOOK_AFTER_ACTION,
    ]:
        ctx = registry.trigger_lifecycle(point, ctx)

    assert ctx["_trace"] == ["before_think", "after_think", "before_action", "after_action"]


def test_hooks_fire_during_agent_run(tmp_path):
    ext = tmp_path / "order_ext.py"
    ext.write_text(HOOK_TRACE_EXT, encoding="utf-8")
    stack = ThinkStack()
    stack.register_extension("order_ext", str(ext))
    stack.start()

    result = stack.run_agent(TraceAgent(), "x", max_iterations=1)
    # think 之前已触发 before_think，TraceAgent 应能读到该记录
    assert "before_think" in result.history[0]["thought"]


# ---------------------------------------------------------------- 扩展隔离性

def test_extension_isolation(tmp_path):
    ext = tmp_path / "bad_ext.py"
    ext.write_text(BAD_HOOK_EXT, encoding="utf-8")
    registry = ExtensionRegistry()
    registry.register("bad_ext", str(ext))

    # 第一个钩子抛异常，第二个钩子应继续执行
    ctx = registry.trigger_lifecycle(ExpandHook.HOOK_BEFORE_THINK, {})
    assert ctx.get("_trace") == ["good_hook"]


# ---------------------------------------------------------------- 签名校验

def test_signature_validation(tmp_path):
    ext = tmp_path / "bad_sig_ext.py"
    ext.write_text(BAD_SIGNATURE_EXT, encoding="utf-8")
    registry = ExtensionRegistry()
    try:
        registry.register("bad_sig_ext", str(ext))
        assert False, "应抛出 ExtensionValidationError"
    except ExtensionValidationError:
        pass


# ---------------------------------------------------------------- 句柄生命周期

def test_extension_handle_lifecycle():
    registry = ExtensionRegistry()
    handle = registry.register("weather", WEATHER_PATH)
    assert handle.is_active is True
    handle.disable()
    assert handle.is_active is False
    handle.enable()
    assert handle.is_active is True
    handle.unload()
    assert handle.is_active is False


def test_disable_stops_hooks(tmp_path):
    ext = tmp_path / "order_ext.py"
    ext.write_text(HOOK_TRACE_EXT, encoding="utf-8")
    registry = ExtensionRegistry()
    handle = registry.register("order_ext", str(ext))
    handle.disable()
    ctx = registry.trigger_lifecycle(ExpandHook.HOOK_BEFORE_THINK, {})
    assert "_trace" not in ctx


# ---------------------------------------------------------------- 组件扩展端到端

def test_weather_tool_extension():
    stack = ThinkStack()
    stack.register_extension("weather", WEATHER_PATH)
    stack.start()
    result = stack.call_tool("weather", city="北京")
    assert result.success is True
    assert "晴" in result.data and "°C" in result.data


def test_sqlite_memory_extension(monkeypatch, tmp_path):
    monkeypatch.setenv("THINKSTACK_MEMORY_DB", str(tmp_path / "mem.db"))
    stack = ThinkStack()
    stack.register_extension("sqlite_memory", SQLITE_PATH)
    stack.start()
    assert type(stack.long_term_memory).__name__ == "SqliteLongTermMemory"
    stack.store_long_term("user", {"name": "陌老师"})
    assert stack.retrieve_long_term("user") == {"name": "陌老师"}


def test_round_robin_extension():
    stack = ThinkStack()
    stack.register_extension("round_robin", ROUND_ROBIN_PATH)
    stack.start()
    assert len(stack.custom_schedulers) == 1

    sched = stack.custom_schedulers[0]

    def gen_a():
        yield "a1"
        yield "a2"
        yield "a3"

    def gen_b():
        yield "b1"
        yield "b2"
        yield "b3"

    sched.submit(Task(name="A", func=gen_a))
    sched.submit(Task(name="B", func=gen_b))
    results = sched.run_all()

    assert len(results) == 2
    by_name = {r.name: r.data for r in results}
    assert by_name["A"] == ["a1", "a2", "a3"]
    assert by_name["B"] == ["b1", "b2", "b3"]
