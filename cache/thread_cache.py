"""
会话缓存

管理用户会话和对话线程的缓存。
"""

from datetime import timedelta
from typing import Optional, Dict, Any, List

from cache.cache_manager import get_cache_manager
from config.logging import get_logger

logger = get_logger(__name__)


class ThreadCache:
    """会话缓存类"""

    def __init__(self):
        self.cache_manager = get_cache_manager()
        self.default_expire = 3600  # 默认1小时过期

    # 会话基础操作
    async def set_thread_info(
        self,
        thread_id: str,
        info: Dict[str, Any],
        expire: Optional[int] = None
    ) -> bool:
        """
        设置会话信息

        Args:
            thread_id: 会话ID
            info: 会话信息
            expire: 过期时间（秒）

        Returns:
            是否成功
        """
        key = f"thread:{thread_id}"
        expire = expire or self.default_expire
        return await self.cache_manager.set(key, info, expire=expire)

    async def get_thread_info(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话信息

        Args:
            thread_id: 会话ID

        Returns:
            会话信息或None
        """
        key = f"thread:{thread_id}"
        return await self.cache_manager.get(key)

    async def delete_thread(self, thread_id: str) -> bool:
        """
        删除会话缓存

        Args:
            thread_id: 会话ID

        Returns:
            是否成功
        """
        # 删除会话基础信息
        await self.cache_manager.delete(f"thread:{thread_id}")

        # 删除会话相关的所有缓存
        pattern = f"thread:{thread_id}:*"
        deleted_count = await self.cache_manager.clear_pattern(pattern)

        logger.info(f"删除会话缓存: {thread_id}, 清理 {deleted_count} 个相关键")
        return True

    # 消息历史缓存
    async def add_message(
        self,
        thread_id: str,
        message: Dict[str, Any],
        max_messages: int = 100
    ) -> bool:
        """
        添加消息到缓存

        Args:
            thread_id: 会话ID
            message: 消息内容
            max_messages: 最大消息数量

        Returns:
            是否成功
        """
        try:
            key = f"thread:{thread_id}:messages"

            # 添加消息到列表头部
            await self.cache_manager.lpush(key, message)

            # 保持消息数量限制
            await self.cache_manager._async_redis.ltrim(key, 0, max_messages - 1)

            # 设置过期时间
            await self.cache_manager.expire(key, self.default_expire)

            logger.debug(f"添加消息到缓存: {thread_id}")
            return True

        except Exception as e:
            logger.error(f"添加消息到缓存失败 {thread_id}: {str(e)}")
            return False

    async def get_messages(
        self,
        thread_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取消息历史

        Args:
            thread_id: 会话ID
            limit: 消息数量限制

        Returns:
            消息列表
        """
        try:
            key = f"thread:{thread_id}:messages"
            messages = await self.cache_manager.lrange(key, 0, limit - 1)
            return messages

        except Exception as e:
            logger.error(f"获取消息历史失败 {thread_id}: {str(e)}")
            return []

    async def clear_messages(self, thread_id: str) -> bool:
        """
        清空消息历史

        Args:
            thread_id: 会话ID

        Returns:
            是否成功
        """
        key = f"thread:{thread_id}:messages"
        return await self.cache_manager.delete(key)

    # 上下文缓存
    async def set_context(
        self,
        thread_id: str,
        context: Dict[str, Any],
        expire: Optional[int] = None
    ) -> bool:
        """
        设置会话上下文

        Args:
            thread_id: 会话ID
            context: 上下文信息
            expire: 过期时间（秒）

        Returns:
            是否成功
        """
        key = f"thread:{thread_id}:context"
        expire = expire or self.default_expire
        return await self.cache_manager.set(key, context, expire=expire)

    async def get_context(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话上下文

        Args:
            thread_id: 会话ID

        Returns:
            上下文信息或None
        """
        key = f"thread:{thread_id}:context"
        return await self.cache_manager.get(key)

    async def update_context(
        self,
        thread_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        更新会话上下文

        Args:
            thread_id: 会话ID
            updates: 更新的内容

        Returns:
            是否成功
        """
        try:
            # 获取现有上下文
            context = await self.get_context(thread_id) or {}

            # 合并更新
            context.update(updates)

            # 保存更新后的上下文
            return await self.set_context(thread_id, context)

        except Exception as e:
            logger.error(f"更新会话上下文失败 {thread_id}: {str(e)}")
            return False

    # 用户会话管理
    async def get_user_threads(self, user_id: str) -> List[str]:
        """
        获取用户的所有会话

        Args:
            user_id: 用户ID

        Returns:
            会话ID列表
        """
        try:
            key = f"user:{user_id}:threads"
            thread_ids = await self.cache_manager.lrange(key, 0, -1)
            return thread_ids

        except Exception as e:
            logger.error(f"获取用户会话列表失败 {user_id}: {str(e)}")
            return []

    async def add_user_thread(self, user_id: str, thread_id: str) -> bool:
        """
        添加用户会话

        Args:
            user_id: 用户ID
            thread_id: 会话ID

        Returns:
            是否成功
        """
        try:
            key = f"user:{user_id}:threads"

            # 检查是否已存在
            threads = await self.get_user_threads(user_id)
            if thread_id in threads:
                return True

            # 添加到列表
            await self.cache_manager.lpush(key, thread_id)

            # 设置过期时间
            await self.cache_manager.expire(key, self.default_expire * 24)  # 24小时

            logger.debug(f"添加用户会话: {user_id} -> {thread_id}")
            return True

        except Exception as e:
            logger.error(f"添加用户会话失败 {user_id}: {str(e)}")
            return False

    async def remove_user_thread(self, user_id: str, thread_id: str) -> bool:
        """
        移除用户会话

        Args:
            user_id: 用户ID
            thread_id: 会话ID

        Returns:
            是否成功
        """
        try:
            key = f"user:{user_id}:threads"

            # 从列表中移除
            redis = await self.cache_manager.get_async_redis()
            await redis.lrem(key, 0, thread_id)

            logger.debug(f"移除用户会话: {user_id} -> {thread_id}")
            return True

        except Exception as e:
            logger.error(f"移除用户会话失败 {user_id}: {str(e)}")
            return False

    # 会话统计
    async def get_thread_stats(self, thread_id: str) -> Dict[str, Any]:
        """
        获取会话统计信息

        Args:
            thread_id: 会话ID

        Returns:
            统计信息
        """
        try:
            stats = {}

            # 消息数量
            key = f"thread:{thread_id}:messages"
            redis = await self.cache_manager.get_async_redis()
            stats["message_count"] = await redis.llen(key)

            # 上下文存在性
            stats["has_context"] = await self.cache_manager.exists(
                f"thread:{thread_id}:context"
            )

            # 会话信息
            thread_info = await self.get_thread_info(thread_id)
            if thread_info:
                stats.update(thread_info)

            return stats

        except Exception as e:
            logger.error(f"获取会话统计失败 {thread_id}: {str(e)}")
            return {}

    # 会话搜索
    async def search_threads(
        self,
        user_id: str,
        keyword: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索用户的会话

        Args:
            user_id: 用户ID
            keyword: 搜索关键词
            limit: 结果数量限制

        Returns:
            匹配的会话列表
        """
        try:
            # 获取用户所有会话
            thread_ids = await self.get_user_threads(user_id)
            results = []

            for thread_id in thread_ids:
                # 获取会话信息
                thread_info = await self.get_thread_info(thread_id)
                if thread_info:
                    # 检查标题或描述是否包含关键词
                    title = thread_info.get("title", "").lower()
                    description = thread_info.get("description", "").lower()

                    if keyword.lower() in title or keyword.lower() in description:
                        results.append({
                            "thread_id": thread_id,
                            **thread_info
                        })

                        if len(results) >= limit:
                            break

            return results

        except Exception as e:
            logger.error(f"搜索会话失败 {user_id}: {str(e)}")
            return []

    # 批量操作
    async def batch_delete_threads(self, thread_ids: List[str]) -> int:
        """
        批量删除会话缓存

        Args:
            thread_ids: 会话ID列表

        Returns:
            删除成功的数量
        """
        success_count = 0
        for thread_id in thread_ids:
            if await self.delete_thread(thread_id):
                success_count += 1

        logger.info(f"批量删除会话缓存: {success_count}/{len(thread_ids)}")
        return success_count