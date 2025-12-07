"""
数据库查询优化器
提供常用的优化查询方法
"""

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.sql import Select
from typing import TypeVar, Type, Optional, List, Dict, Any
from db.models import (
    ThreadModel, MessageModel, FileInfo, KnowledgeBase,
    APIKey, SessionCache, BaseModel
)

T = TypeVar('T', bound=BaseModel)

class QueryOptimizer:
    """数据库查询优化器"""

    @staticmethod
    def get_paginated_query(
        query: Select,
        cursor: Optional[str] = None,
        limit: int = 20,
        order_by: str = "created_at"
    ) -> Select:
        """
        实现游标分页，提高大列表查询性能

        Args:
            query: SQLAlchemy 查询对象
            cursor: 游标位置（通常是ID或时间戳）
            limit: 每页数量
            order_by: 排序字段

        Returns:
            优化后的查询对象
        """
        # 添加排序
        if hasattr(query.column_descriptions[0]['type'], order_by):
            query = query.order_by(getattr(query.column_descriptions[0]['type'], order_by))

        # 如果有游标，添加条件
        if cursor:
            # 假设使用ID作为游标
            if order_by == "id":
                query = query.where(getattr(query.column_descriptions[0]['type'], "id") > cursor)

        # 限制数量
        return query.limit(limit + 1)  # +1 用于判断是否有下一页

    @staticmethod
    def optimize_thread_query(user_id: int, include_messages: bool = False) -> Select:
        """
        优化线程查询，根据需要预加载消息

        Args:
            user_id: 用户ID
            include_messages: 是否包含消息

        Returns:
            优化后的查询
        """
        query = select(ThreadModel).where(ThreadModel.user_id == user_id)

        # 根据需要加载关联数据
        if include_messages:
            query = query.options(
                selectinload(ThreadModel.messages),
                joinedload(ThreadModel.knowledge_base)
            )
        else:
            query = query.options(
                selectinload(ThreadModel.messages).load_only(
                    MessageModel.id, MessageModel.role, MessageModel.created_at
                )
            )

        return query.order_by(ThreadModel.updated_at.desc())

    @staticmethod
    def optimize_file_query(
        user_id: int = None,
        kb_id: int = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> tuple[Select, Dict[str, Any]]:
        """
        优化文件查询，支持多种过滤条件

        Returns:
            (query, metadata) - 查询对象和元数据
        """
        # 构建基础查询
        query = select(FileInfo)
        conditions = []

        # 添加过滤条件
        if user_id:
            conditions.append(FileInfo.user_id == user_id)

        if kb_id:
            conditions.append(FileInfo.kb_id == kb_id)

        if status:
            conditions.append(FileInfo.status == status)

        if conditions:
            query = query.where(and_(*conditions))

        # 添加预加载
        query = query.options(
            joinedload(FileInfo.knowledge_base).load_only(
                KnowledgeBase.id, KnowledgeBase.name
            )
        )

        # 分页
        offset = (page - 1) * per_page
        query = query.order_by(FileInfo.upload_time.desc())

        # 获取总数
        count_query = select(func.count(FileInfo.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))

        # 返回查询和元数据
        metadata = {
            "page": page,
            "per_page": per_page,
            "offset": offset,
            "count_query": count_query
        }

        return query.offset(offset).limit(per_page), metadata

    @staticmethod
    def optimize_kb_query(
        user_id: int,
        with_stats: bool = True
    ) -> Select:
        """
        优化知识库查询，可选择包含统计信息

        Args:
            user_id: 用户ID
            with_stats: 是否包含文档统计

        Returns:
            优化后的查询
        """
        query = select(KnowledgeBase).where(KnowledgeBase.user_id == user_id)

        if with_stats:
            # 预加载统计信息
            query = query.options(
                selectinload(KnowledgeBase.files)
            )

        query = query.order_by(KnowledgeBase.updated_at.desc())

        return query

    @staticmethod
    def get_active_api_keys(user_id: int) -> Select:
        """
        获取用户的有效API密钥

        Args:
            user_id: 用户ID

        Returns:
            优化后的查询
        """
        return select(APIKey).where(
            and_(
                APIKey.user_id == user_id,
                APIKey.is_active == True,
                or_(
                    APIKey.expires_at.is_(None),
                    APIKey.expires_at > func.now()
                )
            )
        ).order_by(APIKey.created_at.desc())

    @staticmethod
    def cleanup_expired_sessions() -> Select:
        """
        获取过期会话查询，用于清理

        Returns:
            过期会话查询
        """
        return select(SessionCache).where(
            SessionCache.expires_at < func.now()
        )

    @staticmethod
    def get_message_stats(thread_id: str) -> Select:
        """
        获取消息统计信息

        Args:
            thread_id: 线程ID

        Returns:
            统计查询
        """
        return select(
            MessageModel.role,
            func.count(MessageModel.id).label('count'),
            func.avg(func.length(MessageModel.content)).label('avg_length')
        ).where(
            MessageModel.thread_id == thread_id
        ).group_by(MessageModel.role)

    @staticmethod
    def search_files(
        user_id: int,
        keyword: str,
        file_type: Optional[str] = None,
        limit: int = 50
    ) -> Select:
        """
        优化文件搜索查询

        Args:
            user_id: 用户ID
            keyword: 搜索关键词
            file_type: 文件类型过滤
            limit: 结果限制

        Returns:
            优化后的搜索查询
        """
        conditions = [
            FileInfo.user_id == user_id,
            FileInfo.status == 'completed',
            or_(
                FileInfo.filename.ilike(f"%{keyword}%"),
                FileInfo.original_filename.ilike(f"%{keyword}%")
            )
        ]

        if file_type:
            conditions.append(FileInfo.file_type == file_type)

        query = select(FileInfo).where(and_(*conditions))
        query = query.order_by(FileInfo.upload_time.desc()).limit(limit)

        return query

    @staticmethod
    def bulk_delete_expired_sessions(batch_size: int = 1000) -> List[Select]:
        """
        批量删除过期会话，避免大事务

        Args:
            batch_size: 批次大小

        Returns:
            批次删除查询列表
        """
        queries = []

        # 获取过期会话ID
        expired_ids_query = select(SessionCache.id).where(
            SessionCache.expires_at < func.now()
        ).limit(batch_size)

        # 生成删除查询
        queries.append(expired_ids_query)

        return queries

# 查询优化装饰器
def cache_query_result(ttl: int = 300):
    """
    查询结果缓存装饰器

    Args:
        ttl: 缓存生存时间（秒）
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"query:{func.__name__}:{hash(str(args) + str(kwargs))}"

            # 尝试从缓存获取
            from cache.cache import cache_manager
            cached_result = await cache_manager.get(cache_key)

            if cached_result is not None:
                return cached_result

            # 执行查询
            result = await func(*args, **kwargs)

            # 缓存结果
            await cache_manager.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator