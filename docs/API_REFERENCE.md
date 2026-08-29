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
| `register_agent` | `register_agent(name, agent) -> None` | 注册自定义 Agent（实例或子类） |
| `resolve_agent` | `resolve_agent(name) -> Optional[Agent]` | 按名称解析 Agent 实例 |
| `list_agents` | `list_agents() -> list[str]` | 列出自定义 Agent 名称 |
| `run_agent_stream` | `run_agent_stream(agent, task_input, max_iterations=None) -> Iterator[dict]` | 流式执行 Agent 循环（供 SSE） |
| `get_memory` | `get_memory(kind) -> Memory` | 按类别获取记忆后端（long/short/working） |
| `check_architecture` | `check_architecture() -> dict` | 四层架构自检，返回 TS 状态码 |

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

### `class MarkdownAgent(Agent)`

Markdown 渲染 Agent：把输入的 Markdown 文本渲染为 HTML（面向 LLM 输出多为 Markdown 的场景）。

```python
res = stack.run_agent(MarkdownAgent(), "# 你好", max_iterations=1)
print(res.output["html"])  # <h1>你好</h1>
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

### `markdown_to_html(text: str) -> str`

把 Markdown 文本转换为 HTML 片段（纯标准库，无第三方依赖）。支持标题、加粗/斜体/删除线、行内代码、围栏代码块、链接、图片、列表、引用、表格、分隔线。

```python
from thinkstack import markdown_to_html

html = markdown_to_html("**加粗** 和 `代码`")
# <p><strong>加粗</strong> 和 <code>代码</code></p>
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

### `class JsonFileLongTermMemory(LongTermMemory)`

JSON 文件持久化的长期记忆后端。`JsonFileLongTermMemory(path="thinkstack_memory.json")`，
`save()` 原子写入（临时文件 + `os.replace`）。可通过配置启用：

```python
from thinkstack import Config, ThinkStack

stack = ThinkStack(Config.from_dict({"memory": {"long_term_backend": "json_file", "persist_path": "mem.json"}}))
stack.store_long_term("user", {"name": "陌老师"})
stack.long_term_memory.save()
```

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

十个扩展点：`HOOK_BEFORE_THINK`、`HOOK_AFTER_THINK`、`HOOK_BEFORE_ACTION`、`HOOK_AFTER_ACTION`、`HOOK_BEFORE_OBSERVE`、`HOOK_AFTER_OBSERVE`、`HOOK_CUSTOM_TOOL`、`HOOK_CUSTOM_MEMORY`、`HOOK_CUSTOM_SCHEDULER`、`HOOK_CUSTOM_AGENT`。

### `expand_hook(hook_point: ExpandHook) -> Callable`

装饰器，将函数注册到指定扩展点。生命周期钩子签名约定 `func(ctx: dict) -> dict`，组件钩子约定 `func() -> Component`。

### `register_extension(name: str, module_path: str) -> ExtensionHandle`

动态加载扩展并返回句柄（使用模块级默认注册表）。

> 注意：模块级 `register_extension()` 与 `stack.register_extension()` 使用**两套独立注册表**。
> 前者仅写入全局默认注册表（供独立场景），后者才把扩展挂到具体 `ThinkStack` 实例。
> 要让扩展真正生效（如注册工具/记忆/调度器/Agent），请使用 `stack.register_extension()`。

> 安全边界：Python 无法在运行时真正强制「扩展禁止访问私有成员」。框架约定扩展仅依赖公开 API，
> `ExtensionAccessError` 保留用于需要显式抛出的场景；对 `_private` 成员的访问属于「约定而非强制」。

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
| GET | `/api/health` | 健康检查（含 TS 状态码） |
| GET | `/api/info` | 框架信息（含版本号） |
| GET | `/api/architecture/check` | 架构自检，返回 TS 状态码 |
| GET | `/api/tools` | 工具列表 |
| POST | `/api/tools/call` | 调用工具（同步） |
| POST | `/api/tools/acall` | 调用工具（异步） |
| GET | `/api/extensions` | 扩展列表 |
| POST | `/api/extensions/register` | 注册扩展 |
| POST | `/api/extensions/{name}/disable` | 停用扩展 |
| POST | `/api/extensions/{name}/enable` | 激活扩展 |
| POST | `/api/extensions/{name}/unload` | 卸载扩展 |
| GET | `/api/agents` | 内置与自定义 Agent 列表 |
| GET | `/api/memory` | 记忆信息 |
| POST | `/api/memory` | 记忆读写（`action: store/retrieve/clear`，`kind: long/short/working`） |
| POST | `/api/markdown/render` | Markdown 转 HTML |
| POST | `/api/agent/run` | 运行 Agent |
| POST | `/api/agent/run/stream` | 流式运行 Agent（SSE） |
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
| `TSStatusError` | `ThinkStackError` | 携带 TS 状态码的框架错误（`exc.ts_code`） |

---

## 11. TS 状态码

状态码清单见 `E:/PC/error.txt`。对外统一格式：

- 通过：`TS ok :2000`
- 失败：`TS error :<code>`

```python
from thinkstack import ts_status, TS_CODE_EXT_ERROR

ts_status(2000)   # 'TS ok :2000'
ts_status(1002)   # 'TS error :1002'
```

### `ts_status(code: int) -> str`

生成 TS 状态字符串；`2000` 返回 `TS ok :2000`，其余返回 `TS error :<code>`。

### `class TSStatusError(ThinkStackError)`

携带状态码的框架异常，`exc.ts_code` 保存状态码，`code` 为 `"TS_<code>"`：

```python
from thinkstack import TSStatusError, TS_CODE_TS_ERROR, ts_status

try:
    raise TSStatusError("核心层组件缺失", ts_code=TS_CODE_TS_ERROR)
except TSStatusError as exc:
    print(exc.ts_code)      # 3005
    print(ts_status(exc.ts_code))  # 'TS error :3005'
```

### 状态码常量

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `TS_CODE_EXT_API_ERROR` | 1001 | 扩展API错误（API本身错误） |
| `TS_CODE_EXT_ERROR` | 1002 | 扩展错误 |
| `TS_CODE_OK` | 2000 | OK,没问题 |
| `TS_CODE_LLM_TOKEN_EXHAUSTED` | 3001 | LLM的token用没了 |
| `TS_CODE_URL_404` | 3002 | URL 404 |
| `TS_CODE_MODEL_404` | 3003 | 模型ID 404 |
| `TS_CODE_KEY_ERROR` | 3004 | key错误 |
| `TS_CODE_TS_ERROR` | 3005 | TS错误 |
| `TS_CODE_TS_LOST` | 3404 | TS意外丢失 |
| `TS_CODE_BLACKHOLE` | 4000 | 消息发进了黑洞 |
| `TS_CODE_UNKNOWN` | 8000 | 未知错误 |

`TS_CODE_MESSAGES` 为状态码 → 中文描述映射，`TS_CODE_*` 常量均可从 `thinkstack` 顶层导入。

### 架构自检（check_architecture）

`stack.check_architecture()` 逐层检查四层架构：

| 层 | 检查内容 | 失败状态码 |
| --- | --- | --- |
| Core（核心层） | 配置、工具注册表、三类记忆、调度器、内置 markdown 工具 | 3404 TS意外丢失 / 3005 TS错误 |
| Expand API（扩展接口层） | 扩展注册表、十个扩展点、注册 API 可调用性 | 1001 扩展API错误 |
| Extension（扩展层） | 已注册扩展句柄有效且激活 | 1002 扩展错误 |
| Runtime（运行时层） | 生命周期状态一致性 | 4000 消息发进了黑洞 / 3005 TS错误 |

返回结构：

```json
{
  "ok": true,
  "ts_code": 2000,
  "ts_status": "TS ok :2000",
  "message": "OK",
  "layers": {
    "core": {"ok": true, "checks": ["config valid", "tool registry present", "..."]},
    "expand": {"ok": true, "checks": ["..."]},
    "extension": {"ok": true, "checks": ["..."]},
    "runtime": {"ok": true, "checks": ["..."]}
  }
}
```
