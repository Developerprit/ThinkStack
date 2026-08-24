"""可插拔日志：基于标准库 logging 的轻量封装。

公开接口：setup_logger
"""

from __future__ import annotations

import logging

from thinkstack.config import LogConfig


def setup_logger(name: str, config: LogConfig) -> logging.Logger:
    """创建并配置一个独立 logger（可插拔到控制台或文件）。

    参数：
        name: logger 名称。
        config: 日志配置（级别与可选文件路径）。

    返回：
        配置完成的 logging.Logger 实例。
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.level, logging.INFO))
    # 清空既有 handler，避免重复输出
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    if config.file:
        handler: logging.Handler = logging.FileHandler(config.file, encoding="utf-8")
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
