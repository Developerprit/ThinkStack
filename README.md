# ThinkStack 🧵

> **一切皆为可编写的扩展** —— 一个模型无关、可扩展的 Python 3 Agent 框架。
> **Everything is a writable extension** —— a model-agnostic, extensible Python 3 Agent framework.

ThinkStack 将 Agent 的每一个组件（核心、工具、记忆、调度器、通信协议）都通过统一的 **ThinkStack Expand API** 对外开放，任何人都可以编写自定义扩展并无缝接入。

ThinkStack opens every Agent component (core, tools, memory, scheduler, protocols) through a unified **ThinkStack Expand API**, so anyone can write custom extensions and plug them in seamlessly.

---

## 特性 / Features

- **四层架构 / Four-layer architecture**：Core Layer（核心逻辑）、Expand API Layer（扩展接口）、Extension Layer（扩展实现）、Runtime Layer（运行时加载）。
- **模型无关 / Model-agnostic**：不绑定任何 AI 模型 SDK，`think()` 只依赖可插拔的推理后端抽象。
- **统一扩展 API / Unified Expand API**：`@expand_hook` 装饰器 + `register_extension()`，九个扩展点覆盖完整生命周期。
- **安全隔离 / Sandbox isolation**：扩展加载/执行异常被隔离，单扩展失败不影响框架与其他扩展。
- **内置运行时 / Built-in runtime**：9635 端口提供 REST API，`webrun <port>` 命令动态开启浅/深色 Web 控制台。
- **完整测试 / Full test suite**：28 个单元测试覆盖核心与扩展机制。

---

## 安装 / Installation

要求 Python 3.10+。

```bash
pip install pydantic>=2.0 typing-extensions>=4.0
# 开发测试（可选 / optional）
pip install pytest>=7.0
```

无需安装即可直接运行：克隆/解压本仓库后，在项目根目录执行即可。

No installation required: clone or unzip this repository and run from the project root.

---

## 快速开始 / Quick Start

### 1. 启动框架（9635 端口）

```bash
python run.py
```

启动后，任何人都可通过 HTTP 接入 9635 端口构建 Agent 应用：

```
REST API : http://0.0.0.0:9635
Health   : http://localhost:9635/api/health
Info     : http://localhost:9635/api/info
```

### 2. 调用 REST API

```bash
# 健康检查 / health
curl http://localhost:9635/api/health

# 运行 Agent / run an agent
curl -X POST http://localhost:9635/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{"agent":"echo","input":"你好，ThinkStack","max_iterations":2}'

# 调用工具（示例天气工具）/ call a tool
curl -X POST http://localhost:9635/api/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"weather","args":{"city":"北京"}}'

# 开启 Web 控制台（在 8080 端口）/ open the web console on port 8080
curl -X POST http://localhost:9635/api/command \
  -H "Content-Type: application/json" \
  -d '{"command":"webrun 8080"}'
```

然后访问 `http://localhost:8080/` 查看可切换浅色/深色的 Web 控制台。
Then visit `http://localhost:8080/` to see the light/dark web console.

### 3. 用代码接入

```python
from thinkstack import ThinkStack, EchoAgent

stack = ThinkStack()
stack.start()

result = stack.run_agent(EchoAgent(), "你好", max_iterations=3)
print(result.output)
stack.shutdown()
```

---

## 扩展开发指南 / Extension Development Guide

扩展是一个带 `@expand_hook` 装饰器标记的独立 `.py` 文件，通过 `register_extension(name, module_path)` 动态加载。
An extension is a standalone `.py` file with `@expand_hook` markers, loaded via `register_extension(name, module_path)`.

### 示例 A：自定义工具 / Custom tool

```python
from pydantic import BaseModel, Field
from thinkstack import ExpandHook, FunctionTool, expand_hook

class WeatherInput(BaseModel):
    city: str = Field(description="城市名称")

def _query(city: str) -> str:
    return f"{city} 晴"

@expand_hook(ExpandHook.HOOK_CUSTOM_TOOL)
def register_tool() -> FunctionTool:
    return FunctionTool(name="weather", description="查询天气",
                        input_schema=WeatherInput, func=_query)
```

接入 / Register:

```python
stack.register_extension("weather", "path/to/weather.py")
stack.start()
stack.call_tool("weather", city="北京")
```

### 示例 B：自定义记忆后端 / Custom memory backend

```python
from thinkstack import ExpandHook, LongTermMemory, expand_hook

class SqliteLongTermMemory(LongTermMemory):
    # 实现 store / retrieve / clear / save / load ...

@expand_hook(ExpandHook.HOOK_CUSTOM_MEMORY)
def register_memory():
    return SqliteLongTermMemory()
```

接入后，`stack.long_term_memory` 会被替换为自定义后端。
After registration, `stack.long_term_memory` is replaced by your backend.

### 示例 C：自定义调度器 / Custom scheduler

```python
from thinkstack import ExpandHook, Scheduler, expand_hook

class RoundRobinScheduler(Scheduler):
    # 实现 run_all ...

@expand_hook(ExpandHook.HOOK_CUSTOM_SCHEDULER)
def register_scheduler():
    return RoundRobinScheduler()
```

接入后通过 `stack.custom_schedulers` 获取实例。
After registration, retrieve it from `stack.custom_schedulers`.

> 完整示例见 `examples/` 目录，每个扩展附独立的 `pyproject.toml` 说明依赖与接入方式。
> Full examples are under `examples/`, each with its own `pyproject.toml`.

---

## 九个扩展点 / Nine Extension Hooks

| 扩展点 / Hook | 说明 / Purpose |
| --- | --- |
| `HOOK_BEFORE_THINK` / `HOOK_AFTER_THINK` | 思考前后 / around thinking |
| `HOOK_BEFORE_ACTION` / `HOOK_AFTER_ACTION` | 行动前后 / around action |
| `HOOK_BEFORE_OBSERVE` / `HOOK_AFTER_OBSERVE` | 观察前后 / around observation |
| `HOOK_CUSTOM_TOOL` | 注册自定义工具 / register a tool |
| `HOOK_CUSTOM_MEMORY` | 注册自定义记忆 / register a memory |
| `HOOK_CUSTOM_SCHEDULER` | 注册自定义调度器 / register a scheduler |

---

## 测试 / Tests

```bash
python -m pytest -v
```

覆盖 Agent 循环、工具注册调用、记忆读写、调度器分发、扩展加载/钩子顺序/隔离性。

Covers the agent loop, tool registry, memory, schedulers, and extension loading/hook ordering/isolation.

---

## 目录结构 / Project Layout

```
thinkstack/        框架主包（core / expand / runtime 四层架构）
examples/          3 个示例扩展（工具 / 记忆 / 调度器）
tests/             单元测试套件
docs/              API 参考文档
run.py             9635 端口启动入口
```

---

## 许可证 / License

[Available License](https://license.kscm.top/available.md)
