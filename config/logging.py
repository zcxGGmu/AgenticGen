"""
日志配置

配置应用程序的日志系统，包括日志格式、级别和文件管理。
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from .config import settings


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_rotation: Optional[str] = None,
    log_retention: Optional[str] = None,
):
    """
    设置日志配置

    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        log_rotation: 日志轮转设置
        log_retention: 日志保留时间
    """
    # 移除默认的处理器
    logger.remove()

    # 设置日志级别
    level = log_level or settings.log_level

    # 添加控制台处理器
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # 添加文件处理器
    file_path = log_file or settings.log_file
    if file_path:
        # 确保日志目录存在
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            file_path,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=level,
            rotation=log_rotation or settings.log_rotation,
            retention=log_retention or settings.log_retention,
            compression="zip",
            backtrace=True,
            diagnose=True,
            encoding="utf-8",
        )

    return logger


def get_logger(name: Optional[str] = None):
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的日志记录器
    """
    if name:
        return logger.bind(name=name)
    return logger


# 初始化日志系统
setup_logging()