# ThinkStack API 参考 / API Reference

本文档列出 ThinkStack 全部公开类、函数与枚举的签名、参数说明、返回值类型与最小使用示例。
所有公开接口统一使用简体中文注释，命名遵循：私有成员单下划线 `_` 前缀，魔法方法双下划线 `__`，对外接口无前缀。

---

## 1. 主入口

### `class ThinkStack`

Agent 框架主入口，聚合工具注册表、三类记忆、调度器、扩展注册表与 Agent 执行循环。

```python
ThinkStack(config: Optional[Config] = None)
```

**方法**

| 方法 | 签名 | 返回值 |
| --- | --- | --- |
| `start` | `start() -> None` | 启动框架，应用组件扩展 |
| `shutdown` | `shutdown() -> None` | 关闭框架，持久化长期记忆 |
| `run_agent` | `run_agent(agent, task_input, max_iterations=None) -> AgentResult` | 执行 Agent 循环并触发钩子 |
| `register_tool` | `register_tool(tool: Tool) -> None` | 注册工具 |
| `call_tool` | `call_tool(name, **kwargs) -> ToolResult` | 同步调用工具 |
| `acall_tool` | `async acall_tool(name, **kwargs) -> ToolResult` | 异步调用工具 |
| `list_tools` | `list_tools() -> list[dict]` | 列出工具信息 |
| `register_extension` | `register_extension(name, module_path) -> ExtensionHandle` | 加载并注册扩展 |
| `submit_task` | `submit_task(task: Task) -> None` | 提交调度任务 |
| `run_tasks` | `run_tasks() -> list[TaskResult]` | 执行调度任务 |

**属性**：`config`、`tools`、`short_term_memory`、`working_memory`、`long_term_memory`、`scheduler`、`custom_schedulers`、`is_running`。

**最小示例**

```python
from thinkstack import ThinkStack, EchoAgent

stack = ThinkStack()
stack.start()
result = stack.run_agent(EchoAgent(), "你好", max_iterations=3)
print(result.output)  # {'result': '[指令] 你好 | [input] 你好'}
stack.shutdown()
```

---

## 2. 配置

### `class Config(BaseModel)`

顶层配置数据类，作为统一配置入口。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | `"ThinkStack"` | 框架实例名称 |
| `agent_name` | `str` | `"default-agent"` | 默认 Agent 名称 |
| `max_iterations` | `int` | `10` | Agent 循环最大迭代次数（1–1000） |
| `memory` | `MemoryConfig` | 默认 | 记忆配置 |
| `scheduler` | `SchedulerConfig` | 默认 | 调度配置 |
| `server` | `ServerConfig` | 默认 | 服务器配置 |

```python
from thinkstack import Config

config = Config(name="MyStack", max_iterations=20)
config = Config.from_dict({"name": "MyStack", "max_iterations": 20})
```

子配置 `MemoryConfig`（`short_term_capacity`、`long_term_backend`、`persist_path`）、
`SchedulerConfig`（`strategy: serial|parallel|priority`、`max_workers`）、
`ServerConfig`（`host`、`port`、`enable_console_command`）。

---

## 3. Agent

### `class Agent(ABC)`

Agent 抽象基类，子类覆写 `think()` / `act()` / `observe()`。

```python
Agent(name: Optional[str] = None, reasoner: Optional[Reasoner] = None)
```

| 方法 | 签名 | 说明 |
| --- | --- | --- |
| `think` | `think(context: dict) -> str`（抽象） | 思考 |
| `act` | `act(thought: str) -> Any`（抽象） | 行动 |
| `observe` | `observe(action: Any) -> Any`（抽象） | 观察 |
| `should_stop` | `should_stop(observation) -> bool` | 是否终止循环（默认 False） |
| `run` | `run(task_input, max_iterations=10) -> AgentResult` | 标准循环 |

### `class AgentResult(BaseModel)`

字段：`success: bool`、`output: Any`、`iterations: int`、`history: list[dict]`。

### `class EchoAgent(Agent)`

回显 Agent，不依赖模型，用于跑通循环与演示。

### `class ToolCallingAgent(Agent)`

工具调用 Agent，输入约定为 `tool:工具名 key=value ...`，自动解析并调用工具。

```python
stack.run_agent(ToolCallingAgent(), "tool:weather city=北京", max_iterations=1)
```

---

## 4. 工具

### `class ToolResult(BaseModel)`

字段：`success: bool`、`data: Any`、`error: Optional[str]`。
类方法：`ToolResult.ok(data)`、`ToolResult.fail(error)`。

### `class Tool(ABC)`

工具抽象基类。属性：`name`、`description`、`input_schema: type[BaseModel]`、`is_async`。
方法：`run(**kwargs) -> Any`（同步）、`async arun(**kwargs) -> Any`（异步，默认委托 `run`）、`validate_args(kwargs) -> dict`。

### `class FunctionTool(Tool)`

将普通函数包装为工具：

```python
FunctionTool(name, description, func, input_schema=EmptyInput, is_async=False)
```

### `class ToolRegistry`

工具注册表。

| 方法 | 签名 | 返回值 |
| --- | --- | --- |
| `register` | `register(tool: Tool) -> None` | 注册（重名抛 `ToolError`） |
| `get` | `get(name) -> Tool` | 查询 |
| `list_tools` | `list_tools() -> list[dict]` | 列出工具 |
| `call` | `call(name, **kwargs) -> ToolResult` | 同步调用 |
| `acall` | `async acall(name, **kwargs) -> ToolResult` | 异步调用 |

### `tool` 装饰器

```python
from pydantic import BaseModel
from thinkstack import tool

class AddInput(BaseModel):
    a: int
    b: int

@tool(name="add", description="加法", input_schema=AddInput)
def add(a: int, b: int) -> int:
    return a + b
```

---

## 5. 记忆

### `class Memory(ABC)`

抽象接口：`store(key, value)`、`retrieve(key, default=None)`、`clear()`。

### `class WorkingMemory(Memory)`

工作记忆：会话内临时上下文。额外方法 `snapshot() -> dict`。

### `class ShortTermMemory(Memory)`

短期记忆：`ShortTermMemory(capacity=100)`，按容量 FIFO 淘汰。

### `class LongTermMemory(Memory)`

长期记忆抽象基类，额外抽象方法 `save()`、`load()`。

### `class InMemoryLongTermMemory(LongTermMemory)`

长期记忆内存实现，默认占位后端。

```python
stack.store_short_term("k", "v")
stack.retrieve_short_term("k")        # "v"
stack.store_long_term("user", {"name": "陌老师"})
```

---

## 6. 调度器

### `class Task(BaseModel)`

字段：`name`、`func`（可调用对象）、`args`、`kwargs`、`priority`（数值越小越优先）。

### `class TaskResult(BaseModel)`

字段：`name`、`success`、`data`、`error`。

### `class Scheduler(ABC)`

方法：`submit(task)`、`clear()`、`run_all() -> list[TaskResult]`、`pending_count`。

### `class SerialScheduler(Scheduler)`

串行：按提交顺序执行。

### `class ParallelScheduler(Scheduler)`

并行：`ParallelScheduler(max_workers=4)`，线程池并发执行。

### `class PriorityScheduler(Scheduler)`

优先级：最小堆，数值越小越先执行。

```python
from thinkstack import ThinkStack, Task

stack = ThinkStack()
stack.submit_task(Task(name="t", func=lambda: 42))
print(stack.run_tasks()[0].data)  # 42
```

---

## 7. 推理后端

### `class Reasoner(ABC)`

抽象方法：`reason(context: dict, instruction: str = "") -> str`。

### `class EchoReasoner(Reasoner)`

回显推理器，不依赖模型的占位实现。

---

## 8. Expand API

### `enum ExpandHook(str, Enum)`

九个扩展点：`HOOK_BEFORE_THINK`、`HOOK_AFTER_THINK`、`HOOK_BEFORE_ACTION`、`HOOK_AFTER_ACTION`、`HOOK_BEFORE_OBSERVE`、`HOOK_AFTER_OBSERVE`、`HOOK_CUSTOM_TOOL`、`HOOK_CUSTOM_MEMORY`、`HOOK_CUSTOM_SCHEDULER`。

### `expand_hook(hook_point: ExpandHook) -> Callable`

装饰器，将函数注册到指定扩展点。生命周期钩子签名约定 `func(ctx: dict) -> dict`，组件钩子约定 `func() -> Component`。

### `register_extension(name: str, module_path: str) -> ExtensionHandle`

动态加载扩展并返回句柄（使用模块级默认注册表）。

### `class ExtensionHandle`

| 方法/属性 | 签名 | 说明 |
| --- | --- | --- |
| `is_active` | `-> bool`（只读） | 是否激活 |
| `enable` | `enable() -> None` | 激活 |
| `disable` | `disable() -> None` | 停用 |
| `unload` | `unload() -> None` | 卸载 |
| `hook_points` | `-> list[str]` | 已挂载扩展点 |

### `class ExtensionRegistry`

扩展注册表。方法：`register(name, module_path)`、`get(name)`、`list_extensions()`、`unload(name)`、`all_active_hooks()`、`trigger_lifecycle(hook_point, ctx)`、`collect_components(hook_point)`。

```python
from thinkstack import register_extension

handle = register_extension("weather", "examples/weather_tool/weather.py")
print(handle.is_active)  # True
```

---

## 9. 运行时

### `class ThinkStackServer`

```python
ThinkStackServer(stack: ThinkStack, host="0.0.0.0", port=9635)
```

方法：`start(block=False)`、`shutdown()`、`handle_command(command) -> dict`。

REST 端点：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/info` | 框架信息 |
| GET | `/api/tools` | 工具列表 |
| POST | `/api/tools/call` | 调用工具 |
| GET | `/api/extensions` | 扩展列表 |
| POST | `/api/extensions/register` | 注册扩展 |
| GET | `/api/memory` | 记忆信息 |
| POST | `/api/agent/run` | 运行 Agent |
| POST | `/api/tasks/run` | 执行调度任务 |
| POST | `/api/command` | 命令通道（`webrun <port>` / `help`） |

### `class WebConsole`

```python
WebConsole(stack: ThinkStack, host="0.0.0.0", port=8080)
```

独立的 Web 控制台服务器，内置浅色/深色管理界面，通过 `webrun <port>` 动态开启。

---

## 10. 异常体系

| 异常 | 继承 | 触发场景 |
| --- | --- | --- |
| `ThinkStackError` | `Exception` | 基类 |
| `ConfigError` | `ThinkStackError` | 配置非法 |
| `ToolError` | `ThinkStackError` | 工具注册/调用错误 |
| `MemoryError` | `ThinkStackError` | 记忆读写错误 |
| `SchedulerError` | `ThinkStackError` | 调度错误 |
| `AgentError` | `ThinkStackError` | Agent 循环错误 |
| `ExtensionLoadError` | `ThinkStackError` | 扩展加载失败 |
| `ExtensionValidationError` | `ThinkStackError` | 签名校验失败 |
| `ExtensionAccessError` | `ThinkStackError` | 越权访问 |
