"""
安全中间件
提供各种安全相关的中间件功能
"""

import time
import logging
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from security.security_utils import (
    security_validator,
    generate_csrf_token,
    verify_csrf_token
)

logger = logging.getLogger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response

class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF保护中间件"""

    def __init__(self, app, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/api/auth/login",
            "/api/auth/register",
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查是否需要CSRF保护
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # GET请求不需要CSRF保护
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)

        # 检查CSRF令牌
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            csrf_token = request.cookies.get("csrf_token")

        expected_token = request.cookies.get("csrf_token")

        if not csrf_token or not expected_token or not verify_csrf_token(csrf_token, expected_token):
            raise HTTPException(status_code=403, detail="CSRF token validation failed")

        return await call_next(request)

class InputValidationMiddleware(BaseHTTPMiddleware):
    """输入验证中间件"""

    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):  # 10MB
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查请求体大小
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_size:
            raise HTTPException(
                status_code=413,
                detail="Request entity too large"
            )

        # 验证Content-Type
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if not content_type.startswith(("application/json", "multipart/form-data", "application/x-www-form-urlencoded")):
                raise HTTPException(
                    status_code=415,
                    detail="Unsupported Media Type"
                )

        return await call_next(request)

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """增强的限流中间件"""

    def __init__(self, app):
        super().__init__(app)
        self.requests = {}  # 简单内存存储（生产环境应使用Redis）

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = self.get_client_ip(request)
        current_time = time.time()

        # 清理过期记录
        self.cleanup_expired_requests(current_time)

        # 检查请求频率
        if not self.is_allowed(client_ip, current_time):
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": "60"}
            )

        return await call_next(request)

    def get_client_ip(self, request: Request) -> str:
        """获取客户端IP"""
        # 检查代理头
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host

    def cleanup_expired_requests(self, current_time: float):
        """清理过期的请求记录"""
        window = 60  # 1分钟窗口
        for ip in list(self.requests.keys()):
            self.requests[ip] = [
                req_time for req_time in self.requests[ip]
                if current_time - req_time < window
            ]
            if not self.requests[ip]:
                del self.requests[ip]

    def is_allowed(self, client_ip: str, current_time: float) -> bool:
        """检查是否允许请求"""
        window = 60  # 1分钟
        limit = 100  # 每分钟100个请求

        if client_ip not in self.requests:
            self.requests[client_ip] = []

        # 清理旧请求
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if current_time - req_time < window
        ]

        # 检查限制
        if len(self.requests[client_ip]) >= limit:
            return False

        # 记录新请求
        self.requests[client_ip].append(current_time)
        return True

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # 记录请求
        logger.info(
            f"Request: {request.method} {request.url} - "
            f"IP: {self.get_client_ip(request)} - "
            f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}"
        )

        try:
            response = await call_next(request)

            # 记录响应
            duration = time.time() - start_time
            logger.info(
                f"Response: {response.status_code} - "
                f"Duration: {duration:.3f}s - "
                f"Size: {len(response.body) if hasattr(response, 'body') else 'N/A'} bytes"
            )

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Request failed after {duration:.3f}s: {str(e)}",
                exc_info=True
            )
            raise

    def get_client_ip(self, request: Request) -> str:
        """获取客户端IP"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host

class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """会话安全中间件"""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 设置安全的Cookie
        if "session" in response.cookies:
            response.cookies["session"]["httponly"] = True
            response.cookies["session"]["secure"] = True
            response.cookies["session"]["samesite"] = "Strict"

        return response

class SQLInjectionProtectionMiddleware(BaseHTTPMiddleware):
    """SQL注入保护中间件"""

    def __init__(self, app):
        super().__init__(app)
        self.suspicious_patterns = [
            r"(\bunion\b.*\bselect\b)",
            r"(\bselect\b.*\bfrom\b)",
            r"(\binsert\b.*\binto\b)",
            r"(\bupdate\b.*\bset\b)",
            r"(\bdelete\b.*\bfrom\b)",
            r"(\bdrop\b.*\btable\b)",
            r"(\bexec\b|\bexecute\b)",
            r"(--|#|/\*|\*/)",
            r"(\bor\b.*=.*\bor\b)",
            r"(\band\b.*=.*\band\b)",
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查查询参数
        if self.contains_sql_injection(str(request.query_params)):
            logger.warning(f"Suspicious SQL injection attempt from IP: {self.get_client_ip(request)}")
            raise HTTPException(status_code=400, detail="Invalid request parameters")

        # 检查POST数据
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if self.contains_sql_injection(body.decode('utf-8', errors='ignore')):
                    logger.warning(f"Suspicious SQL injection attempt from IP: {self.get_client_ip(request)}")
                    raise HTTPException(status_code=400, detail="Invalid request data")
            except Exception:
                pass  # 如果无法解析body，继续处理

        return await call_next(request)

    def contains_sql_injection(self, data: str) -> bool:
        """检查是否包含SQL注入"""
        import re
        data_lower = data.lower()
        for pattern in self.suspicious_patterns:
            if re.search(pattern, data_lower, re.IGNORECASE):
                return True
        return False

    def get_client_ip(self, request: Request) -> str:
        """获取客户端IP"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        return request.client.host

# 中间件工厂函数
def add_security_middleware(app):
    """添加所有安全中间件"""
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(InputValidationMiddleware)
    app.add_middleware(RateLimitingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SessionSecurityMiddleware)
    app.add_middleware(SQLInjectionProtectionMiddleware)

    # CSRF中间件需要在最后添加
    app.add_middleware(CSRFMiddleware)

    logger.info("Security middleware added to application")