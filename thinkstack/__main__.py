"""ThinkStack 命令行入口。

用法：
    python -m thinkstack              # 启动 9635 端口 REST API 服务器
    python -m thinkstack --port 9000  # 指定端口
    python -m thinkstack --no-examples# 不加载示例扩展
    python -m thinkstack --repl       # 交互式 REPL（无需 HTTP）

所有命令行输出均为英文。
"""

from __future__ import annotations

import argparse
import os

from thinkstack import EchoAgent, MarkdownAgent, ThinkStack


def _example_extensions() -> list[tuple[str, str]]:
    """返回示例扩展 (名称, 相对路径) 列表。"""
    return [
        ("weather", os.path.join("weather_tool", "weather.py")),
        ("sqlite_memory", os.path.join("sqlite_memory", "sqlite_memory.py")),
        ("round_robin", os.path.join("round_robin_scheduler", "round_robin.py")),
        ("markdown_agent", os.path.join("markdown_agent", "markdown_agent.py")),
    ]


def build_stack(load_examples: bool = True) -> ThinkStack:
    """创建并配置 ThinkStack 实例。"""
    examples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
    stack = ThinkStack()
    if load_examples:
        for name, rel in _example_extensions():
            path = os.path.join(examples_dir, rel)
            if not os.path.exists(path):
                continue
            try:
                handle = stack.register_extension(name, path)
                print(f"[extension] loaded '{name}' -> active={handle.is_active}")
            except Exception as exc:
                print(f"[extension] failed to load '{name}': {exc}")
    stack.start()
    return stack


def run_server(args: argparse.Namespace) -> None:
    """启动 REST API 服务器。"""
    from thinkstack import ThinkStackServer

    stack = build_stack(load_examples=not args.no_examples)
    server = ThinkStackServer(stack, host=args.host, port=args.port)
    server.start(block=False)

    arch = stack.check_architecture()
    print("[archcheck] " + arch["ts_status"] + (" — " + arch["message"] if not arch["ok"] else " — all layers healthy"))
    print("=" * 60)
    print("ThinkStack Agent Framework is running")
    print(f"  REST API : http://{args.host}:{args.port}")
    print(f"  Health   : http://localhost:{args.port}/api/health")
    print(f"  Info     : http://localhost:{args.port}/api/info")
    print(f"  Skills   : http://localhost:{args.port}/api/skills")
    print("=" * 60)

    try:
        import time

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        stack.shutdown()


def run_repl() -> None:
    """交互式 REPL：无需 HTTP 即可体验 Agent 与工具。"""
    stack = build_stack(load_examples=True)

    print("ThinkStack REPL. Type 'help' for commands, 'exit' to quit.")
    while True:
        try:
            raw = input("thinkstack> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not raw:
            continue
        head, _, rest = raw.partition(" ")
        cmd = head.lower()

        if cmd in ("exit", "quit"):
            print("Bye.")
            break
        if cmd == "help":
            print("Commands:")
            print("  echo <text>          Run the echo agent")
            print("  md <markdown>        Render markdown to HTML")
            print("  tool <name> k=v ...  Call a tool (e.g. tool weather city=Beijing)")
            print("  skills               List loaded Agent Skills")
            print("  arch                 Run the architecture self-check (TS status code)")
            print("  help                 Show this help")
            print("  exit                 Quit")
            continue
        if cmd == "skills":
            loaded = stack.list_skills()
            if not loaded:
                print("[skills] none loaded")
            else:
                for s in loaded:
                    print(f"[skills] {s['name']}: {s['description']}")
            continue
        if cmd == "arch":
            result = stack.check_architecture()
            line = result["ts_status"]
            if not result["ok"]:
                line += f" ({result['message']})"
            print(f"[archcheck] {line}")
            continue
        if cmd == "echo":
            result = stack.run_agent(EchoAgent(), rest or "hello", max_iterations=1)
            print(result.output)
            continue
        if cmd == "md":
            result = stack.run_agent(MarkdownAgent(), rest or "**hello**", max_iterations=1)
            print(result.output.get("html", ""))
            continue
        if cmd == "tool":
            parts = rest.split()
            if not parts:
                print("Usage: tool <name> key=value ...")
                continue
            tool_name = parts[0]
            kwargs = {}
            for item in parts[1:]:
                if "=" in item:
                    k, v = item.split("=", 1)
                    kwargs[k] = v
            result = stack.call_tool(tool_name, **kwargs)
            print(result.model_dump())
            continue
        print(f"Unknown command '{cmd}'. Type 'help' for commands.")

    stack.shutdown()


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="ThinkStack Agent Framework")
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9635, help="REST API port (default: 9635)")
    parser.add_argument(
        "--no-examples", action="store_true", help="do not load example extensions"
    )
    parser.add_argument("--repl", action="store_true", help="start interactive REPL")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.repl:
        run_repl()
    else:
        run_server(args)


if __name__ == "__main__":
    main()
