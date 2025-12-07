"""
数据库配置

管理数据库连接配置和连接池设置。
"""

from typing import Dict, Any

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from .config import settings


class DatabaseSettings:
    """数据库配置类"""

    def __init__(self):
        self.database_url = settings.database_url
        self.pool_size = settings.db_pool_size
        self.max_overflow = settings.db_max_overflow
        self._engine = None
        self._session_factory = None

    def create_engine(self) -> Any:
        """创建数据库引擎"""
        if self._engine is None:
            engine_kwargs = {
                "poolclass": QueuePool,
                "pool_size": self.pool_size,
                "max_overflow": self.max_overflow,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                "echo": settings.debug,
            }

            self._engine = create_engine(
                self.database_url,
                **engine_kwargs
            )

        return self._engine

    def create_session_factory(self) -> sessionmaker:
        """创建会话工厂"""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.create_engine()
            )

        return self._session_factory

    def get_engine(self):
        """获取数据库引擎"""
        return self.create_engine()

    def get_session_factory(self):
        """获取会话工厂"""
        return self.create_session_factory()

    def close_connections(self):
        """关闭所有数据库连接"""
        if self._engine:
            self._engine.dispose()


# 创建基础模型类
Base = declarative_base()

# 创建数据库配置实例
db_settings = DatabaseSettings()