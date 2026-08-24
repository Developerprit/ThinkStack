"""ThinkStack 启动入口。

运行本文件后将在 9635 端口启动 ThinkStack REST API 客户端，
任何人都可接入该客户端构建属于自己的 Agent 应用。
通过 API 命令通道下发 `webrun <port>` 可动态开启 Web 控制台。

用法：
    python run.py                 # 默认 0.0.0.0:9635
    python run.py --port 9000     # 指定端口
    python run.py --no-examples   # 不加载示例扩展
"""

from __future__ import annotations

import argparse
import os

from thinkstack import ThinkStack, ThinkStackServer

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")

# 示例扩展：(名称, 相对路径)
_EXAMPLE_EXTENSIONS = [
    ("weather", os.path.join("weather_tool", "weather.py")),
    ("sqlite_memory", os.path.join("sqlite_memory", "sqlite_memory.py")),
    ("round_robin", os.path.join("round_robin_scheduler", "round_robin.py")),
    ("markdown_agent", os.path.join("markdown_agent", "markdown_agent.py")),
]


def build_stack(load_examples: bool = True) -> ThinkStack:
    """创建并配置 ThinkStack 实例。"""
    stack = ThinkStack()
    if load_examples:
        for name, rel in _EXAMPLE_EXTENSIONS:
            path = os.path.join(EXAMPLES_DIR, rel)
            try:
                handle = stack.register_extension(name, path)
                print(f"[extension] loaded '{name}' -> active={handle.is_active}")
            except Exception as exc:
                print(f"[extension] failed to load '{name}': {exc}")
    stack.start()
    return stack


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="ThinkStack Agent Framework server")
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9635, help="REST API port (default: 9635)")
    parser.add_argument(
        "--no-examples", action="store_true", help="do not load example extensions"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stack = build_stack(load_examples=not args.no_examples)

    server = ThinkStackServer(stack, host=args.host, port=args.port)
    server.start(block=False)

    print("=" * 60)
    print("ThinkStack Agent Framework is running")
    print(f"  REST API : http://{args.host}:{args.port}")
    print(f"  Health   : http://localhost:{args.port}/api/health")
    print(f"  Info     : http://localhost:{args.port}/api/info")
    print("  Open a Web console by POST /api/command with body")
    print('  {"command": "webrun 8080"}  ->  http://localhost:8080/')
    print("=" * 60)

    try:
        # 主线程阻塞，保持服务运行
        while True:
            import time

            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        stack.shutdown()


if __name__ == "__main__":
    main()
