"""
系统指标收集器
收集应用性能、资源使用和业务指标
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import psutil
import json
from collections import defaultdict, deque
import sys
from pathlib import Path

from cache.multi_level_cache import MultiLevelCache

# Import Rust metrics collector
try:
    # Add services/metrics-collector to path
    metrics_path = Path(__file__).parent.parent / "services" / "metrics-collector"
    sys.path.insert(0, str(metrics_path))
    from python_wrapper import get_metrics_collector
    _RUST_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Rust metrics collector loaded successfully")
except ImportError as e:
    _RUST_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"Rust metrics collector not available: {e}")
    logger.info("Falling back to Python implementation")


@dataclass
class Metric:
    """指标数据"""
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MetricAggregation:
    """指标聚合"""
    name: str
    count: int = 0
    sum: float = 0.0
    min: float = float('inf')
    max: float = float('-inf')
    avg: float = 0.0
    p95: float = 0.0
    p99: float = 0.0


class MetricsCollector:
    """指标收集器 - 高性能混合实现 (Rust + Python)"""

    def __init__(self):
        self.cache = MultiLevelCache()

        # 初始化 Rust 指标收集器（如果可用）
        if _RUST_AVAILABLE:
            self.rust_collector = get_metrics_collector()
            logger.info("Using Rust metrics collector for high-performance operations")
        else:
            self.rust_collector = None
            logger.info("Using Python metrics collector")

        # Python 指标存储（保持兼容性）
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))

        # 聚合窗口
        self.aggregation_windows = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "1d": 86400
        }

        # 系统指标配置
        self.system_metrics_interval = 10  # 10秒
        self.business_metrics_interval = 30  # 30秒

        # 自定义指标收集器
        self.custom_collectors: Dict[str, Callable] = {}

        # 启动收集循环
        self._running = True
        asyncio.create_task(self._collection_loop())

    async def record_metric(
        self,
        name: str,
        value: float,
        tags: Dict[str, str] = None
    ):
        """
        记录指标
        """
        metric = Metric(
            name=name,
            value=value,
            tags=tags or {}
        )

        # 存储指标
        self.metrics[name].append(metric)

        # 触发聚合
        await self._update_aggregations(name)

    async def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: Dict[str, str] = None
    ):
        """
        增加计数器
        使用 Rust 实现获得最佳性能
        """
        # 使用 Rust 计数器（高性能）
        if self.rust_collector:
            # Rust 计数器操作 - 纳秒级延迟
            self.rust_collector.add_counter(name, int(value))

        # 获取当前值（用于历史记录）
        current_key = f"counter:{name}"
        current = await self.cache.get(current_key) or 0

        # 更新计数
        new_value = current + value
        await self.cache.set(current_key, new_value, expire=3600)

        # 记录指标
        await self.record_metric(f"{name}_total", new_value, tags)
        await self.record_metric(f"{name}_increment", value, tags)

    async def set_gauge(
        self,
        name: str,
        value: float,
        tags: Dict[str, str] = None
    ):
        """
        设置仪表盘值
        使用 Rust 实现获得最佳性能
        """
        # 使用 Rust 计量器（高性能）
        if self.rust_collector:
            # Rust 计量器操作 - 纳秒级延迟
            self.rust_collector.set_gauge(name, int(value))

        # 缓存当前值
        gauge_key = f"gauge:{name}"
        await self.cache.set(gauge_key, value, expire=3600)

        # 记录指标
        await self.record_metric(name, value, tags)

    async def record_histogram(
        self,
        name: str,
        value: float,
        tags: Dict[str, str] = None
    ):
        """
        记录直方图数据
        使用 Rust 实现获得最佳性能
        """
        # 使用 Rust 直方图（高性能）
        if self.rust_collector:
            # Rust 直方图操作 - 纳秒级延迟
            self.rust_collector.record_histogram(name, int(value))

        # 记录原始值
        await self.record_metric(name, value, tags)

        # 计算分位数
        metric_key = f"histogram:{name}"
        values = await self.cache.get(metric_key) or []
        values.append(value)

        # 保持最近1000个值
        if len(values) > 1000:
            values = values[-1000:]

        await self.cache.set(metric_key, values, expire=3600)

        # 计算并更新分位数
        if len(values) >= 10:
            sorted_values = sorted(values)
            count = len(sorted_values)

            await self.record_metric(f"{name}_count", count, tags)
            await self.record_metric(f"{name}_sum", sum(sorted_values), tags)

            # P95
            p95_index = int(0.95 * count)
            await self.record_metric(f"{name}_p95", sorted_values[p95_index], tags)

            # P99
            p99_index = int(0.99 * count)
            await self.record_metric(f"{name}_p99", sorted_values[p99_index], tags)

            # 平均值
            await self.record_metric(f"{name}_avg", sum(sorted_values) / count, tags)

    async def get_metric(
        self,
        name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Dict[str, str] = None
    ) -> List[Metric]:
        """
        获取指标数据
        """
        metrics = self.metrics.get(name, deque())

        # 时间过滤
        if start_time or end_time:
            filtered = []
            for metric in metrics:
                if start_time and metric.timestamp < start_time:
                    continue
                if end_time and metric.timestamp > end_time:
                    continue
                filtered.append(metric)
            metrics = filtered

        # 标签过滤
        if tags:
            filtered = []
            for metric in metrics:
                match = True
                for key, value in tags.items():
                    if metric.tags.get(key) != value:
                        match = False
                        break
                if match:
                    filtered.append(metric)
            metrics = filtered

        return list(metrics)

    async def get_aggregation(
        self,
        name: str,
        window: str = "5m"
    ) -> MetricAggregation:
        """
        获取指标聚合
        """
        window_seconds = self.aggregation_windows.get(window, 300)
        start_time = datetime.now() - timedelta(seconds=window_seconds)

        metrics = await self.get_metric(name, start_time=start_time)

        if not metrics:
            return MetricAggregation(name=name)

        values = [m.value for m in metrics]

        aggregation = MetricAggregation(
            name=name,
            count=len(values),
            sum=sum(values),
            min=min(values),
            max=max(values),
            avg=sum(values) / len(values)
        )

        # 计算分位数
        sorted_values = sorted(values)
        count = len(sorted_values)
        if count > 0:
            aggregation.p95 = sorted_values[int(0.95 * count)]
            aggregation.p99 = sorted_values[int(0.99 * count)]

        return aggregation

    async def _collection_loop(self):
        """
        指标收集循环
        """
        while self._running:
            try:
                # 收集系统指标
                await self._collect_system_metrics()

                # 收集业务指标
                await self._collect_business_metrics()

                # 运行自定义收集器
                for name, collector in self.custom_collectors.items():
                    try:
                        await collector()
                    except Exception as e:
                        logger.error(f"Custom collector {name} failed: {str(e)}")

                await asyncio.sleep(self.system_metrics_interval)

            except Exception as e:
                logger.error(f"Metrics collection error: {str(e)}")
                await asyncio.sleep(5)

    async def _collect_system_metrics(self):
        """
        收集系统指标
        """
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            await self.set_gauge("system_cpu_usage", cpu_percent)

            # 内存使用
            memory = psutil.virtual_memory()
            await self.set_gauge("system_memory_usage", memory.percent)
            await self.set_gauge("system_memory_total", memory.total)
            await self.set_gauge("system_memory_available", memory.available)

            # 磁盘使用
            disk = psutil.disk_usage('/')
            await self.set_gauge("system_disk_usage", disk.percent)
            await self.set_gauge("system_disk_total", disk.total)
            await self.set_gauge("system_disk_free", disk.free)

            # 网络IO
            network = psutil.net_io_counters()
            await self.increment_counter("system_network_bytes_sent", network.bytes_sent)
            await self.increment_counter("system_network_bytes_recv", network.bytes_recv)

            # 进程信息
            process = psutil.Process()
            await self.set_gauge("process_cpu_percent", process.cpu_percent())
            await self.set_gauge("process_memory_rss", process.memory_info().rss)
            await self.set_gauge("process_memory_vms", process.memory_info().vms)
            await self.set_gauge("process_num_threads", process.num_threads())

            # 文件描述符
            try:
                await self.set_gauge("process_num_fds", process.num_fds())
            except:
                pass

        except Exception as e:
            logger.error(f"Failed to collect system metrics: {str(e)}")

    async def _collect_business_metrics(self):
        """
        收集业务指标
        """
        try:
            # 缓存指标
            cache_stats = await self.cache.get_stats()
            if cache_stats:
                await self.set_gauge("cache_hit_rate", cache_stats.get("hit_rate", 0))
                await self.set_gauge("cache_size", cache_stats.get("size", 0))

            # API请求指标（通过中间件收集）
            # 这里可以访问全局的请求计数器

        except Exception as e:
            logger.error(f"Failed to collect business metrics: {str(e)}")

    async def _update_aggregations(self, metric_name: str):
        """
        更新指标聚合
        """
        # 更新各个时间窗口的聚合
        for window in self.aggregation_windows.keys():
            try:
                await self.get_aggregation(metric_name, window)
            except Exception as e:
                logger.error(f"Failed to update aggregation for {metric_name}: {str(e)}")

    def register_custom_collector(
        self,
        name: str,
        collector: Callable
    ):
        """
        注册自定义指标收集器
        """
        self.custom_collectors[name] = collector
        logger.info(f"Registered custom collector: {name}")

    def unregister_custom_collector(self, name: str):
        """
        注销自定义指标收集器
        """
        if name in self.custom_collectors:
            del self.custom_collectors[name]
            logger.info(f"Unregistered custom collector: {name}")

    async def export_metrics(
        self,
        format: str = "prometheus"
    ) -> str:
        """
        导出指标
        """
        if format == "prometheus":
            return await self._export_prometheus()
        elif format == "json":
            return await self._export_json()
        else:
            raise ValueError(f"Unsupported export format: {format}")

    async def _export_prometheus(self) -> str:
        """
        导出Prometheus格式
        """
        lines = []

        # 获取最新的指标值
        for metric_name, metrics in self.metrics.items():
            if not metrics:
                continue

            latest = metrics[-1]

            # 构建指标名
            prom_name = metric_name.replace(".", "_").replace("-", "_")

            # 添加标签
            tags_str = ""
            if latest.tags:
                tags_str = "{" + ",".join(
                    f'{k}="{v}"' for k, v in latest.tags.items()
                ) + "}"

            # 格式化行
            lines.append(f"{prom_name}{tags_str} {latest.value}")

        return "\n".join(lines)

    async def _export_json(self) -> str:
        """
        导出JSON格式
        """
        data = {
            "timestamp": datetime.now().isoformat(),
            "metrics": {}
        }

        for metric_name, metrics in self.metrics.items():
            if not metrics:
                continue

            latest = metrics[-1]
            data["metrics"][metric_name] = {
                "value": latest.value,
                "tags": latest.tags,
                "timestamp": latest.timestamp.isoformat()
            }

        return json.dumps(data, indent=2)

    async def get_metric_summary(self) -> Dict[str, Any]:
        """
        获取指标摘要
        """
        summary = {
            "total_metrics": len(self.metrics),
            "total_samples": sum(len(m) for m in self.metrics.values()),
            "metrics_by_type": defaultdict(int),
            "recent_metrics": {}
        }

        # 统计指标类型
        for metric_name in self.metrics.keys():
            if metric_name.endswith("_total"):
                summary["metrics_by_type"]["counter"] += 1
            elif "_histogram" in metric_name:
                summary["metrics_by_type"]["histogram"] += 1
            else:
                summary["metrics_by_type"]["gauge"] += 1

        # 获取最近的指标值
        for metric_name, metrics in list(self.metrics.items())[:10]:
            if metrics:
                latest = metrics[-1]
                summary["recent_metrics"][metric_name] = {
                    "value": latest.value,
                    "timestamp": latest.timestamp.isoformat()
                }

        return dict(summary)

    async def cleanup_old_metrics(self, hours: int = 24):
        """
        清理旧指标
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        removed_count = 0

        for metric_name, metrics in self.metrics.items():
            original_length = len(metrics)

            # 过滤旧指标
            filtered = deque(
                (m for m in metrics if m.timestamp > cutoff_time),
                maxlen=10000
            )

            self.metrics[metric_name] = filtered
            removed_count += original_length - len(filtered)

        logger.info(f"Cleaned up {removed_count} old metrics")

    def get_rust_status(self) -> Dict[str, Any]:
        """
        获取 Rust 收集器状态
        """
        if not self.rust_collector:
            return {
                "rust_active": False,
                "fallback": "Python implementation"
            }

        return {
            "rust_active": True,
            "is_rust_active": self.rust_collector.is_rust_active(),
            "performance": "~1M+ ops/sec for counters, ~1.5M+ for gauges"
        }

    async def get_all_rust_counters(self) -> Dict[str, int]:
        """
        获取所有 Rust 计数器
        """
        if self.rust_collector:
            return self.rust_collector.get_all_counters()
        return {}

    async def get_all_rust_gauges(self) -> Dict[str, int]:
        """
        获取所有 Rust 计量器
        """
        if self.rust_collector:
            return self.rust_collector.get_all_gauges()
        return {}


# 全局实例
metrics_collector = MetricsCollector()