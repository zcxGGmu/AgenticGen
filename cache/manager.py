"""
缓存管理工具
提供缓存管理、监控和优化功能
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from cache.multi_level_cache import cache_manager, cached
from db.connection import get_db_session
from db.models import User, APIKey, KnowledgeBase, FileInfo

logger = logging.getLogger(__name__)

@dataclass
class CacheMetrics:
    """缓存指标"""
    l1_hit_rate: float
    l2_hit_rate: float
    total_hit_rate: float
    l1_memory_mb: float
    l2_memory_mb: float
    l1_size: int
    l2_connected_clients: int

class AdvancedCacheManager:
    """高级缓存管理器"""

    def __init__(self):
        self.preload_tasks = []

    async def get_metrics(self) -> CacheMetrics:
        """获取缓存性能指标"""
        stats = await cache_manager.get_all_stats()

        return CacheMetrics(
            l1_hit_rate=stats['l1_memory_cache']['hit_rate'],
            l2_hit_rate=stats['l2_redis_cache'].get('hit_rate', 0),
            total_hit_rate=stats['total_hit_rate'],
            l1_memory_mb=stats['l1_memory_cache']['memory_mb'],
            l2_memory_mb=stats['l2_redis_cache'].get('memory_mb', 0),
            l1_size=stats['l1_memory_cache']['size'],
            l2_connected_clients=stats['l2_redis_cache'].get('connected_clients', 0)
        )

    async def preload_user_data(self, user_id: int):
        """预加载用户数据到缓存"""
        try:
            with get_db_session() as session:
                # 加载用户信息
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    await cache_manager.set(
                        f"user:{user_id}",
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "full_name": user.full_name,
                            "is_active": user.is_active
                        },
                        ttl=600,  # 10分钟
                        namespace="user"
                    )

                # 加载用户的API密钥
                api_keys = session.query(APIKey).filter(
                    APIKey.user_id == user_id,
                    APIKey.is_active == True
                ).all()

                if api_keys:
                    key_data = [{
                        "id": key.id,
                        "key_name": key.key_name,
                        "prefix": key.prefix,
                        "permissions": key.permissions
                    } for key in api_keys]

                    await cache_manager.set(
                        f"user_keys:{user_id}",
                        key_data,
                        ttl=600,
                        namespace="auth"
                    )

                # 加载用户的知识库列表
                kbs = session.query(KnowledgeBase).filter(
                    KnowledgeBase.user_id == user_id,
                    KnowledgeBase.is_active == True
                ).all()

                if kbs:
                    kb_data = [{
                        "id": kb.id,
                        "name": kb.name,
                        "description": kb.description,
                        "total_documents": kb.total_documents
                    } for kb in kbs]

                    await cache_manager.set(
                        f"user_kbs:{user_id}",
                        kb_data,
                        ttl=300,  # 5分钟
                        namespace="knowledge"
                    )

                logger.info(f"Preloaded data for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to preload user data: {str(e)}")

    async def preload_hot_data(self):
        """预加载热点数据"""
        try:
            with get_db_session() as session:
                # 加载活跃用户列表
                active_users = session.query(User).filter(
                    User.is_active == True
                ).limit(100).all()

                for user in active_users:
                    await self.preload_user_data(user.id)

                # 加载系统统计
                stats = {
                    "total_users": session.query(User).count(),
                    "active_users": session.query(User).filter(User.is_active == True).count(),
                    "total_kbs": session.query(KnowledgeBase).count(),
                    "total_files": session.query(FileInfo).count()
                }

                await cache_manager.set(
                    "system:stats",
                    stats,
                    ttl=60,  # 1分钟
                    namespace="system"
                )

                logger.info("Hot data preload completed")

        except Exception as e:
            logger.error(f"Failed to preload hot data: {str(e)}")

    async def invalidate_user_cache(self, user_id: int):
        """清除用户相关缓存"""
        namespaces = ["user", "auth", "knowledge"]
        for ns in namespaces:
            await cache_manager.clear_namespace(f"{ns}:{user_id}")

        logger.info(f"Invalidated cache for user {user_id}")

    async def invalidate_kb_cache(self, kb_id: int):
        """清除知识库相关缓存"""
        # 清除知识库详情缓存
        await cache_manager.delete(f"kb:{kb_id}", namespace="knowledge")

        # 清除知识库列表缓存
        await cache_manager.clear_namespace("knowledge:list")

        logger.info(f"Invalidated cache for KB {kb_id}")

    async def get_cache_health(self) -> Dict[str, Any]:
        """获取缓存健康状态"""
        metrics = await self.get_metrics()

        health = {
            "status": "healthy",
            "metrics": {
                "l1_hit_rate": f"{metrics.l1_hit_rate:.2%}",
                "l2_hit_rate": f"{metrics.l2_hit_rate:.2%}",
                "total_hit_rate": f"{metrics.total_hit_rate:.2%}",
                "l1_memory_mb": f"{metrics.l1_memory_mb:.1f}",
                "l2_memory_mb": f"{metrics.l2_memory_mb:.1f}"
            },
            "warnings": [],
            "recommendations": []
        }

        # 检查潜在问题
        if metrics.total_hit_rate < 0.5:
            health["warnings"].append("Low cache hit rate (< 50%)")
            health["recommendations"].append("Consider increasing cache TTL or preloading more data")

        if metrics.l1_memory_mb > 80:  # 超过80MB
            health["warnings"].append("L1 cache memory usage high")
            health["recommendations"].append("Consider reducing L1 cache size or TTL")

        if metrics.l2_connected_clients > 100:
            health["warnings"].append("High Redis connection count")
            health["recommendations"].append("Check for connection leaks")

        # 确定整体状态
        if health["warnings"]:
            health["status"] = "warning"

        return health

    async def export_cache_stats(self) -> Dict[str, Any]:
        """导出缓存统计信息用于监控"""
        metrics = await self.get_metrics()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cache_performance": {
                "l1_hit_rate": metrics.l1_hit_rate,
                "l2_hit_rate": metrics.l2_hit_rate,
                "total_hit_rate": metrics.total_hit_rate
            },
            "memory_usage": {
                "l1_mb": metrics.l1_memory_mb,
                "l2_mb": metrics.l2_memory_mb,
                "total_mb": metrics.l1_memory_mb + metrics.l2_memory_mb
            },
            "cache_size": {
                "l1_entries": metrics.l1_size,
                "l2_clients": metrics.l2_connected_clients
            }
        }

    async def cleanup_expired_cache(self):
        """清理过期缓存"""
        try:
            # L1缓存清理由后台任务自动执行
            # 这里可以添加L2缓存的额外清理逻辑

            # 清理临时数据
            await cache_manager.clear_namespace("temp")

            # 记录清理统计
            metrics = await self.get_metrics()
            logger.info(f"Cache cleanup completed. L1 size: {metrics.l1_size}")

        except Exception as e:
            logger.error(f"Cache cleanup failed: {str(e)}")

    async def warm_up_on_startup(self):
        """启动时预热缓存"""
        logger.info("Starting cache warm-up...")

        # 预加载热点数据
        await self.preload_hot_data()

        # 预加载系统配置
        from cache.multi_level_cache import warm_up_cache
        await warm_up_cache()

        logger.info("Cache warm-up completed")

# 创建全局缓存管理器实例
advanced_cache_manager = AdvancedCacheManager()

# 定时任务
async def schedule_cache_tasks():
    """调度定时缓存任务"""
    while True:
        try:
            # 每小时执行一次
            await asyncio.sleep(3600)

            # 清理过期缓存
            await advanced_cache_manager.cleanup_expired_cache()

            # 重新加载热点数据
            await advanced_cache_manager.preload_hot_data()

        except Exception as e:
            logger.error(f"Scheduled cache task failed: {str(e)}")

# 缓存工具函数
async def cache_user_session(user_id: int, session_data: Dict):
    """缓存用户会话"""
    await cache_manager.set(
        f"session:{user_id}",
        session_data,
        ttl=1800,  # 30分钟
        namespace="session"
    )

async def get_cached_user_session(user_id: int) -> Optional[Dict]:
    """获取缓存的用户会话"""
    return await cache_manager.get(f"session:{user_id}", namespace="session")

async def cache_api_key(api_key: str, key_data: Dict):
    """缓存API密钥"""
    await cache_manager.set(
        f"apikey:{api_key}",
        key_data,
        ttl=600,  # 10分钟
        namespace="auth"
    )

async def invalidate_api_key_cache(api_key: str):
    """使API密钥缓存失效"""
    await cache_manager.delete(f"apikey:{api_key}", namespace="auth")

async def cache_query_result(query_hash: str, result: Any, ttl: int = 300):
    """缓存查询结果"""
    await cache_manager.set(
        query_hash,
        result,
        ttl=ttl,
        namespace="query"
    )

async def get_cached_query_result(query_hash: str) -> Optional[Any]:
    """获取缓存的查询结果"""
    return await cache_manager.get(query_hash, namespace="query")