"""
缓存管理器

提供Redis缓存的核心功能和操作接口。
"""

import json
import pickle
from datetime import timedelta
from typing import Any, Optional, Union, List

import aioredis
from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self.redis_url = settings.redis_url
        self._async_redis: Optional[AsyncRedis] = None
        self._sync_redis: Optional[SyncRedis] = None

    async def get_async_redis(self) -> AsyncRedis:
        """获取异步Redis客户端"""
        if self._async_redis is None:
            self._async_redis = AsyncRedis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._async_redis

    def get_sync_redis(self) -> SyncRedis:
        """获取同步Redis客户端"""
        if self._sync_redis is None:
            self._sync_redis = SyncRedis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._sync_redis

    # 基础缓存操作
    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[Union[int, timedelta]] = None,
        serialize_method: str = "json"
    ) -> bool:
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒或timedelta）
            serialize_method: 序列化方法（json/pickle）

        Returns:
            是否成功
        """
        try:
            redis = await self.get_async_redis()

            # 序列化值
            if serialize_method == "json":
                serialized_value = json.dumps(value, ensure_ascii=False)
            elif serialize_method == "pickle":
                serialized_value = pickle.dumps(value)
            else:
                serialized_value = str(value)

            # 设置缓存
            if expire is None:
                await redis.set(key, serialized_value)
            elif isinstance(expire, timedelta):
                await redis.setex(key, int(expire.total_seconds()), serialized_value)
            else:
                await redis.setex(key, expire, serialized_value)

            logger.debug(f"缓存设置成功: {key}")
            return True

        except Exception as e:
            logger.error(f"缓存设置失败 {key}: {str(e)}")
            return False

    async def get(
        self,
        key: str,
        deserialize_method: str = "json",
        default: Any = None
    ) -> Any:
        """
        获取缓存

        Args:
            key: 缓存键
            deserialize_method: 反序列化方法
            default: 默认值

        Returns:
            缓存值或默认值
        """
        try:
            redis = await self.get_async_redis()
            value = await redis.get(key)

            if value is None:
                return default

            # 反序列化值
            if deserialize_method == "json":
                return json.loads(value)
            elif deserialize_method == "pickle":
                return pickle.loads(value.encode())
            else:
                return value

        except Exception as e:
            logger.error(f"缓存获取失败 {key}: {str(e)}")
            return default

    async def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否成功
        """
        try:
            redis = await self.get_async_redis()
            result = await redis.delete(key)
            logger.debug(f"缓存删除: {key}, 结果: {result}")
            return result > 0

        except Exception as e:
            logger.error(f"缓存删除失败 {key}: {str(e)}")
            return False

    async def exists(self, key: str) -> bool:
        """
        检查缓存是否存在

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        try:
            redis = await self.get_async_redis()
            return await redis.exists(key) > 0

        except Exception as e:
            logger.error(f"缓存存在性检查失败 {key}: {str(e)}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置缓存过期时间

        Args:
            key: 缓存键
            seconds: 过期秒数

        Returns:
            是否成功
        """
        try:
            redis = await self.get_async_redis()
            return await redis.expire(key, seconds)

        except Exception as e:
            logger.error(f"设置缓存过期时间失败 {key}: {str(e)}")
            return False

    async def ttl(self, key: str) -> int:
        """
        获取缓存剩余生存时间

        Args:
            key: 缓存键

        Returns:
            剩余秒数（-1表示永不过期，-2表示不存在）
        """
        try:
            redis = await self.get_async_redis()
            return await redis.ttl(key)

        except Exception as e:
            logger.error(f"获取缓存TTL失败 {key}: {str(e)}")
            return -2

    # 批量操作
    async def mset(self, mapping: dict, expire: Optional[int] = None) -> bool:
        """
        批量设置缓存

        Args:
            mapping: 键值对字典
            expire: 过期时间（秒）

        Returns:
            是否成功
        """
        try:
            redis = await self.get_async_redis()

            # 序列化所有值
            serialized_mapping = {}
            for key, value in mapping.items():
                serialized_mapping[key] = json.dumps(value, ensure_ascii=False)

            # 批量设置
            if expire is None:
                await redis.mset(serialized_mapping)
            else:
                # 使用pipeline提高性能
                pipe = redis.pipeline()
                for key, value in serialized_mapping.items():
                    pipe.setex(key, expire, value)
                await pipe.execute()

            logger.debug(f"批量缓存设置成功: {len(mapping)} 个键")
            return True

        except Exception as e:
            logger.error(f"批量缓存设置失败: {str(e)}")
            return False

    async def mget(self, keys: List[str]) -> List[Any]:
        """
        批量获取缓存

        Args:
            keys: 缓存键列表

        Returns:
            缓存值列表
        """
        try:
            redis = await self.get_async_redis()
            values = await redis.mget(keys)

            # 反序列化所有值
            result = []
            for value in values:
                if value is None:
                    result.append(None)
                else:
                    try:
                        result.append(json.loads(value))
                    except json.JSONDecodeError:
                        result.append(value)

            return result

        except Exception as e:
            logger.error(f"批量缓存获取失败: {str(e)}")
            return [None] * len(keys)

    # 列表操作
    async def lpush(self, key: str, *values: Any) -> int:
        """
        左推入列表

        Args:
            key: 列表键
            *values: 要推入的值

        Returns:
            列表长度
        """
        try:
            redis = await self.get_async_redis()
            serialized_values = [json.dumps(v, ensure_ascii=False) for v in values]
            return await redis.lpush(key, *serialized_values)

        except Exception as e:
            logger.error(f"列表左推失败 {key}: {str(e)}")
            return 0

    async def rpop(self, key: str) -> Any:
        """
        右弹出列表

        Args:
            key: 列表键

        Returns:
            弹出的值
        """
        try:
            redis = await self.get_async_redis()
            value = await redis.rpop(key)
            if value:
                return json.loads(value)
            return None

        except Exception as e:
            logger.error(f"列表右弹失败 {key}: {str(e)}")
            return None

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """
        获取列表范围

        Args:
            key: 列表键
            start: 起始索引
            end: 结束索引

        Returns:
            列表值
        """
        try:
            redis = await self.get_async_redis()
            values = await redis.lrange(key, start, end)
            return [json.loads(v) for v in values]

        except Exception as e:
            logger.error(f"获取列表范围失败 {key}: {str(e)}")
            return []

    # 哈希操作
    async def hset(self, key: str, field: str, value: Any) -> bool:
        """
        设置哈希字段

        Args:
            key: 哈希键
            field: 字段名
            value: 字段值

        Returns:
            是否成功
        """
        try:
            redis = await self.get_async_redis()
            serialized_value = json.dumps(value, ensure_ascii=False)
            result = await redis.hset(key, field, serialized_value)
            return True

        except Exception as e:
            logger.error(f"哈希字段设置失败 {key}.{field}: {str(e)}")
            return False

    async def hget(self, key: str, field: str, default: Any = None) -> Any:
        """
        获取哈希字段

        Args:
            key: 哈希键
            field: 字段名
            default: 默认值

        Returns:
            字段值
        """
        try:
            redis = await self.get_async_redis()
            value = await redis.hget(key, field)
            if value is None:
                return default
            return json.loads(value)

        except Exception as e:
            logger.error(f"哈希字段获取失败 {key}.{field}: {str(e)}")
            return default

    async def hgetall(self, key: str) -> dict:
        """
        获取所有哈希字段

        Args:
            key: 哈希键

        Returns:
            所有字段值
        """
        try:
            redis = await self.get_async_redis()
            hash_data = await redis.hgetall(key)
            result = {}
            for field, value in hash_data.items():
                try:
                    result[field] = json.loads(value)
                except json.JSONDecodeError:
                    result[field] = value
            return result

        except Exception as e:
            logger.error(f"获取所有哈希字段失败 {key}: {str(e)}")
            return {}

    # 缓存统计
    async def get_info(self) -> dict:
        """
        获取Redis信息

        Returns:
            Redis信息字典
        """
        try:
            redis = await self.get_async_redis()
            info = await redis.info()
            return {
                "used_memory": info.get("used_memory_human", "0B"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }

        except Exception as e:
            logger.error(f"获取Redis信息失败: {str(e)}")
            return {}

    # 清理操作
    async def clear_pattern(self, pattern: str) -> int:
        """
        清理匹配模式的键

        Args:
            pattern: 匹配模式

        Returns:
            删除的键数量
        """
        try:
            redis = await self.get_async_redis()
            keys = await redis.keys(pattern)
            if keys:
                count = await redis.delete(*keys)
                logger.info(f"清理缓存键: {pattern}, 删除 {count} 个键")
                return count
            return 0

        except Exception as e:
            logger.error(f"清理缓存键失败 {pattern}: {str(e)}")
            return 0

    async def close(self):
        """关闭Redis连接"""
        if self._async_redis:
            await self._async_redis.close()
        if self._sync_redis:
            self._sync_redis.close()


# 创建全局缓存管理器实例
_cache_manager = None


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例（单例模式）"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager