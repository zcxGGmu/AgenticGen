"""
智能告警系统
支持规则引擎、多渠道通知和自动恢复
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart

from .metrics_collector import MetricsCollector, MetricAggregation

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """告警状态"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    ACKNOWLEDGED = "acknowledged"


class ComparisonOperator(Enum):
    """比较操作符"""
    GT = ">"  # 大于
    GTE = ">="  # 大于等于
    LT = "<"  # 小于
    LTE = "<="  # 小于等于
    EQ = "=="  # 等于
    NEQ = "!="  # 不等于


@dataclass
class AlertRule:
    """告警规则"""
    id: str
    name: str
    description: str
    metric_name: str
    operator: ComparisonOperator
    threshold: float
    severity: AlertSeverity
    duration: int = 300  # 持续时间（秒）
    tags: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Alert:
    """告警"""
    id: str
    rule_id: str
    status: AlertStatus
    severity: AlertSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    triggered_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class NotificationChannel:
    """通知渠道"""
    id: str
    name: str
    type: str  # email, slack, webhook, etc.
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    rate_limit: int = 300  # 限流时间（秒）


class AlertingEngine:
    """告警引擎"""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector

        # 告警规则
        self.rules: Dict[str, AlertRule] = {}

        # 活跃告警
        self.alerts: Dict[str, Alert] = {}

        # 通知渠道
        self.channels: Dict[str, NotificationChannel] = {}

        # 告警状态跟踪
        self.rule_states: Dict[str, Dict[str, Any]] = {}

        # 通知限流
        self.notification_history: Dict[str, datetime] = {}

        # 默认规则
        self._create_default_rules()

        # 启动评估循环
        self._running = True
        asyncio.create_task(self._evaluation_loop())

    def _create_default_rules(self):
        """
        创建默认告警规则
        """
        default_rules = [
            AlertRule(
                id="cpu_high",
                name="CPU使用率过高",
                description="CPU使用率超过80%",
                metric_name="system_cpu_usage",
                operator=ComparisonOperator.GT,
                threshold=80.0,
                severity=AlertSeverity.WARNING,
                duration=300
            ),
            AlertRule(
                id="memory_high",
                name="内存使用率过高",
                description="内存使用率超过85%",
                metric_name="system_memory_usage",
                operator=ComparisonOperator.GT,
                threshold=85.0,
                severity=AlertSeverity.WARNING,
                duration=300
            ),
            AlertRule(
                id="disk_high",
                name="磁盘使用率过高",
                description="磁盘使用率超过90%",
                metric_name="system_disk_usage",
                operator=ComparisonOperator.GT,
                threshold=90.0,
                severity=AlertSeverity.ERROR,
                duration=600
            ),
            AlertRule(
                id="error_rate_high",
                name="错误率过高",
                description="API错误率超过5%",
                metric_name="api_error_rate",
                operator=ComparisonOperator.GT,
                threshold=5.0,
                severity=AlertSeverity.ERROR,
                duration=300
            ),
            AlertRule(
                id="response_time_high",
                name="响应时间过长",
                description="API平均响应时间超过1秒",
                metric_name="api_response_time_avg",
                operator=ComparisonOperator.GT,
                threshold=1000.0,
                severity=AlertSeverity.WARNING,
                duration=300
            )
        ]

        for rule in default_rules:
            self.rules[rule.id] = rule
            self.rule_states[rule.id] = {
                "triggered": False,
                "trigger_count": 0,
                "last_evaluation": datetime.now()
            }

    async def add_rule(self, rule: AlertRule) -> str:
        """
        添加告警规则
        """
        self.rules[rule.id] = rule
        self.rule_states[rule.id] = {
            "triggered": False,
            "trigger_count": 0,
            "last_evaluation": datetime.now()
        }

        logger.info(f"Added alert rule: {rule.name}")
        return rule.id

    async def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新告警规则
        """
        rule = self.rules.get(rule_id)
        if not rule:
            return False

        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        logger.info(f"Updated alert rule: {rule.name}")
        return True

    async def delete_rule(self, rule_id: str) -> bool:
        """
        删除告警规则
        """
        if rule_id not in self.rules:
            return False

        # 取消相关告警
        await self._resolve_alerts_for_rule(rule_id)

        del self.rules[rule_id]
        del self.rule_states[rule_id]

        logger.info(f"Deleted alert rule: {rule_id}")
        return True

    async def add_notification_channel(self, channel: NotificationChannel) -> str:
        """
        添加通知渠道
        """
        self.channels[channel.id] = channel
        logger.info(f"Added notification channel: {channel.name}")
        return channel.id

    async def evaluate_rule(self, rule: AlertRule):
        """
        评估告警规则
        """
        try:
            # 获取指标数据
            aggregation = await self.metrics_collector.get_aggregation(
                rule.metric_name,
                window="5m"
            )

            if aggregation.count == 0:
                return  # 没有数据

            # 评估条件
            current_value = aggregation.avg
            triggered = self._evaluate_condition(
                current_value,
                rule.operator,
                rule.threshold
            )

            # 更新规则状态
            state = self.rule_states[rule.id]
            state["last_evaluation"] = datetime.now()

            if triggered:
                state["trigger_count"] += 1
                if not state["triggered"]:
                    # 检查持续时间
                    if state["trigger_count"] * 60 >= rule.duration:
                        state["triggered"] = True
                        await self._trigger_alert(rule, current_value)
            else:
                if state["triggered"]:
                    state["triggered"] = False
                    state["trigger_count"] = 0
                    await self._resolve_alerts_for_rule(rule.id)

        except Exception as e:
            logger.error(f"Failed to evaluate rule {rule.id}: {str(e)}")

    def _evaluate_condition(
        self,
        value: float,
        operator: ComparisonOperator,
        threshold: float
    ) -> bool:
        """
        评估条件
        """
        if operator == ComparisonOperator.GT:
            return value > threshold
        elif operator == ComparisonOperator.GTE:
            return value >= threshold
        elif operator == ComparisonOperator.LT:
            return value < threshold
        elif operator == ComparisonOperator.LTE:
            return value <= threshold
        elif operator == ComparisonOperator.EQ:
            return value == threshold
        elif operator == ComparisonOperator.NEQ:
            return value != threshold
        return False

    async def _trigger_alert(self, rule: AlertRule, current_value: float):
        """
        触发告警
        """
        # 检查是否已有活跃告警
        existing_alert = next(
            (a for a in self.alerts.values()
             if a.rule_id == rule.id and a.status == AlertStatus.ACTIVE),
            None
        )

        if existing_alert:
            return  # 告警已存在

        # 创建新告警
        alert_id = f"alert_{rule.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        alert = Alert(
            id=alert_id,
            rule_id=rule.id,
            status=AlertStatus.ACTIVE,
            severity=rule.severity,
            message=f"{rule.name}: 当前值 {current_value} {rule.operator.value} {rule.threshold}",
            details={
                "rule_name": rule.name,
                "metric_name": rule.metric_name,
                "current_value": current_value,
                "threshold": rule.threshold,
                "operator": rule.operator.value
            },
            tags=rule.tags
        )

        self.alerts[alert_id] = alert

        # 发送通知
        await self._send_notifications(alert)

        logger.warning(f"Alert triggered: {alert.message}")

    async def _resolve_alerts_for_rule(self, rule_id: str):
        """
        解决规则的所有告警
        """
        for alert in self.alerts.values():
            if alert.rule_id == rule_id and alert.status == AlertStatus.ACTIVE:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now()

                # 发送恢复通知
                await self._send_recovery_notification(alert)

                logger.info(f"Alert resolved: {alert.message}")

    async def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str
    ) -> bool:
        """
        确认告警
        """
        alert = self.alerts.get(alert_id)
        if not alert or alert.status != AlertStatus.ACTIVE:
            return False

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()
        alert.acknowledged_by = user_id

        logger.info(f"Alert acknowledged by {user_id}: {alert.message}")
        return True

    async def suppress_alert(
        self,
        alert_id: str,
        duration: int = 3600
    ) -> bool:
        """
        抑制告警
        """
        alert = self.alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.SUPPRESSED

        # 设置恢复定时器
        asyncio.create_task(self._unsuppress_alert(alert_id, duration))

        logger.info(f"Alert suppressed for {duration}s: {alert.message}")
        return True

    async def _unsuppress_alert(self, alert_id: str, delay: int):
        """
        取消抑制告警
        """
        await asyncio.sleep(delay)

        alert = self.alerts.get(alert_id)
        if alert and alert.status == AlertStatus.SUPPRESSED:
            alert.status = AlertStatus.ACTIVE

    async def _send_notifications(self, alert: Alert):
        """
        发送告警通知
        """
        for channel in self.channels.values():
            if not channel.enabled:
                continue

            # 检查限流
            if not self._check_rate_limit(channel.id):
                continue

            try:
                if channel.type == "email":
                    await self._send_email_notification(alert, channel)
                elif channel.type == "slack":
                    await self._send_slack_notification(alert, channel)
                elif channel.type == "webhook":
                    await self._send_webhook_notification(alert, channel)

            except Exception as e:
                logger.error(f"Failed to send notification via {channel.type}: {str(e)}")

    async def _send_recovery_notification(self, alert: Alert):
        """
        发送恢复通知
        """
        # 创建恢复通知
        recovery_alert = Alert(
            id=f"{alert.id}_recovery",
            rule_id=alert.rule_id,
            status=AlertStatus.RESOLVED,
            severity=AlertSeverity.INFO,
            message=f"已恢复: {alert.message}",
            details=alert.details
        )

        await self._send_notifications(recovery_alert)

    def _check_rate_limit(self, channel_id: str) -> bool:
        """
        检查通知限流
        """
        channel = self.channels.get(channel_id)
        if not channel:
            return False

        last_sent = self.notification_history.get(channel_id)
        if last_sent:
            elapsed = (datetime.now() - last_sent).total_seconds()
            if elapsed < channel.rate_limit:
                return False

        self.notification_history[channel_id] = datetime.now()
        return True

    async def _send_email_notification(
        self,
        alert: Alert,
        channel: NotificationChannel
    ):
        """
        发送邮件通知
        """
        config = channel.config
        smtp_server = config.get("smtp_server")
        smtp_port = config.get("smtp_port", 587)
        username = config.get("username")
        password = config.get("password")
        from_email = config.get("from_email")
        to_emails = config.get("to_emails", [])

        if not all([smtp_server, username, password, from_email, to_emails]):
            logger.warning("Email channel configuration incomplete")
            return

        # 创建邮件
        msg = MimeMultipart()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = f"[AgenticGen Alert] {alert.severity.value.upper()}: {alert.message}"

        # 邮件内容
        body = f"""
        告警详情:

        级别: {alert.severity.value}
        消息: {alert.message}
        触发时间: {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}

        详细信息:
        {json.dumps(alert.details, indent=2, ensure_ascii=False)}
        """

        msg.attach(MimeText(body, "plain", "utf-8"))

        # 发送邮件
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

            logger.info(f"Email notification sent for alert {alert.id}")

        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

    async def _send_slack_notification(
        self,
        alert: Alert,
        channel: NotificationChannel
    ):
        """
        发送Slack通知
        """
        # TODO: 实现Slack通知
        pass

    async def _send_webhook_notification(
        self,
        alert: Alert,
        channel: NotificationChannel
    ):
        """
        发送Webhook通知
        """
        # TODO: 实现Webhook通知
        pass

    async def _evaluation_loop(self):
        """
        告警评估循环
        """
        while self._running:
            try:
                # 评估所有规则
                for rule in self.rules.values():
                    if rule.enabled:
                        await self.evaluate_rule(rule)

                await asyncio.sleep(60)  # 每分钟评估一次

            except Exception as e:
                logger.error(f"Alert evaluation error: {str(e)}")
                await asyncio.sleep(10)

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """
        获取活跃告警
        """
        active_alerts = [
            {
                "id": alert.id,
                "rule_id": alert.rule_id,
                "severity": alert.severity.value,
                "message": alert.message,
                "triggered_at": alert.triggered_at.isoformat(),
                "status": alert.status.value
            }
            for alert in self.alerts.values()
            if alert.status in [AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]
        ]

        return active_alerts

    async def get_alert_statistics(self) -> Dict[str, Any]:
        """
        获取告警统计
        """
        stats = {
            "total_alerts": len(self.alerts),
            "active_alerts": 0,
            "resolved_alerts": 0,
            "by_severity": defaultdict(int),
            "by_status": defaultdict(int)
        }

        for alert in self.alerts.values():
            stats["by_severity"][alert.severity.value] += 1
            stats["by_status"][alert.status.value] += 1

            if alert.status in [AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]:
                stats["active_alerts"] += 1
            elif alert.status == AlertStatus.RESOLVED:
                stats["resolved_alerts"] += 1

        return dict(stats)