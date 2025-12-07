"""
数据库连接管理
优化连接池配置和会话管理
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager, asynccontextmanager
from typing import Generator, Optional
import logging
import time

from config.config import settings

logger = logging.getLogger(__name__)

# 全局变量
_engine: Optional[object] = None
_session_factory: Optional[sessionmaker] = None

class DatabaseConfig:
    """数据库连接配置"""

    # 连接池配置
    POOL_SIZE = 20  # 连接池大小
    MAX_OVERFLOW = 30  # 最大溢出连接数
    POOL_TIMEOUT = 30  # 获取连接超时时间（秒）
    POOL_RECYCLE = 3600  # 连接回收时间（秒）
    POOL_PRE_PING = True  # 连接前检查

    # 查询配置
    QUERY_TIMEOUT = 30  # 查询超时时间（秒）
    ECHO_SQL = settings.LOG_LEVEL == "DEBUG"  # 是否打印SQL

def get_database_url() -> str:
    """获取数据库连接URL"""
    url = settings.DATABASE_URL
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")
    return url

def create_database_engine():
    """
    创建数据库引擎，优化连接池配置
    """
    global _engine

    if _engine is not None:
        return _engine

    url = get_database_url()

    # 连接池配置
    engine_kwargs = {
        "poolclass": QueuePool,
        "pool_size": DatabaseConfig.POOL_SIZE,
        "max_overflow": DatabaseConfig.MAX_OVERFLOW,
        "pool_timeout": DatabaseConfig.POOL_TIMEOUT,
        "pool_recycle": DatabaseConfig.POOL_RECYCLE,
        "pool_pre_ping": DatabaseConfig.POOL_PRE_PING,
        "echo": DatabaseConfig.ECHO_SQL,
        # 连接参数
        "connect_args": {
            "charset": "utf8mb4",
            "use_unicode": True,
            # 自动重连
            "autocommit": False,
            # 设置超时
            "connect_timeout": DatabaseConfig.QUERY_TIMEOUT,
            "read_timeout": DatabaseConfig.QUERY_TIMEOUT,
            "write_timeout": DatabaseConfig.QUERY_TIMEOUT,
        }
    }

    _engine = create_engine(url, **engine_kwargs)

    logger.info(f"Database engine created with pool_size={DatabaseConfig.POOL_SIZE}")

    return _engine

def get_session_factory():
    """获取会话工厂"""
    global _session_factory

    if _session_factory is not None:
        return _session_factory

    engine = create_database_engine()
    _session_factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False
    )

    return _session_factory

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    获取数据库会话（同步版本）

    使用示例:
        with get_db_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
    """
    session = get_session_factory()()

    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {str(e)}")
        raise
    finally:
        session.close()

class DatabaseMetrics:
    """数据库性能指标收集"""

    def __init__(self):
        self.query_count = 0
        self.total_time = 0.0
        self.slow_queries = []

    def record_query(self, duration: float, query: str = ""):
        """记录查询指标"""
        self.query_count += 1
        self.total_time += duration

        # 记录慢查询（超过1秒）
        if duration > 1.0:
            self.slow_queries.append({
                "query": query[:100],  # 只保存前100个字符
                "duration": duration
            })

    def get_stats(self) -> dict:
        """获取统计信息"""
        avg_time = self.total_time / self.query_count if self.query_count > 0 else 0

        return {
            "query_count": self.query_count,
            "total_time": self.total_time,
            "avg_time": avg_time,
            "slow_query_count": len(self.slow_queries),
            "slow_queries": self.slow_queries[-10:]  # 最近10个慢查询
        }

# 全局指标收集器
db_metrics = DatabaseMetrics()

class InstrumentedSession(Session):
    """带指标收集的数据库会话"""

    def execute(self, *args, **kwargs):
        start_time = time.time()

        try:
            result = super().execute(*args, **kwargs)

            # 记录查询指标
            duration = time.time() - start_time
            query_str = str(args[0]) if args else ""
            db_metrics.record_query(duration, query_str)

            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Query failed after {duration:.2f}s: {str(e)}")
            raise

def create_instrumented_session():
    """创建带监控的会话"""
    engine = create_database_engine()

    return sessionmaker(
        bind=engine,
        class_=InstrumentedSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False
    )()

def get_db_stats() -> dict:
    """获取数据库性能统计"""
    # 获取连接池状态
    engine = create_database_engine()

    pool_status = {
        "size": engine.pool.size(),
        "checked_in": engine.pool.checkedin(),
        "checked_out": engine.pool.checkedout(),
        "overflow": engine.pool.overflow(),
    }

    return {
        "pool": pool_status,
        "queries": db_metrics.get_stats()
    }

def test_database_connection():
    """测试数据库连接"""
    try:
        with get_db_session() as session:
            session.execute("SELECT 1")
        logger.info("Database connection test: PASSED")
        return True
    except Exception as e:
        logger.error(f"Database connection test: FAILED - {str(e)}")
        return False

def close_database_connections():
    """关闭所有数据库连接"""
    global _engine, _session_factory

    if _engine:
        _engine.dispose()
        _engine = None
        logger.info("Database engine disposed")

    _session_factory = None

# 健康检查
async def health_check() -> dict:
    """数据库健康检查"""
    try:
        with get_db_session() as session:
            start_time = time.time()
            result = session.execute("SELECT 1").fetchone()
            duration = time.time() - start_time

            return {
                "status": "healthy",
                "connection_time": duration,
                "pool_status": get_db_stats()["pool"]
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }