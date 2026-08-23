# ThinkStack — 实施计划（Planning.md）

> 一个「一切皆为可编写的扩展」的 Python 3 Agent 框架。
> 本文件是项目启动前的技术方案与决策记录，交付于工作空间 `Planning/` 目录。

---

## 1. 项目定位

- **名称**：ThinkStack
- **语言/运行时**：Python 3.10+（本机实测 3.13.14）
- **核心哲学**：框架所有组件（Agent 核心、工具、记忆、调度器、通信协议）均通过统一的 **ThinkStack Expand API** 对外开放，任何人均可编写自定义扩展无缝接入。
- **模型无关**：不绑定任何 AI 模型 SDK，Agent 的 `think()` 只依赖一个可插拔的「推理后端」抽象；框架内置 `EchoReasoner`（回显推理器）作为开箱即用的占位实现。

---

## 2. 技术决策（已确认/已假设）

| 事项 | 决策 | 说明 |
|------|------|------|
| 依赖范围 | 仅标准库 + `pydantic` + `typing_extensions` | 严格遵循需求约束，HTTP 服务用标准库 `http.server` 实现，不引入 FastAPI/Flask |
| 9635 端口形态 | **纯 HTTP REST API**（JSON） | 任何语言/HTTP 客户端均可接入 |
| Web 控制台 | 通过 API 下发 `webrun <port>` 命令动态开启 | 控制台运行于指定端口，内置浅色/深色切换 |
| 数据结构 | 统一 `pydantic.BaseModel` | 类型注解用 `typing` / `typing_extensions` |
| 扩展加载 | `importlib.util.spec_from_file_location` | 严禁 `eval`/`exec`/`__import__` |
| 注释/文档语言 | 简体中文 | 代码、注释、docstring、文档统一中文 |
| 编码风格 | 标准库 → 第三方 → 本地模块 排序 import | 模块级 docstring：一行简述 + 公开接口列表 |

---

## 3. 四层架构与模块关系

### 3.1 分层总览

```
┌─────────────────────────────────────────────────────────┐
│  Extension Layer（扩展实现）                               │
│  examples/weather_tool  ·  examples/sqlite_memory         │
│  examples/round_robin_scheduler                           │
├─────────────────────────────────────────────────────────┤
│  Expand API Layer（扩展接口）                              │
│  @expand_hook · register_extension · ExpandHook           │
│  ExtensionHandle · ExtensionLoader                        │
├─────────────────────────────────────────────────────────┤
│  Core Layer（核心逻辑）                                    │
│  ThinkStack · Agent · Tool · Memory · Scheduler · Config  │
│  Reasoner（推理后端抽象） · errors（异常体系）               │
├─────────────────────────────────────────────────────────┤
│  Runtime Layer（运行时加载）                                │
│  HttpServer(9635) · WebConsole(动态端口) · 扩展加载器       │
└─────────────────────────────────────────────────────────┘
```

### 3.2 模块关系表

| 层 | 模块名 | 核心职责 | 依赖方向 |
|----|--------|----------|----------|
| Core | `thinkstack.config` | `Config` 配置数据类，统一配置入口 | → (无) |
| Core | `thinkstack.errors` | `ThinkStackError` 异常体系 | → (无) |
| Core | `thinkstack.core.agent` | `Agent` 抽象基类，「思考→行动→观察」循环 | → Tool, Memory, Reasoner |
| Core | `thinkstack.core.tool` | `Tool` 注册表 + 参数校验 + `ToolResult` | → errors |
| Core | `thinkstack.core.memory` | `ShortTermMemory` / `LongTermMemory` / `WorkingMemory` | → errors |
| Core | `thinkstack.core.scheduler` | `SerialScheduler` / `ParallelScheduler` / `PriorityScheduler` | → errors |
| Core | `thinkstack.core.reasoner` | `Reasoner` 推理后端抽象（模型无关） | → (无) |
| Core | `thinkstack.stack` | `ThinkStack` 主入口类，生命周期管理 | → 上述全部 + expand |
| Expand | `thinkstack.expand.hooks` | `ExpandHook` 扩展点枚举 | → (无) |
| Expand | `thinkstack.expand.handle` | `ExtensionHandle` 扩展句柄 | → errors |
| Expand | `thinkstack.expand.api` | `@expand_hook` + `register_extension` | → hooks, loader |
| Expand | `thinkstack.expand.loader` | 扩展动态加载/校验/隔离 | → hooks, errors |
| Runtime | `thinkstack.runtime.server` | 9635 HTTP REST API 服务器 | → stack |
| Runtime | `thinkstack.runtime.webconsole` | Web 控制台（`webrun <port>`） | → stack |

---

## 4. 核心数据流

```
用户请求(HTTP)
   │
   ▼
ThinkStack.run_agent() ──▶ [HOOK_BEFORE_THINK] ──▶ Agent.think() ──▶ [HOOK_AFTER_THINK]
   │                                                    │
   │                                        Reasoning(可选调用 Reasoner)
   ▼                                                    │
Agent.act() ◀── [HOOK_AFTER_ACTION] ◀── Tool 调用 ◀── [HOOK_BEFORE_ACTION]
   │
   ▼
Agent.observe() ──▶ [HOOK_BEFORE_OBSERVE] ──▶ 记忆读写(Memory) ──▶ [HOOK_AFTER_OBSERVE]
   │
   ▼
结果封装(ToolResult / AgentResult) ──▶ HTTP 响应返回
```

- 任务分发由 `Scheduler` 统一管理，三种策略（串行/并行/优先级）可插拔。
- 每个「钩子点」前后都可挂自定义扩展，扩展异常被隔离，不影响主流程。

---

## 5. 目录结构

```
E:\PC\ThinkStack\
├── Planning\Planning.md            # 本文件
├── thinkstack\                     # 框架主包
│   ├── __init__.py                 # 顶层导出
│   ├── config.py                   # Config 配置类
│   ├── errors.py                   # 异常体系
│   ├── core\
│   │   ├── agent.py                # Agent 抽象基类
│   │   ├── tool.py                 # Tool 注册表 + ToolResult
│   │   ├── memory.py               # 三类记忆接口
│   │   ├── scheduler.py            # 三种调度策略
│   │   ├── reasoner.py             # 推理后端抽象 + EchoReasoner
│   │   └── stack.py                # ThinkStack 主入口
│   ├── expand\
│   │   ├── hooks.py                # ExpandHook 枚举
│   │   ├── handle.py               # ExtensionHandle
│   │   ├── api.py                  # @expand_hook / register_extension
│   │   └── loader.py               # 扩展加载器
│   └── runtime\
│       ├── server.py               # 9635 HTTP REST API
│       └── webconsole.py           # Web 控制台(浅/深色)
├── examples\                       # 3 个示例扩展
│   ├── weather_tool\weather.py
│   ├── sqlite_memory\sqlite_memory.py
│   └── round_robin_scheduler\round_robin.py
├── tests\
│   ├── test_core.py
│   └── test_expand.py
├── docs\API_REFERENCE.md
├── README.md
├── run.py                          # 启动入口(9635)
└── pyproject.toml
```

---

## 6. 关键设计要点

1. **Expand API**：`@expand_hook(ExpandHook.X)` 装饰器把函数挂到扩展点；`register_extension(name, module_path)` 动态加载并返回 `ExtensionHandle`。
2. **扩展句柄**：`enable()` / `disable()` / `unload()` + 只读 `is_active`。
3. **扩展隔离**：每个扩展初始化包 `try/except`，失败抛 `ExtensionLoadError`，不崩溃框架，其余扩展继续加载。
4. **访问控制**：扩展禁止直接访问 `_private` 成员，违者抛 `ExtensionAccessError`。
5. **签名校验**：注册时校验函数签名是否匹配钩子约定，不符抛 `ExtensionValidationError`。
6. **输入防护**：公开方法校验类型/范围，异常统一转 `ThinkStackError` 体系。
7. **HTTP 服务**：`/api/...` REST 端点 + `/command` 命令通道（支持 `webrun <port>`）。
8. **Web 控制台**：内嵌单文件 HTML，浅色/深色可切换，展示运行态与交互入口。

---

## 7. 验证与交付

- 测试：`python -m pytest -v` 全绿，无外部依赖。
- 运行：`python run.py` 启动 9635 端口；`curl` 验证 REST API 与 `webrun <port>` 命令。
- 交付物：`ThinkStack.zip`（全部内容）+ `run.py`（9635 入口）。
