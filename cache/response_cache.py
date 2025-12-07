"""
响应缓存

管理API响应缓存，提高响应速度和减少重复计算。
"""

import hashlib
import json
from datetime import timedelta
from typing import Optional, Any, Dict, List, Callable

from cache.cache_manager import get_cache_manager
from config.logging import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """响应缓存类"""

    def __init__(self):
        self.cache_manager = get_cache_manager()
        self.default_expire = 300  # 默认5分钟过期

    def _generate_cache_key(
        self,
        prefix: str,
        params: Dict[str, Any],
        include_body: bool = False
    ) -> str:
        """
        生成缓存键

        Args:
            prefix: 键前缀
            params: 参数字典
            include_body: 是否包含请求体

        Returns:
            缓存键
        """
        # 创建参数的稳定表示
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)

        # 生成哈希
        hash_value = hashlib.md5(sorted_params.encode()).hexdigest()

        return f"{prefix}:{hash_value}"

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        获取缓存的响应

        Args:
            endpoint: API端点
            params: 请求参数
            user_id: 用户ID（用于用户级别的缓存）

        Returns:
            缓存的响应或None
        """
        try:
            # 构建缓存键
            prefix = f"response:{endpoint}"
            if user_id:
                prefix = f"user:{user_id}:{prefix}"

            cache_key = self._generate_cache_key(prefix, params or {})

            # 获取缓存
            cached_data = await self.cache_manager.get(cache_key)
            if cached_data:
                logger.debug(f"响应缓存命中: {endpoint}")
                return cached_data.get("data")

            return None

        except Exception as e:
            logger.error(f"获取响应缓存失败 {endpoint}: {str(e)}")
            return None

    async def set(
        self,
        endpoint: str,
        response: Any,
        params: Optional[Dict[str, Any]] = None,
        expire: Optional[int] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        设置响应缓存

        Args:
            endpoint: API端点
            response: 响应数据
            params: 请求参数
            expire: 过期时间（秒）
            user_id: 用户ID
            tags: 缓存标签

        Returns:
            是否成功
        """
        try:
            # 构建缓存键
            prefix = f"response:{endpoint}"
            if user_id:
                prefix = f"user:{user_id}:{prefix}"

            cache_key = self._generate_cache_key(prefix, params or {})

            # 构建缓存数据
            cache_data = {
                "data": response,
                "endpoint": endpoint,
                "params": params,
                "user_id": user_id,
                "tags": tags or [],
                "cached_at": str(datetime.utcnow())
            }

            # 设置缓存
            expire = expire or self.default_expire
            success = await self.cache_manager.set(cache_key, cache_data, expire=expire)

            # 如果有标签，添加到标签索引
            if success and tags:
                await self._add_to_tags(cache_key, tags)

            logger.debug(f"响应缓存设置: {endpoint}, 过期时间: {expire}s")
            return success

        except Exception as e:
            logger.error(f"设置响应缓存失败 {endpoint}: {str(e)}")
            return False

    async def invalidate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """
        使特定缓存失效

        Args:
            endpoint: API端点
            params: 请求参数
            user_id: 用户ID

        Returns:
            是否成功
        """
        try:
            # 构建缓存键
            prefix = f"response:{endpoint}"
            if user_id:
                prefix = f"user:{user_id}:{prefix}"

            cache_key = self._generate_cache_key(prefix, params or {})

            # 删除缓存
            success = await self.cache_manager.delete(cache_key)

            logger.debug(f"响应缓存失效: {endpoint}")
            return success

        except Exception as e:
            logger.error(f"响应缓存失效失败 {endpoint}: {str(e)}")
            return False

    async def invalidate_by_tag(self, tag: str) -> int:
        """
        通过标签使缓存失效

        Args:
            tag: 缓存标签

        Returns:
            失效的缓存数量
        """
        try:
            # 获取标签下的所有缓存键
            tag_key = f"response:tag:{tag}"
            cache_keys = await self.cache_manager.get(tag_key, [])

            if not cache_keys:
                return 0

            # 批量删除缓存
            deleted_count = 0
            for cache_key in cache_keys:
                if await self.cache_manager.delete(cache_key):
                    deleted_count += 1

            # 删除标签索引
            await self.cache_manager.delete(tag_key)

            logger.info(f"通过标签失效缓存: {tag}, 删除 {deleted_count} 个缓存")
            return deleted_count

        except Exception as e:
            logger.error(f"通过标签失效缓存失败 {tag}: {str(e)}")
            return 0

    async def invalidate_user_cache(self, user_id: str) -> int:
        """
        使用户的所有缓存失效

        Args:
            user_id: 用户ID

        Returns:
            失效的缓存数量
        """
        try:
            # 查找用户相关的所有缓存键
            pattern = f"user:{user_id}:response:*"
            deleted_count = await self.cache_manager.clear_pattern(pattern)

            logger.info(f"用户缓存失效: {user_id}, 删除 {deleted_count} 个缓存")
            return deleted_count

        except Exception as e:
            logger.error(f"用户缓存失效失败 {user_id}: {str(e)}")
            return 0

    async def _add_to_tags(self, cache_key: str, tags: List[str]) -> None:
        """
        将缓存键添加到标签索引

        Args:
            cache_key: 缓存键
            tags: 标签列表
        """
        try:
            redis = await self.cache_manager.get_async_redis()

            for tag in tags:
                tag_key = f"response:tag:{tag}"
                await redis.sadd(tag_key, cache_key)
                await redis.expire(tag_key, self.default_expire * 10)  # 标签索引更长时间

        except Exception as e:
            logger.error(f"添加缓存到标签索引失败: {str(e)}")

    # 装饰器功能
    def cache_response(
        self,
        expire: Optional[int] = None,
        key_params: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        vary_on_user: bool = True
    ):
        """
        响应缓存装饰器

        Args:
            expire: 过期时间（秒）
            key_params: 用于生成缓存键的参数名列表
            tags: 缓存标签
            vary_on_user: 是否按用户区分缓存

        Returns:
            装饰器函数
        """
        def decorator(func: Callable):
            async def wrapper(*args, **kwargs):
                # 提取请求对象和用户ID
                request = None
                user_id = None

                # 从参数中查找request对象
                for arg in args:
                    if hasattr(arg, 'url'):
                        request = arg
                        if hasattr(arg.state, 'user_id'):
                            user_id = arg.state.user_id
                        break

                # 从kwargs中查找
                if request is None:
                    request = kwargs.get('request')
                    if request and hasattr(request.state, 'user_id'):
                        user_id = request.state.user_id

                # 如果不需要按用户区分，清空user_id
                if not vary_on_user:
                    user_id = None

                # 构建端点名称
                endpoint = f"{func.__module__}.{func.__name__}"

                # 构建缓存参数
                cache_params = {}
                if key_params:
                    for param in key_params:
                        if param in kwargs:
                            cache_params[param] = kwargs[param]
                else:
                    # 使用所有参数（除了request对象）
                    cache_params = {
                        k: v for k, v in kwargs.items()
                        if k != 'request' and not callable(v)
                    }

                # 尝试获取缓存
                cached_response = await self.get(
                    endpoint=endpoint,
                    params=cache_params,
                    user_id=user_id
                )

                if cached_response is not None:
                    return cached_response

                # 执行原函数
                response = await func(*args, **kwargs)

                # 缓存响应
                await self.set(
                    endpoint=endpoint,
                    response=response,
                    params=cache_params,
                    expire=expire,
                    user_id=user_id,
                    tags=tags
                )

                return response

            return wrapper
        return decorator

    # 缓存统计
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息
        """
        try:
            redis = await self.cache_manager.get_async_redis()

            # 统计响应缓存键数量
            response_keys = await redis.keys("response:*")
            stats = {
                "total_cached_responses": len([k for k in response_keys if not k.endswith(":tag")]),
                "total_tags": len([k for k in response_keys if k.endswith(":tag")]),
                "memory_usage": await self.cache_manager.get_info().get("used_memory", "0B")
            }

            # 统计各端点的缓存数量
            endpoint_stats = {}
            for key in response_keys:
                if ":tag" not in key:
                    parts = key.split(":")
                    if len(parts) >= 3:
                        endpoint = parts[2]
                        endpoint_stats[endpoint] = endpoint_stats.get(endpoint, 0) + 1

            stats["endpoint_counts"] = endpoint_stats
            return stats

        except Exception as e:
            logger.error(f"获取缓存统计失败: {str(e)}")
            return {}

    # 缓存预热
    async def warm_up(
        self,
        endpoints: List[Dict[str, Any]],
        user_ids: Optional[List[str]] = None
    ) -> int:
        """
        缓存预热

        Args:
            endpoints: 端点配置列表，包含endpoint、params、func等
            user_ids: 用户ID列表

        Returns:
            预热的缓存数量
        """
        warmed_count = 0

        try:
            for config in endpoints:
                endpoint = config.get("endpoint")
                params = config.get("params", {})
                func = config.get("func")
                expire = config.get("expire")

                if not endpoint or not func:
                    continue

                # 如果指定了用户，为每个用户预热
                target_users = user_ids or [None]

                for user_id in target_users:
                    # 检查是否已缓存
                    cached = await self.get(endpoint, params, user_id)
                    if cached is None:
                        # 执行函数获取响应
                        try:
                            response = await func(**params)
                            await self.set(
                                endpoint=endpoint,
                                response=response,
                                params=params,
                                expire=expire,
                                user_id=user_id
                            )
                            warmed_count += 1
                        except Exception as e:
                            logger.error(f"缓存预热失败 {endpoint}: {str(e)}")

            logger.info(f"缓存预热完成: {warmed_count} 个缓存")
            return warmed_count

        except Exception as e:
            logger.error(f"缓存预热过程失败: {str(e)}")
            return warmed_count