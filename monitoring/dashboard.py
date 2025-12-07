"""
监控仪表板
提供实时监控图表和告警展示
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

from auth.middleware import get_current_user
from auth.permissions import check_user_permission, Permission
from .metrics_collector import metrics_collector
from .alerting import AlertingEngine, AlertSeverity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["监控仪表板"])

# 全局告警引擎实例
alerting_engine = None


def init_alerting():
    """初始化告警引擎"""
    global alerting_engine
    if not alerting_engine:
        alerting_engine = AlertingEngine(metrics_collector)
    return alerting_engine


@router.get("/dashboard", response_class=HTMLResponse, summary="监控仪表板")
async def monitoring_dashboard(
    current_user: dict = Depends(get_current_user)
):
    """
    监控仪表板页面
    """
    # 检查权限
    if not await check_user_permission(
        current_user["id"],
        Permission.SYSTEM_MONITOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: system monitor required"
        )

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AgenticGen - 监控仪表板</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/date-fns"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background-color: #f5f5f5;
                color: #333;
            }

            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 1rem 2rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            .header h1 {
                font-size: 1.5rem;
                font-weight: 600;
            }

            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 2rem;
            }

            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }

            .metric-card {
                background: white;
                border-radius: 8px;
                padding: 1.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                transition: transform 0.2s;
            }

            .metric-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }

            .metric-label {
                color: #666;
                font-size: 0.875rem;
                margin-bottom: 0.5rem;
            }

            .metric-value {
                font-size: 2rem;
                font-weight: bold;
                color: #333;
            }

            .metric-unit {
                font-size: 0.875rem;
                color: #999;
                margin-left: 0.25rem;
            }

            .metric-change {
                font-size: 0.875rem;
                margin-top: 0.5rem;
            }

            .metric-change.positive {
                color: #28a745;
            }

            .metric-change.negative {
                color: #dc3545;
            }

            .charts-section {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                gap: 2rem;
                margin-bottom: 2rem;
            }

            .chart-card {
                background: white;
                border-radius: 8px;
                padding: 1.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }

            .chart-card h3 {
                margin-bottom: 1rem;
                color: #333;
            }

            .chart-container {
                position: relative;
                height: 300px;
            }

            .alerts-section {
                background: white;
                border-radius: 8px;
                padding: 1.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }

            .alerts-section h3 {
                margin-bottom: 1rem;
                color: #333;
            }

            .alert-item {
                padding: 1rem;
                margin-bottom: 0.75rem;
                border-radius: 6px;
                border-left: 4px solid;
                background: #f8f9fa;
            }

            .alert-item.critical {
                border-left-color: #dc3545;
                background: #f8d7da;
            }

            .alert-item.error {
                border-left-color: #fd7e14;
                background: #fff3cd;
            }

            .alert-item.warning {
                border-left-color: #ffc107;
                background: #fff3cd;
            }

            .alert-item.info {
                border-left-color: #17a2b8;
                background: #d1ecf1;
            }

            .alert-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 0.5rem;
            }

            .alert-title {
                font-weight: 600;
                color: #333;
            }

            .alert-time {
                font-size: 0.875rem;
                color: #666;
            }

            .alert-message {
                color: #555;
            }

            .refresh-btn {
                position: fixed;
                bottom: 2rem;
                right: 2rem;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 50%;
                width: 56px;
                height: 56px;
                font-size: 1.5rem;
                cursor: pointer;
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                transition: transform 0.2s;
            }

            .refresh-btn:hover {
                transform: scale(1.1);
            }

            .loading {
                text-align: center;
                padding: 2rem;
                color: #666;
            }

            @media (max-width: 768px) {
                .container {
                    padding: 1rem;
                }

                .charts-section {
                    grid-template-columns: 1fr;
                }

                .metrics-grid {
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 AgenticGen 监控仪表板</h1>
        </div>

        <div class="container">
            <!-- 系统指标卡片 -->
            <div class="metrics-grid" id="metricsGrid">
                <div class="loading">加载指标中...</div>
            </div>

            <!-- 图表区域 -->
            <div class="charts-section">
                <div class="chart-card">
                    <h3>CPU & 内存使用率</h3>
                    <div class="chart-container">
                        <canvas id="systemChart"></canvas>
                    </div>
                </div>
                <div class="chart-card">
                    <h3>API 请求量</h3>
                    <div class="chart-container">
                        <canvas id="requestsChart"></canvas>
                    </div>
                </div>
            </div>

            <!-- 告警区域 -->
            <div class="alerts-section">
                <h3>📢 活跃告警</h3>
                <div id="alertsList">
                    <div class="loading">加载告警中...</div>
                </div>
            </div>
        </div>

        <button class="refresh-btn" onclick="refreshData()">↻</button>

        <script>
            let systemChart, requestsChart;

            // 初始化图表
            function initCharts() {
                // 系统资源图表
                const systemCtx = document.getElementById('systemChart').getContext('2d');
                systemChart = new Chart(systemCtx, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'CPU %',
                            data: [],
                            borderColor: '#007bff',
                            backgroundColor: 'rgba(0, 123, 255, 0.1)',
                            tension: 0.4
                        }, {
                            label: 'Memory %',
                            data: [],
                            borderColor: '#28a745',
                            backgroundColor: 'rgba(40, 167, 69, 0.1)',
                            tension: 0.4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });

                // 请求量图表
                const requestsCtx = document.getElementById('requestsChart').getContext('2d');
                requestsChart = new Chart(requestsCtx, {
                    type: 'bar',
                    data: {
                        labels: [],
                        datasets: [{
                            label: '请求数',
                            data: [],
                            backgroundColor: 'rgba(102, 126, 234, 0.8)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });
            }

            // 更新指标卡片
            async function updateMetrics() {
                try {
                    const response = await fetch('/api/monitoring/metrics/summary');
                    const data = await response.json();

                    const metricsHtml = `
                        <div class="metric-card">
                            <div class="metric-label">CPU 使用率</div>
                            <div class="metric-value">${data.system_cpu_usage?.toFixed(1) || 0}<span class="metric-unit">%</span></div>
                            <div class="metric-change ${data.system_cpu_usage > 80 ? 'negative' : 'positive'}">
                                ${data.system_cpu_usage > 80 ? '⚠️ 高负载' : '✅ 正常'}
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">内存使用率</div>
                            <div class="metric-value">${data.system_memory_usage?.toFixed(1) || 0}<span class="metric-unit">%</span></div>
                            <div class="metric-change ${data.system_memory_usage > 85 ? 'negative' : 'positive'}">
                                ${data.system_memory_usage > 85 ? '⚠️ 高使用率' : '✅ 正常'}
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">活跃用户</div>
                            <div class="metric-value">${data.active_users || 0}</div>
                            <div class="metric-change positive">在线</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">总请求数</div>
                            <div class="metric-value">${data.total_requests?.toLocaleString() || 0}</div>
                            <div class="metric-change positive">累计</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">平均响应时间</div>
                            <div class="metric-value">${data.avg_response_time?.toFixed(0) || 0}<span class="metric-unit">ms</span></div>
                            <div class="metric-change ${data.avg_response_time > 500 ? 'negative' : 'positive'}">
                                ${data.avg_response_time > 500 ? '⚠️ 较慢' : '✅ 良好'}
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">错误率</div>
                            <div class="metric-value">${data.error_rate?.toFixed(2) || 0}<span class="metric-unit">%</span></div>
                            <div class="metric-change ${data.error_rate > 1 ? 'negative' : 'positive'}">
                                ${data.error_rate > 1 ? '⚠️ 过高' : '✅ 正常'}
                            </div>
                        </div>
                    `;

                    document.getElementById('metricsGrid').innerHTML = metricsHtml;

                    // 更新图表
                    updateCharts(data);

                } catch (error) {
                    console.error('Failed to update metrics:', error);
                }
            }

            // 更新图表数据
            function updateCharts(data) {
                const now = new Date();
                const timeLabel = now.toLocaleTimeString();

                // 更新系统图表
                if (systemChart.data.labels.length > 20) {
                    systemChart.data.labels.shift();
                    systemChart.data.datasets[0].data.shift();
                    systemChart.data.datasets[1].data.shift();
                }

                systemChart.data.labels.push(timeLabel);
                systemChart.data.datasets[0].data.push(data.system_cpu_usage || 0);
                systemChart.data.datasets[1].data.push(data.system_memory_usage || 0);
                systemChart.update('none');

                // 更新请求图表
                if (requestsChart.data.labels.length > 10) {
                    requestsChart.data.labels.shift();
                    requestsChart.data.datasets[0].data.shift();
                }

                requestsChart.data.labels.push(timeLabel);
                requestsChart.data.datasets[0].data.push(data.requests_per_minute || 0);
                requestsChart.update('none');
            }

            // 更新告警列表
            async function updateAlerts() {
                try {
                    const response = await fetch('/api/monitoring/alerts');
                    const alerts = await response.json();

                    const alertsHtml = alerts.length > 0
                        ? alerts.map(alert => `
                            <div class="alert-item ${alert.severity}">
                                <div class="alert-header">
                                    <span class="alert-title">${alert.severity.toUpperCase()}: ${alert.message}</span>
                                    <span class="alert-time">${new Date(alert.triggered_at).toLocaleString()}</span>
                                </div>
                                <div class="alert-message">${alert.details?.rule_name || ''}</div>
                            </div>
                        `).join('')
                        : '<div style="text-align: center; color: #666; padding: 2rem;">✅ 当前无活跃告警</div>';

                    document.getElementById('alertsList').innerHTML = alertsHtml;

                } catch (error) {
                    console.error('Failed to update alerts:', error);
                }
            }

            // 刷新所有数据
            async function refreshData() {
                await Promise.all([
                    updateMetrics(),
                    updateAlerts()
                ]);
            }

            // 初始化
            document.addEventListener('DOMContentLoaded', () => {
                initCharts();
                refreshData();

                // 定期刷新
                setInterval(refreshData, 30000); // 30秒刷新一次
            });
        </script>
    </body>
    </html>
    """


@router.get("/metrics/summary", summary="获取指标摘要")
async def get_metrics_summary(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取系统指标摘要
    """
    # 检查权限
    if not await check_user_permission(
        current_user["id"],
        Permission.SYSTEM_MONITOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: system monitor required"
        )

    try:
        # 获取各种指标的最新值
        summary = {}

        # 系统指标
        system_metrics = [
            "system_cpu_usage",
            "system_memory_usage",
            "system_disk_usage"
        ]

        for metric_name in system_metrics:
            metrics = await metrics_collector.get_metric(metric_name)
            if metrics:
                summary[metric_name] = metrics[-1].value

        # API指标
        api_metrics = [
            "api_requests_total",
            "api_response_time_avg",
            "api_error_rate"
        ]

        for metric_name in api_metrics:
            metrics = await metrics_collector.get_metric(metric_name)
            if metrics:
                summary[metric_name.split('_')[-1]] = metrics[-1].value

        # 计算每分钟请求数
        requests_last_minute = await metrics_collector.get_metric(
            "api_requests_total",
            start_time=datetime.now() - timedelta(minutes=1)
        )
        summary["requests_per_minute"] = len(requests_last_minute)

        # 活跃用户数
        # TODO: 从会话管理器获取
        summary["active_users"] = 0

        return summary

    except Exception as e:
        logger.error(f"Failed to get metrics summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


@router.get("/alerts", summary="获取活跃告警")
async def get_active_alerts(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    获取活跃告警列表
    """
    # 检查权限
    if not await check_user_permission(
        current_user["id"],
        Permission.SYSTEM_MONITOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: system monitor required"
        )

    try:
        alert_engine = init_alerting()
        return await alert_engine.get_active_alerts()

    except Exception as e:
        logger.error(f"Failed to get alerts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alerts")


@router.get("/charts/data", summary="获取图表数据")
async def get_chart_data(
    metric_name: str,
    window: str = "1h",
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取图表数据
    """
    # 检查权限
    if not await check_user_permission(
        current_user["id"],
        Permission.SYSTEM_MONITOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: system monitor required"
        )

    try:
        # 计算时间窗口
        window_seconds = {
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "6h": 21600,
            "24h": 86400
        }.get(window, 3600)

        start_time = datetime.now() - timedelta(seconds=window_seconds)

        # 获取指标数据
        metrics = await metrics_collector.get_metric(
            metric_name,
            start_time=start_time
        )

        # 格式化数据
        data_points = []
        for metric in metrics:
            data_points.append({
                "timestamp": metric.timestamp.isoformat(),
                "value": metric.value
            })

        # 聚合数据点（如果太多）
        max_points = 100
        if len(data_points) > max_points:
            step = len(data_points) // max_points
            data_points = data_points[::step]

        return {
            "metric": metric_name,
            "window": window,
            "data_points": data_points
        }

    except Exception as e:
        logger.error(f"Failed to get chart data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chart data")