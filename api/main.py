"""
FastAPI应用入口

创建和配置FastAPI应用。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

from config import settings
from config.logging import setup_logging, get_logger
from auth.middleware import AuthMiddleware, RateLimitMiddleware, logging_middleware
from agent.agent_manager import get_agent_manager
from api.routes import (
    chat,
    auth,
    files,
    knowledge,
    tools,
    admin,
)

# 设置日志
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("应用启动中...")

    # 初始化Agent管理器
    agent_manager = get_agent_manager()
    await agent_manager.start_cleanup_task()

    logger.info("应用启动完成")

    yield

    # 关闭时执行
    logger.info("应用关闭中...")
    await agent_manager.shutdown()
    logger.info("应用关闭完成")


# 创建FastAPI应用
app = FastAPI(
    title="AgenticGen API",
    description="智能编程助手API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_methods_list,
    allow_headers=["*"],
)

# 添加受信任主机中间件
if settings.environment == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.yourdomain.com"]
    )

# 添加日志中间件
app.middleware("http")(logging_middleware)

# 添加速率限制中间件
app.add_middleware(RateLimitMiddleware)

# 添加身份验证中间件（排除特定路径）
auth_middleware = AuthMiddleware(
    exclude_paths=[
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/static",
        "/favicon.ico",
        "/api/auth/login",
        "/api/auth/register",
    ]
)
app.middleware("http")(auth_middleware.dispatch)


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": asyncio.get_event_loop().time(),
        "version": "1.0.0",
    }


# 根路径
@app.get("/", response_class=HTMLResponse)
async def root():
    """根路径，返回简单的主页"""
    return """
    <html>
        <head>
            <title>AgenticGen API</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                h1 {
                    color: #333;
                    text-align: center;
                }
                .links {
                    text-align: center;
                    margin-top: 30px;
                }
                .links a {
                    display: inline-block;
                    margin: 0 10px;
                    padding: 10px 20px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                }
                .links a:hover {
                    background-color: #0056b3;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 AgenticGen API</h1>
                <p style="text-align: center; color: #666;">
                    智能编程助手API服务
                </p>
                <div class="links">
                    <a href="/docs">API文档</a>
                    <a href="/redoc">ReDoc</a>
                </div>
            </div>
        </body>
    </html>
    """


# 注册路由
app.include_router(
    chat.router,
    prefix="/api/chat",
    tags=["聊天"],
)

app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["认证"],
)

app.include_router(
    files.router,
    prefix="/api/files",
    tags=["文件管理"],
)

app.include_router(
    knowledge.router,
    prefix="/api/knowledge",
    tags=["知识库"],
)

app.include_router(
    tools.router,
    prefix="/api/tools",
    tags=["工具执行"],
)

app.include_router(
    admin.router,
    prefix="/api/admin",
    tags=["管理"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)

    return Response(
        content={
            "success": False,
            "error": "内部服务器错误",
            "detail": str(exc) if settings.debug else None,
        },
        status_code=500,
    )


# 启动命令
if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        workers=1,
        reload=settings.debug,
        log_level="info",
    )