"""
缓存模块

提供高性能缓存系统，包括会话缓存、响应缓存、多级缓存等功能。
"""

from .cache_manager import CacheManager, get_cache_manager
from .thread_cache import ThreadCache
from .response_cache import ResponseCache
from .multi_level_cache import (
    cache_manager,
    cached,
    query_cached,
    warm_up_cache,
    MultiLevelCache,
    CacheConfig
)
from .manager import (
    advanced_cache_manager,
    CacheMetrics,
    schedule_cache_tasks,
    cache_user_session,
    get_cached_user_session,
    cache_api_key,
    invalidate_api_key_cache,
    cache_query_result,
    get_cached_query_result
)

__all__ = [
    # 原有缓存
    "CacheManager",
    "get_cache_manager",
    "ThreadCache",
    "ResponseCache",

    # 多级缓存
    "cache_manager",
    "advanced_cache_manager",
    "MultiLevelCache",
    "CacheConfig",
    "CacheMetrics",

    # 装饰器
    "cached",
    "query_cached",

    # 工具函数
    "warm_up_cache",
    "schedule_cache_tasks",
    "cache_user_session",
    "get_cached_user_session",
    "cache_api_key",
    "invalidate_api_key_cache",
    "cache_query_result",
    "get_cached_query_result",
]

# 初始化函数
async def init_cache():
    """初始化缓存系统"""
    # 初始化多级缓存
    await cache_manager.init()
    await warm_up_cache()

    # 启动定时任务
    import asyncio
    asyncio.create_task(schedule_cache_tasks())