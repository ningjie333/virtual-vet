"""统一日志配置"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger，首次调用时初始化 root 配置"""
    logger = logging.getLogger(name)

    # 只在 root logger 未配置时初始化一次
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    return logger
