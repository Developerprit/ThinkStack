"""示例扩展 B：基于 SQLite 的长期记忆后端。

演示记忆接口（LongTermMemory）的完整实现与持久化。
通过 HOOK_CUSTOM_MEMORY 扩展点向框架注册自定义长期记忆后端。

公开接口：SqliteLongTermMemory, register_sqlite_memory
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Optional

from thinkstack import ExpandHook, LongTermMemory, expand_hook


class SqliteLongTermMemory(LongTermMemory):
    """SQLite 持久化的长期记忆后端。

    数据以 key-value 形式存入 SQLite，value 使用 JSON 序列化，
    支持任意可 JSON 化的数据类型。
    """

    def __init__(self, db_path: str = "thinkstack_memory.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

    def store(self, key: str, value: Any) -> None:
        """写入（或覆盖）一条长期记忆。"""
        payload = json.dumps(value, ensure_ascii=False, default=str)
        self._conn.execute(
            "INSERT INTO memory (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, payload),
        )
        self._conn.commit()

    def retrieve(self, key: str, default: Any = None) -> Any:
        """读取一条长期记忆，不存在返回 default。"""
        cur = self._conn.execute("SELECT value FROM memory WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return row[0]

    def clear(self) -> None:
        """清空全部长期记忆。"""
        self._conn.execute("DELETE FROM memory")
        self._conn.commit()

    def save(self) -> None:
        """持久化（SQLite 每次写已即时提交，此处确保落盘）。"""
        self._conn.commit()

    def load(self) -> None:
        """从数据库恢复（SQLite 连接打开即已就绪，无需额外动作）。"""
        pass

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()

    def __del__(self) -> None:  # 对象销毁时兜底关闭连接
        try:
            self._conn.close()
        except Exception:
            pass


@expand_hook(ExpandHook.HOOK_CUSTOM_MEMORY)
def register_sqlite_memory() -> SqliteLongTermMemory:
    """向框架注册 SQLite 长期记忆后端。"""
    db_path = os.environ.get("THINKSTACK_MEMORY_DB", "thinkstack_memory.db")
    return SqliteLongTermMemory(db_path=db_path)
