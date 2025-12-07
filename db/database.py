"""
数据库连接管理

提供数据库会话管理和连接池功能。
"""

from typing import Generator

from sqlalchemy.orm import Session

from config.database import db_settings


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话

    Returns:
        数据库会话生成器
    """
    session_factory = db_settings.get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """
    获取新的数据库会话

    Returns:
        数据库会话
    """
    session_factory = db_settings.get_session_factory()
    return session_factory()