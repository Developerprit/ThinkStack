"""test_archcheck.py —— 覆盖 TS 状态码与四层架构自检（check_architecture）。

状态码定义见 E:/PC/error.txt，对外格式为 "TS error :<code>" / "TS ok :<code>"。
"""

from __future__ import annotations

import json
import os
import urllib.request

from thinkstack import (
    ThinkStack,
    ThinkStackServer,
    TS_CODE_EXT_API_ERROR,
    TS_CODE_EXT_ERROR,
    TS_CODE_OK,
    TS_CODE_TS_LOST,
    ts_status,
)

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
WEATHER_PATH = os.path.join(EXAMPLES_DIR, "weather_tool", "weather.py")


# ---------------------------------------------------------------- TS 状态码格式

def test_ts_status_format():
    assert ts_status(2000) == "TS ok :2000"
    assert ts_status(1002) == "TS error :1002"
    assert ts_status(3404) == "TS error :3404"
    assert ts_status(8000) == "TS error :8000"


# ---------------------------------------------------------------- 健康架构

def test_healthy_architecture_returns_2000():
    stack = ThinkStack()
    stack.start()
    result = stack.check_architecture()
    assert result["ok"] is True
    assert result["ts_code"] == TS_CODE_OK
    assert result["ts_status"] == "TS ok :2000"
    assert result["message"] == "OK"
    assert set(result["layers"]) == {"core", "expand", "extension", "runtime"}
    for layer in result["layers"].values():
        assert layer["ok"] is True
    stack.shutdown()


def test_archcheck_not_started_is_still_ok():
    # 未 start() 时生命周期一致（not running 是合法状态），应返回 2000
    stack = ThinkStack()
    result = stack.check_architecture()
    assert result["ok"] is True
    assert result["ts_code"] == TS_CODE_OK


# ---------------------------------------------------------------- 各层报错

def test_missing_core_component_returns_3404():
    stack = ThinkStack()
    stack.tools = None  # 破坏核心层：工具注册表丢失
    result = stack.check_architecture()
    assert result["ok"] is False
    assert result["ts_code"] == TS_CODE_TS_LOST
    assert result["ts_status"].startswith("TS error :")
    assert result["layers"]["core"]["ok"] is False
    assert "tool registry" in "; ".join(result["layers"]["core"]["checks"])


def test_broken_expand_api_returns_1001():
    stack = ThinkStack()
    stack._registry = None  # 破坏扩展 API 层：注册表丢失
    result = stack.check_architecture()
    assert result["ok"] is False
    assert result["ts_code"] == TS_CODE_EXT_API_ERROR
    assert result["layers"]["expand"]["ok"] is False


def test_inactive_extension_returns_1002():
    stack = ThinkStack()
    handle = stack.register_extension("weather", WEATHER_PATH)
    handle.disable()  # 扩展未激活 → 扩展层报错
    result = stack.check_architecture()
    assert result["ok"] is False
    assert result["ts_code"] == TS_CODE_EXT_ERROR
    assert result["layers"]["extension"]["ok"] is False
    assert "inactive" in "; ".join(result["layers"]["extension"]["checks"])


# ---------------------------------------------------------------- REST 端点

def test_rest_architecture_check_endpoint():
    stack = ThinkStack()
    stack.start()
    server = ThinkStackServer(stack, host="127.0.0.1", port=0)
    server.start(block=False)
    port = server._httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        body = json.loads(
            urllib.request.urlopen(f"{base}/api/architecture/check").read().decode()
        )
        assert body["ok"] is True
        assert body["ts_status"] == "TS ok :2000"

        info = json.loads(urllib.request.urlopen(f"{base}/api/info").read().decode())
        assert info["version"] == "1.3.0"

        health = json.loads(urllib.request.urlopen(f"{base}/api/health").read().decode())
        assert health["ts"] == "TS ok :2000"
    finally:
        server.shutdown()
        stack.shutdown()
