"""
API性能优化模块
提供响应压缩、异步处理、连接池等性能优化功能
"""

import gzip
import json
import logging
import time
from typing import Callable, Dict, Any, Optional, List
from functools import wraps
from io import BytesIO
import asyncio
from fastapi import Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as aioredis

from config.config import settings
from cache import cache_manager

logger = logging.getLogger(__name__)

class ResponseCompressionMiddleware(BaseHTTPMiddleware):
    """响应压缩中间件"""

    def __init__(self, app, minimum_size: int = 1024):
        super().__init__(app)
        self.minimum_size = minimum_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 检查是否需要压缩
        if (
            response.headers.get("Content-Encoding") == "gzip" or
            len(response.body or b"") < self.minimum_size or
            "gzip" not in request.headers.get("Accept-Encoding", "")
        ):
            return response

        # 压缩响应
        compressed = gzip.compress(response.body)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(compressed))
        response.body = compressed

        return response

class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """性能监控中间件"""

    def __init__(self, app):
        super().__init__(app)
        self.request_times: Dict[str, List[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # 记录请求开始
        method = request.method
        path = request.url.path
        key = f"{method}:{path}"

        try:
            response = await call_next(request)

            # 记录响应时间
            duration = time.time() - start_time

            # 存储性能数据
            if key not in self.request_times:
                self.request_times[key] = []
            self.request_times[key].append(duration)

            # 只保留最近100个请求的数据
            if len(self.request_times[key]) > 100:
                self.request_times[key] = self.request_times[key][-100:]

            # 添加性能头
            response.headers["X-Response-Time"] = f"{duration:.3f}s"

            # 记录慢请求
            if duration > 1.0:
                logger.warning(f"Slow request: {key} took {duration:.3f}s")
                response.headers["X-Slow-Request"] = "true"

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Request failed after {duration:.3f}s: {str(e)}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        stats = {}
        for key, times in self.request_times.items():
            if times:
                stats[key] = {
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "count": len(times),
                    "p95": sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else None
                }
        return stats

class AsyncTaskQueue:
    """异步任务队列"""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.queue = asyncio.Queue()
        self.workers = []
        self.running = False

    async def start(self):
        """启动工作线程"""
        if self.running:
            return

        self.running = True
        self.workers = [
            asyncio.create_task(self._worker(f"worker-{i}"))
            for i in range(self.max_workers)
        ]
        logger.info(f"Started {self.max_workers} async workers")

    async def stop(self):
        """停止工作线程"""
        self.running = False

        # 等待所有任务完成
        await self.queue.join()

        # 取消工作线程
        for worker in self.workers:
            worker.cancel()

        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("Stopped all async workers")

    async def _worker(self, name: str):
        """工作线程"""
        while self.running:
            try:
                task = await self.queue.get()
                await task()
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {name} error: {str(e)}")

    async def add_task(self, coro):
        """添加任务到队列"""
        await self.queue.put(coro)

    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self.queue.qsize()

# 全局任务队列
task_queue = AsyncTaskQueue()

def async_task(func: Callable):
    """异步任务装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 创建异步任务
        coro = func(*args, **kwargs)
        await task_queue.add_task(coro)
        return {"message": "Task queued", "queue_size": task_queue.get_queue_size()}
    return wrapper

class ConnectionPoolManager:
    """连接池管理器"""

    def __init__(self):
        self.pools: Dict[str, Any] = {}

    async def get_redis_pool(self) -> aioredis.Redis:
        """获取Redis连接池"""
        if "redis" not in self.pools:
            self.pools["redis"] = aioredis.from_url(
                settings.REDIS_URL,
                max_connections=20,
                retry_on_timeout=True
            )
        return self.pools["redis"]

    async def close_all(self):
        """关闭所有连接池"""
        for pool in self.pools.values():
            if hasattr(pool, "close"):
                await pool.close()
        self.pools.clear()

# 全局连接池管理器
pool_manager = ConnectionPoolManager()

class BulkOperationOptimizer:
    """批量操作优化器"""

    def __init__(self, batch_size: int = 100, flush_interval: float = 5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.pending_operations: List[Dict] = []
        self.last_flush = time.time()
        self._flush_task = None

    async def add_operation(self, operation_type: str, data: Dict):
        """添加操作到批次"""
        self.pending_operations.append({
            "type": operation_type,
            "data": data,
            "timestamp": time.time()
        })

        # 检查是否需要刷新
        if (
            len(self.pending_operations) >= self.batch_size or
            time.time() - self.last_flush > self.flush_interval
        ):
            await self.flush()

    async def flush(self):
        """刷新所有待处理的操作"""
        if not self.pending_operations:
            return

        try:
            # 按类型分组
            grouped = {}
            for op in self.pending_operations:
                op_type = op["type"]
                if op_type not in grouped:
                    grouped[op_type] = []
                grouped[op_type].append(op["data"])

            # 批量执行
            for op_type, items in grouped.items():
                await self._execute_batch(op_type, items)

            self.pending_operations.clear()
            self.last_flush = time.time()

        except Exception as e:
            logger.error(f"Bulk operation failed: {str(e)}")

    async def _execute_batch(self, operation_type: str, items: List[Dict]):
        """执行批量操作"""
        if operation_type == "cache_set":
            # 批量设置缓存
            pipe = await pool_manager.get_redis_pool().pipeline()
            for item in items:
                await pipe.setex(
                    item["key"],
                    item.get("ttl", 300),
                    item["value"]
                )
            await pipe.execute()

        elif operation_type == "cache_delete":
            # 批量删除缓存
            keys = [item["key"] for item in items]
            await pool_manager.get_redis_pool().delete(*keys)

        # 可以添加更多批量操作类型

# 全局批量操作优化器
bulk_optimizer = BulkOperationOptimizer()

# 缓存装饰器优化版本
def smart_cache(ttl: int = 300, key_func: Optional[Callable] = None):
    """智能缓存装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"

            # 尝试从缓存获取
            cached_result = await cache_manager.get(cache_key, "api")
            if cached_result is not None:
                return cached_result

            # 执行函数
            result = await func(*args, **kwargs)

            # 异步设置缓存
            await bulk_optimizer.add_operation("cache_set", {
                "key": cache_key,
                "value": result,
                "ttl": ttl
            })

            return result
        return wrapper
    return decorator

class APIRateLimiter:
    """API限流器"""

    def __init__(self):
        self.redis = None

    async def init(self):
        """初始化Redis连接"""
        self.redis = await pool_manager.get_redis_pool()

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window: int = 60
    ) -> tuple[bool, Dict[str, Any]]:
        """
        检查是否允许请求

        Args:
            key: 限流键（通常是IP或用户ID）
            limit: 限制次数
            window: 时间窗口（秒）

        Returns:
            (是否允许, 限流信息)
        """
        if not self.redis:
            await self.init()

        now = int(time.time())
        window_start = now - window
        redis_key = f"rate_limit:{key}"

        # 使用滑动窗口算法
        async with self.redis.pipeline() as pipe:
            # 移除过期的请求记录
            await pipe.zremrangebyscore(redis_key, 0, window_start)

            # 获取当前窗口内的请求数
            await pipe.zcard(redis_key)

            # 添加当前请求
            await pipe.zadd(redis_key, {str(now): now})

            # 设置键过期时间
            await pipe.expire(redis_key, window)

            results = await pipe.execute()

        current_requests = results[1]
        allowed = current_requests <= limit

        return allowed, {
            "limit": limit,
            "remaining": max(0, limit - current_requests),
            "reset_time": now + window,
            "current_requests": current_requests
        }

# 全局限流器
rate_limiter = APIRateLimiter()

def rate_limit(limit: int, window: int = 60):
    """限流装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # 获取客户端IP
            client_ip = request.client.host

            # 检查是否限流
            allowed, info = await rate_limiter.is_allowed(client_ip, limit, window)

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        "X-RateLimit-Limit": str(info["limit"]),
                        "X-RateLimit-Remaining": str(info["remaining"]),
                        "X-RateLimit-Reset": str(info["reset_time"])
                    }
                )

            # 添加响应头
            response = await func(request, *args, **kwargs)
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset_time"])

            return response
        return wrapper
    return decorator

# 性能指标收集
class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "requests_total": 0,
            "requests_slow": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "response_times": [],
            "error_count": 0
        }

    def record_request(self, duration: float, is_slow: bool = False):
        """记录请求"""
        self.metrics["requests_total"] += 1
        if is_slow:
            self.metrics["requests_slow"] += 1

        # 只保留最近1000个响应时间
        self.metrics["response_times"].append(duration)
        if len(self.metrics["response_times"]) > 1000:
            self.metrics["response_times"] = self.metrics["response_times"][-1000:]

    def record_cache_hit(self):
        """记录缓存命中"""
        self.metrics["cache_hits"] += 1

    def record_cache_miss(self):
        """记录缓存未命中"""
        self.metrics["cache_misses"] += 1

    def record_error(self):
        """记录错误"""
        self.metrics["error_count"] += 1

    def get_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        total_requests = self.metrics["requests_total"]
        total_cache = self.metrics["cache_hits"] + self.metrics["cache_misses"]

        avg_response_time = (
            sum(self.metrics["response_times"]) / len(self.metrics["response_times"])
            if self.metrics["response_times"] else 0
        )

        return {
            "requests_total": total_requests,
            "requests_slow": self.metrics["requests_slow"],
            "slow_request_rate": (
                self.metrics["requests_slow"] / total_requests
                if total_requests > 0 else 0
            ),
            "cache_hit_rate": (
                self.metrics["cache_hits"] / total_cache
                if total_cache > 0 else 0
            ),
            "avg_response_time": avg_response_time,
            "error_count": self.metrics["error_count"],
            "error_rate": (
                self.metrics["error_count"] / total_requests
                if total_requests > 0 else 0
            )
        }

# 全局性能指标收集器
perf_metrics = PerformanceMetrics()