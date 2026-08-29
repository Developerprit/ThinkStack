# ThinkStack 🧵

> **一切皆为可编写的扩展** —— 一个模型无关、可扩展的 Python 3 Agent 框架。
> **Everything is a writable extension** —— a model-agnostic, extensible Python 3 Agent framework.

ThinkStack 将 Agent 的每一个组件（核心、工具、记忆、调度器、通信协议）都通过统一的 **ThinkStack Expand API** 对外开放，任何人都可以编写自定义扩展并无缝接入。

ThinkStack opens every Agent component (core, tools, memory, scheduler, protocols) through a unified **ThinkStack Expand API**, so anyone can write custom extensions and plug them in seamlessly.

---

## 特性 / Features

- **四层架构 / Four-layer architecture**：Core Layer（核心逻辑）、Expand API Layer（扩展接口）、Extension Layer（扩展实现）、Runtime Layer（运行时加载）。
- **模型无关 / Model-agnostic**：不绑定任何 AI 模型 SDK，`think()` 只依赖可插拔的推理后端抽象。
- **统一扩展 API / Unified Expand API**：`@expand_hook` 装饰器 + `register_extension()`，十个扩展点覆盖完整生命周期。
- **Markdown 渲染 / Markdown rendering**：内置纯标准库的 `markdown_to_html()`，把 LLM 输出的 Markdown 一键转 HTML，附 `markdown` 工具、`MarkdownAgent` 与 REST 端点。
- **安全隔离 / Sandbox isolation**：扩展加载/执行异常被隔离，单扩展失败不影响框架与其他扩展。
- **架构自检 / Architecture check**：`check_architecture()` 逐层检查 Core / Expand API / Extension / Runtime 四层架构，任一层报错即返回 TS 状态码（`TS error :<code>`，状态码清单见 `E:/PC/error.txt`），并提供 `GET /api/architecture/check` 端点。
- **Agent Skill 支持 / Agent Skills**：原生支持 [Agent Skills](https://agentskills.io/specification) 开放标准（Anthropic 发起）——加载 `SKILL.md` 技能目录、渐进式披露注入上下文、内置 `skill` 工具按需取指令。
- **内置运行时 / Built-in runtime**：9635 端口提供 REST API（含 SSE 流式、记忆 CRUD、扩展与 Skill 生命周期管理），`python -m thinkstack` 提供 CLI/REPL。Web UI 不再由框架自带，由各 Agent 应用自行铺设。
- **完整测试 / Full test suite**：59 个单元测试覆盖核心与扩展机制。

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

# 架构自检 / architecture self-check（返回 TS 状态码，如 TS ok :2000）
curl http://localhost:9635/api/architecture/check

# 框架信息（含版本号）/ framework info
curl http://localhost:9635/api/info

# 运行 Agent / run an agent
curl -X POST http://localhost:9635/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{"agent":"echo","input":"你好，ThinkStack","max_iterations":2}'

# 调用工具（示例天气工具）/ call a tool
curl -X POST http://localhost:9635/api/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"weather","args":{"city":"北京"}}'

# 列出已加载的 Agent Skill / list loaded agent skills
curl http://localhost:9635/api/skills

# 加载 Agent Skill（指向含 SKILL.md 的目录）/ load an agent skill
curl -X POST http://localhost:9635/api/skills/load \
  -H "Content-Type: application/json" \
  -d '{"path":"/path/to/my-skill"}'

# Markdown 转 HTML / render markdown to HTML
curl -X POST http://localhost:9635/api/markdown/render \
  -H "Content-Type: application/json" \
  -d '{"text":"# 标题\n\n**加粗**"}'

# 读写记忆 / read & write memory
curl -X POST http://localhost:9635/api/memory \
  -H "Content-Type: application/json" \
  -d '{"action":"store","kind":"working","key":"user","value":{"name":"陌老师"}}'

# 流式运行 Agent（SSE）/ stream an agent
curl -X POST http://localhost:9635/api/agent/run/stream \
  -H "Content-Type: application/json" \
  -d '{"agent":"echo","input":"你好","max_iterations":3}'
```

> v1.3.0 起框架不再自带 Web 控制台——Web UI 由各 Agent 应用自行铺设。
> Since v1.3.0 the framework ships no built-in web console — the Web UI is up to each agent application.

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

## Agent Skill 支持 / Agent Skills

ThinkStack 原生支持 [Agent Skills 开放标准](https://agentskills.io/specification)（Anthropic 发起维护），
技能即一个含 `SKILL.md` 的目录：

ThinkStack natively supports the [Agent Skills open standard](https://agentskills.io/specification) (initiated by Anthropic). A skill is a directory containing `SKILL.md`:

```
my-skill/
├── SKILL.md        # 必需：YAML frontmatter（name/description）+ Markdown 指令
├── scripts/        # 可选：可执行代码
├── references/     # 可选：参考文档
└── assets/         # 可选：模板与资源
```

`SKILL.md` 的 frontmatter 遵循标准字段：`name`（小写字母/数字/连字符，须与目录名一致）、`description`（必需）、`license`、`compatibility`、`metadata`、`allowed-tools`（可选）。

`SKILL.md` frontmatter follows the standard fields: `name` (lowercase letters/digits/hyphens, must match the directory name), `description` (required), plus optional `license`, `compatibility`, `metadata`, `allowed-tools`.

### 加载与使用 / Load & use

```python
from thinkstack import ThinkStack

stack = ThinkStack()
stack.load_skill("path/to/my-skill")   # 加载单个技能目录
stack.load_skill_dir("path/to/skills") # 扫描目录下全部技能
print(stack.list_skills())             # [{name, description}, ...]

# 渐进式披露：Agent 循环启动时自动注入全部技能摘要（ctx["skills"]），
# 需要完整指令时再通过内置 skill 工具按名称获取：
result = stack.call_tool("skill", skill="my-skill")
print(result.data)  # 完整指令 Markdown（含正文与资源清单）
```

REST 端点：`GET /api/skills`（列表）、`POST /api/skills/load`（`{"path": ...}`）、`POST /api/skills/unload`（`{"name": ...}`）。

---

## Markdown 渲染 / Markdown Rendering

LLM 输出多为 Markdown。ThinkStack 内置纯标准库的 `markdown_to_html()`，支持标题、加粗/斜体/删除线、行内代码、围栏代码块、链接、图片、列表、引用、表格、分隔线等常见语法。

```python
from thinkstack import markdown_to_html

html = markdown_to_html("# 标题\n\n**加粗** 和 `代码`")
# <h1>标题</h1><p><strong>加粗</strong> 和 <code>代码</code></p>
```

- 内置工具：`stack.call_tool("markdown", text="...")`
- 内置 Agent：`stack.run_agent(MarkdownAgent(), "# Hi")`
- REST 端点：`POST /api/markdown/render`

## CLI / 命令行

```bash
python -m thinkstack             # 启动 9635 端口 REST API
python -m thinkstack --port 9000 # 指定端口
python -m thinkstack --repl      # 交互式 REPL（无需 HTTP）
```

REPL 命令（英文输出）：`echo <text>`、`md <markdown>`、`tool <name> k=v ...`、`skills`（列出已加载 Agent Skill）、`arch`（架构自检，返回 TS 状态码）、`help`、`exit`。

---

## 十个扩展点 / Ten Extension Hooks

| 扩展点 / Hook | 说明 / Purpose |
| --- | --- |
| `HOOK_BEFORE_THINK` / `HOOK_AFTER_THINK` | 思考前后 / around thinking |
| `HOOK_BEFORE_ACTION` / `HOOK_AFTER_ACTION` | 行动前后 / around action |
| `HOOK_BEFORE_OBSERVE` / `HOOK_AFTER_OBSERVE` | 观察前后 / around observation |
| `HOOK_CUSTOM_TOOL` | 注册自定义工具 / register a tool |
| `HOOK_CUSTOM_MEMORY` | 注册自定义记忆 / register a memory |
| `HOOK_CUSTOM_SCHEDULER` | 注册自定义调度器 / register a scheduler |
| `HOOK_CUSTOM_AGENT` | 注册自定义 Agent / register an agent |

---

## TS 状态码 / TS Status Codes

ThinkStack 用统一的状态码表达错误与健康状态，对外格式：

- 通过 / OK：`TS ok :2000`
- 报错 / Error：`TS error :<code>`

状态码清单源自 `E:/PC/error.txt`，常量与工具函数均从 `thinkstack` 顶层导出。

Status codes follow a unified format — `TS ok :2000` on success, `TS error :<code>` on failure. The list originates from `E:/PC/error.txt`; all constants and helpers are exported from the `thinkstack` package top level.

| 状态码 / Code | 含义 / Meaning | 常量 / Constant |
| --- | --- | --- |
| `1001` | 扩展API错误（API本身错误）/ Extension API error | `TS_CODE_EXT_API_ERROR` |
| `1002` | 扩展错误 / Extension error | `TS_CODE_EXT_ERROR` |
| `2000` | OK,没问题 / OK | `TS_CODE_OK` |
| `3001` | LLM的token用没了 / LLM token exhausted | `TS_CODE_LLM_TOKEN_EXHAUSTED` |
| `3002` | URL 404 | `TS_CODE_URL_404` |
| `3003` | 模型ID 404 / Model ID 404 | `TS_CODE_MODEL_404` |
| `3004` | key错误 / Key error | `TS_CODE_KEY_ERROR` |
| `3005` | TS错误 / TS error | `TS_CODE_TS_ERROR` |
| `3404` | TS意外丢失 / TS unexpectedly lost | `TS_CODE_TS_LOST` |
| `4000` | 消息发进了黑洞 / Message lost to the black hole | `TS_CODE_BLACKHOLE` |
| `8000` | 未知错误 / Unknown error | `TS_CODE_UNKNOWN` |

`TS_CODE_MESSAGES` 为状态码 → 中文描述映射。

### 架构自检 / Architecture self-check

`stack.check_architecture()` 逐层检查四层架构，任一层报错即返回对应 TS 状态码，全部通过返回 2000：

| 层 / Layer | 失败状态码 / Failure code |
| --- | --- |
| Core（核心层） | `3404` TS意外丢失 / `3005` TS错误 |
| Expand API（扩展接口层） | `1001` 扩展API错误 |
| Extension（扩展层） | `1002` 扩展错误 |
| Runtime（运行时层） | `4000` 消息发进了黑洞 / `3005` TS错误 |

```python
from thinkstack import ThinkStack, ts_status

stack = ThinkStack()
result = stack.check_architecture()
print(result["ts_status"])   # 'TS ok :2000'（健康）/'TS error :1002'（报错）
print(ts_status(1002))       # 'TS error :1002'
```

```bash
# 通过 REST 端点获取架构自检结果
curl http://localhost:9635/api/architecture/check
```

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
thinkstack/        框架主包（core / expand / runtime 四层架构，含 core/skills.py）
examples/          3 个示例扩展（工具 / 记忆 / 调度器）
tests/             单元测试套件
docs/              API 参考文档
run.py             9635 端口启动入口
```

---

## 文档导航 / Documentation

- [API 参考 / API Reference](docs/API_REFERENCE.md) — 全部公开类、函数、枚举的签名与最小示例
- [实施计划 / Planning](Planning/Planning.md) — 四层架构设计与技术决策
- [许可证 / License](LICENSE.md) — Available License 全文
- [需求说明 / Requirements](要求.md) — 原始需求文档

---

## 许可证 / License

本项目采用 [Available License](LICENSE.md)（全文见仓库根目录 `LICENSE.md`）。
This project is licensed under the [Available License](LICENSE.md) (full text in `LICENSE.md`).

> 原文出处 / Source: https://license.kscm.top/available.md
