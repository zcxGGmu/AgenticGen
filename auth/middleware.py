"""
验证中间件

提供FastAPI中间件用于身份验证和速率限制。
"""

import time
from typing import Dict, Optional
from urllib.parse import parse_qs

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from auth.identity_verification import get_identity_verifier
from auth.crypto import get_crypto_manager
from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """身份验证中间件"""

    def __init__(self, app, exclude_paths: Optional[list] = None):
        super().__init__(app)
        self.identity_verifier = get_identity_verifier()
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/static",
            "/favicon.ico",
        ]

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        path = request.url.path

        # 跳过不需要验证的路径
        if any(path.startswith(exclude_path) for exclude_path in self.exclude_paths):
            return await call_next(request)

        # 获取API密钥
        api_key = self._extract_api_key(request)

        if api_key is None:
            logger.warning(f"缺少API密钥: {path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "缺少API密钥"}
            )

        # 验证API密钥
        secret = self.identity_verifier.verify_secret(api_key)
        if secret is None:
            logger.warning(f"无效的API密钥: {path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "无效的API密钥"}
            )

        # 将用户信息添加到请求状态
        request.state.user_id = secret.user_id
        request.state.secret_id = secret.id

        # 继续处理请求
        return await call_next(request)

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """
        从请求中提取API密钥

        Args:
            request: 请求对象

        Returns:
            API密钥或None
        """
        # 优先从Authorization头获取
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        # 从查询参数获取
        api_key = request.query_params.get("api_key")
        if api_key:
            return api_key

        # 从X-API-Key头获取
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key

        # 从表单数据获取（仅POST请求）
        if request.method == "POST":
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                # 对于表单数据，需要特殊处理
                return None  # 让视图层处理

        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = {}
        self.request_limit = settings.rate_limit_requests
        self.time_window = settings.rate_limit_window

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 获取客户端标识
        client_id = self._get_client_id(request)

        # 检查速率限制
        if not self._check_rate_limit(client_id):
            logger.warning(f"速率限制触发: {client_id}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "请求过于频繁，请稍后再试"}
            )

        # 继续处理请求
        return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """
        获取客户端标识

        Args:
            request: 请求对象

        Returns:
            客户端标识
        """
        # 优先使用用户ID
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        # 使用IP地址
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host

        return f"ip:{ip}"

    def _check_rate_limit(self, client_id: str) -> bool:
        """
        检查速率限制

        Args:
            client_id: 客户端标识

        Returns:
            是否允许请求
        """
        current_time = time.time()

        # 获取或创建客户端请求记录
        if client_id not in self.rate_limiter:
            self.rate_limiter[client_id] = []

        # 清理过期的请求记录
        self.rate_limiter[client_id] = [
            req_time for req_time in self.rate_limiter[client_id]
            if current_time - req_time < self.time_window
        ]

        # 检查请求数量
        if len(self.rate_limiter[client_id]) >= self.request_limit:
            return False

        # 记录当前请求
        self.rate_limiter[client_id].append(current_time)

        return True


async def rate_limit_middleware(request: Request, call_next):
    """
    速率限制装饰器（作为中间件使用）

    Args:
        request: 请求对象
        call_next: 下一个处理函数

    Returns:
        响应对象
    """
    middleware = RateLimitMiddleware(None)
    return await middleware.dispatch(request, call_next)


# 日志中间件
async def logging_middleware(request: Request, call_next):
    """
    日志记录中间件

    Args:
        request: 请求对象
        call_next: 下一个处理函数

    Returns:
        响应对象
    """
    start_time = time.time()

    # 记录请求信息
    logger.info(
        f"请求开始: {request.method} {request.url.path} "
        f"- 客户端: {request.client.host}"
    )

    # 处理请求
    response = await call_next(request)

    # 计算处理时间
    process_time = time.time() - start_time

    # 记录响应信息
    logger.info(
        f"请求完成: {request.method} {request.url.path} "
        f"- 状态码: {response.status_code} "
        f"- 处理时间: {process_time:.3f}s"
    )

    # 添加处理时间到响应头
    response.headers["X-Process-Time"] = str(process_time)

    return response


# CORS中间件
from fastapi.middleware.cors import CORSMiddleware

def get_cors_middleware():
    """
    获取CORS中间件配置

    Returns:
        CORSMiddleware实例
    """
    return CORSMiddleware(
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_allow_headers.split(",") if settings.cors_allow_headers else ["*"],
    )