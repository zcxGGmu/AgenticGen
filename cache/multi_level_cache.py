"""
多级缓存系统实现
实现 L1(内存) + L2(Redis) + L3(数据库) 三级缓存架构
"""

import asyncio
import json
import time
import logging
from typing import Any, Optional, Dict, List, Union
from dataclasses import dataclass
from collections import OrderedDict
import hashlib
import pickle
from functools import wraps

import aioredis
from config.config import settings

logger = logging.getLogger(__name__)

@dataclass
class CacheConfig:
    """缓存配置"""
    # L1 缓存配置
    l1_max_size: int = 1000  # 最大条目数
    l1_ttl: int = 60  # 生存时间（秒）
    l1_max_memory_mb: int = 100  # 最大内存（MB）

    # L2 缓存配置
    l2_ttl: int = 300  # 5分钟
    l2_max_memory_mb: int = 1024  # 1GB

    # L3 缓存配置（查询结果缓存）
    l3_ttl: int = 1800  # 30分钟

class LRUCache:
    """LRU内存缓存实现"""

    def __init__(self, max_size: int, max_memory_mb: int):
        self.max_size = max_size
        self.max_memory = max_memory_mb * 1024 * 1024  # 转换为字节
        self.cache = OrderedDict()
        self.current_memory = 0
        self.hits = 0
        self.misses = 0

    def _estimate_size(self, value: Any) -> int:
        """估算对象大小"""
        try:
            return len(pickle.dumps(value))
        except:
            # 如果无法序列化，使用字符串长度估算
            return len(str(value)) * 2  # 假设每个字符2字节

    def _evict_if_needed(self, new_item_size: int):
        """如果需要，清理缓存"""
        while (len(self.cache) >= self.max_size or
               self.current_memory + new_item_size > self.max_memory):
            if not self.cache:
                break

            oldest_key, oldest_value = self.cache.popitem(last=False)
            self.current_memory -= self._estimate_size(oldest_value)

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self.cache:
            # 移动到最后（最近使用）
            value = self.cache.pop(key)
            self.cache[key] = value
            self.hits += 1
            return value

        self.misses += 1
        return None

    def set(self, key: str, value: Any, ttl: int = None):
        """设置缓存值"""
        # 如果已存在，先删除旧值
        if key in self.cache:
            old_value = self.cache.pop(key)
            self.current_memory -= self._estimate_size(old_value)

        # 估算新值大小
        new_size = self._estimate_size(value)

        # 清理空间
        self._evict_if_needed(new_size)

        # 设置新值
        self.cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl if ttl else None
        }
        self.current_memory += new_size

    def delete(self, key: str):
        """删除缓存"""
        if key in self.cache:
            value = self.cache.pop(key)
            self.current_memory -= self._estimate_size(value)

    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.current_memory = 0

    def get_expired_keys(self) -> List[str]:
        """获取过期的键"""
        now = time.time()
        expired = []

        for key, data in self.cache.items():
            if data['expires_at'] and data['expires_at'] < now:
                expired.append(key)

        return expired

    def cleanup_expired(self):
        """清理过期项"""
        expired_keys = self.get_expired_keys()
        for key in expired_keys:
            self.delete(key)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0

        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'size': len(self.cache),
            'memory_mb': self.current_memory / (1024 * 1024)
        }

class RedisCache:
    """Redis缓存层"""

    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.hits = 0
        self.misses = 0

    async def connect(self):
        """连接Redis"""
        if self.redis_client is None:
            try:
                self.redis_client = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding='utf-8',
                    decode_responses=True
                )
                # 测试连接
                await self.redis_client.ping()
                logger.info("Redis connected successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                raise

    def _make_key(self, key: str) -> str:
        """生成Redis键"""
        return f"agenticgen:cache:v2:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if not self.redis_client:
            await self.connect()

        try:
            redis_key = self._make_key(key)
            data = await self.redis_client.get(redis_key)

            if data:
                self.hits += 1
                # 前缀标记数据类型
                if data.startswith('json:'):
                    return json.loads(data[5:])
                elif data.startswith('pickle:'):
                    return pickle.loads(bytes.fromhex(data[7:]))
                else:
                    return data
            else:
                self.misses += 1
                return None
        except Exception as e:
            logger.error(f"Redis get error: {str(e)}")
            self.misses += 1
            return None

    async def set(self, key: str, value: Any, ttl: int = None):
        """设置缓存值"""
        if not self.redis_client:
            await self.connect()

        try:
            redis_key = self._make_key(key)

            # 序列化数据
            if isinstance(value, (dict, list)):
                data = f"json:{json.dumps(value)}"
            elif hasattr(value, '__dict__'):
                data = f"pickle:{pickle.dumps(value).hex()}"
            else:
                data = str(value)

            # 设置默认TTL
            if ttl is None:
                ttl = CacheConfig.l2_ttl

            await self.redis_client.setex(redis_key, ttl, data)
        except Exception as e:
            logger.error(f"Redis set error: {str(e)}")

    async def delete(self, key: str):
        """删除缓存"""
        if not self.redis_client:
            await self.connect()

        try:
            redis_key = self._make_key(key)
            await self.redis_client.delete(redis_key)
        except Exception as e:
            logger.error(f"Redis delete error: {str(e)}")

    async def clear(self, pattern: str = "*"):
        """清除缓存"""
        if not self.redis_client:
            await self.connect()

        try:
            redis_pattern = self._make_key(pattern)
            keys = await self.redis_client.keys(redis_pattern)
            if keys:
                await self.redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis clear error: {str(e)}")

    async def get_stats(self) -> Dict:
        """获取统计信息"""
        if not self.redis_client:
            await self.connect()

        try:
            info = await self.redis_client.info()
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0

            return {
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': hit_rate,
                'memory_mb': info.get('used_memory', 0) / (1024 * 1024),
                'connected_clients': info.get('connected_clients', 0)
            }
        except Exception as e:
            logger.error(f"Redis stats error: {str(e)}")
            return {}

class MultiLevelCache:
    """多级缓存管理器"""

    def __init__(self):
        self.config = CacheConfig()
        self.l1_cache = LRUCache(
            max_size=self.config.l1_max_size,
            max_memory_mb=self.config.l1_max_memory_mb
        )
        self.l2_cache = RedisCache()
        self.background_task = None

    async def init(self):
        """初始化"""
        await self.l2_cache.connect()
        # 启动后台清理任务
        self.background_task = asyncio.create_task(self._cleanup_task())

    async def _cleanup_task(self):
        """后台清理任务"""
        while True:
            try:
                # 每分钟清理一次
                await asyncio.sleep(60)
                self.l1_cache.cleanup_expired()
            except Exception as e:
                logger.error(f"Cache cleanup error: {str(e)}")

    def _make_key(self, key: str, namespace: str = "default") -> str:
        """生成缓存键"""
        # 使用MD5确保键的一致性
        full_key = f"{namespace}:{key}"
        return hashlib.md5(full_key.encode()).hexdigest()

    async def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取缓存值（三级）"""
        cache_key = self._make_key(key, namespace)

        # L1 缓存查找
        value = self.l1_cache.get(cache_key)
        if value is not None:
            # 检查是否过期
            if value['expires_at'] and value['expires_at'] < time.time():
                self.l1_cache.delete(cache_key)
            else:
                return value['value']

        # L2 缓存查找
        value = await self.l2_cache.get(cache_key)
        if value is not None:
            # 回填到L1
            self.l1_cache.set(cache_key, value, self.config.l1_ttl)
            return value

        # L3 缓存（数据库查询结果）
        # 这里由具体的查询方法处理
        return None

    async def set(self, key: str, value: Any, ttl: int = None, namespace: str = "default"):
        """设置缓存值（同时写入L1和L2）"""
        cache_key = self._make_key(key, namespace)

        # 设置L1缓存
        l1_ttl = ttl if ttl and ttl < self.config.l1_ttl else self.config.l1_ttl
        self.l1_cache.set(cache_key, value, l1_ttl)

        # 设置L2缓存
        l2_ttl = ttl if ttl and ttl < self.config.l2_ttl else self.config.l2_ttl
        await self.l2_cache.set(cache_key, value, l2_ttl)

    async def delete(self, key: str, namespace: str = "default"):
        """删除缓存"""
        cache_key = self._make_key(key, namespace)
        self.l1_cache.delete(cache_key)
        await self.l2_cache.delete(cache_key)

    async def clear_namespace(self, namespace: str):
        """清除命名空间的所有缓存"""
        pattern = f"{namespace}:*"
        await self.l2_cache.clear(pattern)
        # L1缓存需要逐个删除或直接清空
        self.l1_cache.clear()

    async def get_all_stats(self) -> Dict:
        """获取所有缓存层统计"""
        l1_stats = self.l1_cache.get_stats()
        l2_stats = await self.l2_cache.get_stats()

        return {
            'l1_memory_cache': l1_stats,
            'l2_redis_cache': l2_stats,
            'total_hit_rate': (
                (l1_stats['hits'] + l2_stats.get('hits', 0)) /
                (l1_stats['hits'] + l1_stats['misses'] + l2_stats.get('hits', 0) + l2_stats.get('misses', 0))
                if (l1_stats['hits'] + l1_stats['misses'] + l2_stats.get('hits', 0) + l2_stats.get('misses', 0)) > 0
                else 0
            )
        }

    async def close(self):
        """关闭缓存"""
        if self.background_task:
            self.background_task.cancel()
        self.l1_cache.clear()

# 全局缓存管理器实例
cache_manager = MultiLevelCache()

# 缓存装饰器
def cached(ttl: int = 300, namespace: str = "default"):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"

            # 尝试从缓存获取
            result = await cache_manager.get(cache_key, namespace)
            if result is not None:
                return result

            # 执行函数
            result = await func(*args, **kwargs)

            # 设置缓存
            await cache_manager.set(cache_key, result, ttl, namespace)

            return result
        return wrapper
    return decorator

# 查询结果缓存装饰器
def query_cached(ttl: int = 300):
    """专门用于数据库查询的缓存装饰器"""
    return cached(ttl=ttl, namespace="query")

# 预热缓存
async def warm_up_cache():
    """预热常用缓存"""
    # 预加载系统配置
    from config.config import settings
    await cache_manager.set(
        "system:config",
        {
            "app_name": settings.app_name,
            "version": settings.app_version,
            "features": ["chat", "code_exec", "knowledge_base"]
        },
        ttl=3600,
        namespace="system"
    )

    logger.info("Cache warm-up completed")