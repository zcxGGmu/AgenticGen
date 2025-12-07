"""
验证装饰器

提供身份验证和速率限制的装饰器。
"""

import functools
from typing import Callable, Optional

from fastapi import Request, HTTPException, status, Depends
from starlette.requests import Request

from auth.identity_verification import get_identity_verifier
from config.logging import get_logger

logger = get_logger(__name__)


def require_auth(request: Request):
    """
    身份验证依赖项

    Args:
        request: 请求对象

    Returns:
        用户ID

    Raises:
        HTTPException: 验证失败时抛出
    """
    # 检查是否已经通过中间件验证
    if hasattr(request.state, "user_id"):
        return request.state.user_id

    # 手动验证
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not api_key:
        api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        api_key = request.query_params.get("api_key", "")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少API密钥"
        )

    identity_verifier = get_identity_verifier()
    secret = identity_verifier.verify_secret(api_key)

    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的API密钥"
        )

    return secret.user_id


def get_current_user_id(request: Request) -> str:
    """
    获取当前用户ID

    Args:
        request: 请求对象

    Returns:
        用户ID
    """
    return require_auth(request)


def get_secret_id(request: Request) -> Optional[int]:
    """
    获取密钥ID

    Args:
        request: 请求对象

    Returns:
        密钥ID
    """
    if hasattr(request.state, "secret_id"):
        return request.state.secret_id
    return None


def rate_limit(requests: int = 100, window: int = 60):
    """
    速率限制装饰器

    Args:
        requests: 允许的请求数
        window: 时间窗口（秒）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 从kwargs中获取request对象
            request = None
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                    break

            if request is None and args:
                # 尝试从位置参数中获取
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                # 如果没有request对象，直接执行函数
                return await func(*args, **kwargs)

            # 检查速率限制
            client_id = getattr(request.state, "user_id", None) or request.client.host

            # 这里应该使用Redis等分布式存储来实现速率限制
            # 简化实现，仅作为示例
            logger.info(f"速率限制检查: {client_id}, 限制: {requests}/{window}s")

            # 执行原函数
            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_permissions(permissions: list):
    """
    权限验证装饰器

    Args:
        permissions: 需要的权限列表

    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取用户ID
            request = None
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                    break

            if request is None and args:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="无法获取请求对象"
                )

            user_id = require_auth(request)

            # TODO: 实现权限验证逻辑
            # 这里应该查询数据库或缓存来验证用户权限
            logger.info(f"权限验证: 用户 {user_id}, 需要: {permissions}")

            # 执行原函数
            return await func(*args, **kwargs)

        return wrapper
    return decorator


def validate_content_type(content_types: list):
    """
    内容类型验证装饰器

    Args:
        content_types: 允许的内容类型列表

    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取request对象
            request = None
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                    break

            if request is None and args:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is not None:
                # 验证内容类型
                content_type = request.headers.get("content-type", "").split(";")[0]
                if content_type not in content_types:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail=f"不支持的内容类型: {content_type}"
                    )

            # 执行原函数
            return await func(*args, **kwargs)

        return wrapper
    return decorator