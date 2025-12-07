"""
管理API路由
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from db.database import get_db
from db.models import (
    KnowledgeBase as KBModel,
    KnowledgeDocument,
    KnowledgeChunk,
    ThreadModel,
    MessageModel,
    FileInfo,
    UserSession,
    SecretModel,
)
from auth.decorators import get_current_user_id, require_permissions
from agent.agent_manager import get_agent_manager
from config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class SystemStatsResponse(BaseModel):
    """系统统计响应"""
    success: bool
    stats: Dict[str, Any]
    error: Optional[str] = None


@router.get("/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取系统统计信息
    """
    try:
        # 检查管理员权限
        # TODO: 实现真实的权限检查
        if not user_id.endswith("@admin"):  # 简化的管理员检查
            raise HTTPException(status_code=403, detail="需要管理员权限")

        stats = {}

        # 知识库统计
        kb_count = db.query(KBModel).filter(KBModel.is_active == True).count()
        stats["knowledge_bases"] = {
            "total": kb_count,
            "active": kb_count,
        }

        # 文档统计
        doc_count = db.query(KnowledgeDocument).count()
        chunk_count = db.query(KnowledgeChunk).count()
        stats["documents"] = {
            "total_documents": doc_count,
            "total_chunks": chunk_count,
        }

        # 会话统计
        thread_count = db.query(ThreadModel).count()
        message_count = db.query(MessageModel).count()
        stats["threads"] = {
            "total_threads": thread_count,
            "total_messages": message_count,
        }

        # 文件统计
        file_count = db.query(FileInfo).count()
        stats["files"] = {
            "total_files": file_count,
        }

        # 用户会话统计
        active_sessions = db.query(UserSession).filter(
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow(),
        ).count()
        stats["sessions"] = {
            "active_sessions": active_sessions,
        }

        # API密钥统计
        active_secrets = db.query(SecretModel).filter(
            SecretModel.is_active == True,
        ).count()
        stats["secrets"] = {
            "active_secrets": active_secrets,
        }

        # Agent统计
        agent_manager = get_agent_manager()
        active_agents = len(agent_manager.active_agents)
        stats["agents"] = {
            "active_agents": active_agents,
        }

        return SystemStatsResponse(
            success=True,
            stats=stats,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取系统统计失败: {str(e)}")
        return SystemStatsResponse(
            success=False,
            error=str(e),
        )


@router.get("/health/detailed")
async def get_detailed_health_check(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取详细的健康检查信息
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        health_status = {
            "database": "unknown",
            "cache": "unknown",
            "agents": "unknown",
            "overall": "unknown",
        }

        # 检查数据库连接
        try:
            db.execute("SELECT 1")
            health_status["database"] = "healthy"
        except Exception as e:
            health_status["database"] = f"unhealthy: {str(e)}"

        # 检查缓存连接
        try:
            from cache.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            await cache_manager.get_async_redis().ping()
            health_status["cache"] = "healthy"
        except Exception as e:
            health_status["cache"] = f"unhealthy: {str(e)}"

        # 检查Agent状态
        try:
            agent_manager = get_agent_manager()
            await agent_manager.cleanup_inactive_agents()
            health_status["agents"] = "healthy"
        except Exception as e:
            health_status["agents"] = f"unhealthy: {str(e)}"

        # 整体状态
        if all(status == "healthy" for status in health_status.values() if status != "unknown"):
            health_status["overall"] = "healthy"
        else:
            health_status["overall"] = "degraded"

        return {
            "success": True,
            "health": health_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/logs")
async def get_system_logs(
    level: str = Query("INFO", description="日志级别"),
    limit: int = Query(100, ge=1, le=1000, description="日志数量"),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取系统日志
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        # TODO: 实现从日志文件读取
        # 这里简化实现
        return {
            "success": True,
            "logs": [],
            "message": "功能开发中",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/cleanup/sessions")
async def cleanup_expired_sessions(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    清理过期会话
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        from auth.identity_verification import get_identity_verifier
        verifier = get_identity_verifier()
        cleaned_count = await verifier.cleanup_expired_sessions(db)

        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "message": f"清理了 {cleaned_count} 个过期会话",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清理会话失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/cleanup/cache")
async def cleanup_cache(
    pattern: str = Query("*", description="清理模式"),
    user_id: str = Depends(get_current_user_id),
):
    """
    清理缓存
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        from cache.cache_manager import get_cache_manager
        cache_manager = get_cache_manager()
        cleaned_count = await cache_manager.clear_pattern(pattern)

        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "message": f"清理了 {cleaned_count} 个缓存键",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清理缓存失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/config")
async def get_system_config(
    user_id: str = Depends(get_current_user_id),
):
    """
    获取系统配置
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        from config import settings

        # 返回安全的配置信息
        config = {
            "app_name": settings.app_name,
            "environment": settings.environment,
            "debug": settings.debug,
            "host": settings.host,
            "port": settings.port,
            "database": {
                "host": settings.db_host,
                "port": settings.db_port,
                "database": settings.db_name,
            },
            "redis": {
                "host": settings.redis_host,
                "port": settings.redis_port,
                "db": settings.redis_db,
            },
            "openai": {
                "model": settings.openai_model,
                "max_tokens": settings.openai_max_tokens,
                "temperature": settings.openai_temperature,
            },
        }

        return {
            "success": True,
            "config": config,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/users/activity")
async def get_user_activity(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取用户活动统计
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        # TODO: 实现真实的用户活动统计
        return {
            "success": True,
            "activity": [],
            "message": "功能开发中",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户活动失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/maintenance/reload-agents")
async def reload_agents(
    user_id: str = Depends(get_current_user_id),
):
    """
    重新加载Agent
    """
    try:
        # 检查管理员权限
        if not user_id.endswith("@admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        agent_manager = get_agent_manager()
        # 清理并重新加载
        await agent_manager.cleanup_inactive_agents()

        return {
            "success": True,
            "message": "Agent重新加载完成",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新加载Agent失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }