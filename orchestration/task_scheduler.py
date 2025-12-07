"""
智能任务调度器
实现任务的优先级调度、负载均衡和资源优化
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

from .orchestrator import Task, TaskStatus, TaskPriority, AgentOrchestrator

logger = logging.getLogger(__name__)


class SchedulingStrategy(Enum):
    """调度策略"""
    FIFO = "fifo"  # 先进先出
    PRIORITY = "priority"  # 优先级调度
    SHORTEST_JOB = "shortest_job"  # 最短作业优先
    ROUND_ROBIN = "round_robin"  # 轮转调度
    LOAD_BALANCED = "load_balanced"  # 负载均衡
    DEADLINE_FIRST = "deadline_first"  # 截止时间优先


@dataclass
class TaskDeadline:
    """任务截止时间"""
    task_id: str
    deadline: datetime
    priority_boost: float = 2.0


@dataclass
class AgentPerformance:
    """代理性能指标"""
    agent_id: str
    completed_tasks: int = 0
    total_duration: float = 0.0
    success_rate: float = 1.0
    avg_task_time: float = 0.0
    last_active: Optional[datetime] = None


class TaskScheduler:
    """智能任务调度器"""

    def __init__(self, orchestrator: AgentOrchestrator):
        self.orchestrator = orchestrator

        # 调度策略
        self.strategy = SchedulingStrategy.LOAD_BALANCED
        self.strategy_weights = {
            SchedulingStrategy.PRIORITY: 0.3,
            SchedulingStrategy.LOAD_BALANCED: 0.3,
            SchedulingStrategy.SHORTEST_JOB: 0.2,
            SchedulingStrategy.DEADLINE_FIRST: 0.2
        }

        # 代理性能跟踪
        self.agent_performance: Dict[str, AgentPerformance] = {}

        # 任务历史
        self.task_history: List[Task] = []

        # 负载预测
        self.load_prediction_window = 300  # 5分钟
        self.load_history: List[Tuple[datetime, int]] = []

        # 调度优化
        self.optimization_interval = 60  # 60秒
        self.last_optimization = datetime.now()

        # 资源限制
        self.max_concurrent_tasks = 50
        self.agent_timeout = 300  # 5分钟

        # 启动优化循环
        asyncio.create_task(self._optimization_loop())

    async def schedule_task(self, task: Task) -> Optional[str]:
        """调度任务到合适的代理"""
        try:
            # 更新负载历史
            await self._update_load_history()

            # 选择调度策略
            agent_id = await self._select_agent(task)

            if agent_id:
                # 更新代理性能
                if agent_id not in self.agent_performance:
                    self.agent_performance[agent_id] = AgentPerformance(
                        agent_id=agent_id,
                        last_active=datetime.now()
                    )

                logger.info(f"Scheduled task {task.id} to agent {agent_id}")
                return agent_id

            logger.warning(f"No available agent for task {task.id}")
            return None

        except Exception as e:
            logger.error(f"Failed to schedule task {task.id}: {str(e)}")
            return None

    async def _select_agent(self, task: Task) -> Optional[str]:
        """根据策略选择代理"""
        if self.strategy == SchedulingStrategy.FIFO:
            return await self._fifo_schedule(task)
        elif self.strategy == SchedulingStrategy.PRIORITY:
            return await self._priority_schedule(task)
        elif self.strategy == SchedulingStrategy.SHORTEST_JOB:
            return await self._shortest_job_schedule(task)
        elif self.strategy == SchedulingStrategy.ROUND_ROBIN:
            return await self._round_robin_schedule(task)
        elif self.strategy == SchedulingStrategy.LOAD_BALANCED:
            return await self._load_balanced_schedule(task)
        elif self.strategy == SchedulingStrategy.DEADLINE_FIRST:
            return await self._deadline_first_schedule(task)
        else:
            # 混合策略
            return await self._hybrid_schedule(task)

    async def _fifo_schedule(self, task: Task) -> Optional[str]:
        """先进先出调度"""
        # 选择负载最轻的代理
        return await self._get_least_loaded_agent(task)

    async def _priority_schedule(self, task: Task) -> Optional[str]:
        """优先级调度"""
        # 根据任务优先级选择最合适的代理
        candidates = await self._get_available_agents(task)

        if not candidates:
            return None

        # 高优先级任务选择性能最好的代理
        if task.priority == TaskPriority.URGENT:
            return await self._get_best_performing_agent(candidates)
        else:
            return await self._get_least_loaded_agent(task)

    async def _shortest_job_schedule(self, task: Task) -> Optional[str]:
        """最短作业优先调度"""
        # 估计任务时长
        estimated_duration = self._estimate_task_duration(task)

        # 为短任务选择快速响应的代理
        if estimated_duration < 60:  # 1分钟
            return await self._get_fastest_response_agent(task)
        else:
            return await self._get_least_loaded_agent(task)

    async def _round_robin_schedule(self, task: Task) -> Optional[str]:
        """轮转调度"""
        candidates = await self._get_available_agents(task)

        if not candidates:
            return None

        # 选择上次使用时间最早的代理
        oldest_agent = min(
            candidates,
            key=lambda aid: self.agent_performance[aid].last_active or datetime.min
        )

        return oldest_agent

    async def _load_balanced_schedule(self, task: Task) -> Optional[str]:
        """负载均衡调度"""
        return await self._get_least_loaded_agent(task)

    async def _deadline_first_schedule(self, task: Task) -> Optional[str]:
        """截止时间优先调度"""
        # 获取任务截止时间
        deadline = self._get_task_deadline(task)

        if not deadline:
            return await self._load_balanced_schedule(task)

        # 计算剩余时间
        time_remaining = (deadline - datetime.now()).total_seconds()

        if time_remaining < 300:  # 5分钟内
            # 紧急任务，选择性能最好的代理
            candidates = await self._get_available_agents(task)
            return await self._get_best_performing_agent(candidates) if candidates else None
        else:
            # 有充足时间，使用负载均衡
            return await self._get_least_loaded_agent(task)

    async def _hybrid_schedule(self, task: Task) -> Optional[str]:
        """混合调度策略"""
        # 收集各策略的推荐
        recommendations = []

        # 优先级调度
        priority_agent = await self._priority_schedule(task)
        if priority_agent:
            recommendations.append((priority_agent, self.strategy_weights[SchedulingStrategy.PRIORITY]))

        # 负载均衡调度
        load_agent = await self._load_balanced_schedule(task)
        if load_agent:
            recommendations.append((load_agent, self.strategy_weights[SchedulingStrategy.LOAD_BALANCED]))

        # 最短作业调度
        shortest_agent = await self._shortest_job_schedule(task)
        if shortest_agent:
            recommendations.append((shortest_agent, self.strategy_weights[SchedulingStrategy.SHORTEST_JOB]))

        # 截止时间调度
        deadline_agent = await self._deadline_first_schedule(task)
        if deadline_agent:
            recommendations.append((deadline_agent, self.strategy_weights[SchedulingStrategy.DEADLINE_FIRST]))

        # 加权投票
        votes = {}
        for agent_id, weight in recommendations:
            votes[agent_id] = votes.get(agent_id, 0) + weight

        if not votes:
            return None

        # 选择得票最高的代理
        best_agent = max(votes.items(), key=lambda x: x[1])[0]
        return best_agent

    async def _get_available_agents(self, task: Task) -> List[str]:
        """获取可用的代理列表"""
        available = []

        for agent_id, load in self.orchestrator.agent_loads.items():
            # 检查代理负载
            max_load = self._get_agent_max_load(agent_id)
            if load >= max_load:
                continue

            # 检查代理是否活跃
            perf = self.agent_performance.get(agent_id)
            if perf and perf.last_active:
                idle_time = (datetime.now() - perf.last_active).total_seconds()
                if idle_time > self.agent_timeout:
                    continue

            available.append(agent_id)

        return available

    async def _get_least_loaded_agent(self, task: Task) -> Optional[str]:
        """获取负载最轻的代理"""
        candidates = await self._get_available_agents(task)

        if not candidates:
            return None

        # 选择当前负载最低的代理
        least_loaded = min(
            candidates,
            key=lambda aid: self.orchestrator.agent_loads.get(aid, 0)
        )

        return least_loaded

    async def _get_best_performing_agent(self, candidates: List[str]) -> Optional[str]:
        """获取性能最好的代理"""
        if not candidates:
            return None

        # 根据成功率选择
        best_agent = max(
            candidates,
            key=lambda aid: self.agent_performance[aid].success_rate
        )

        return best_agent

    async def _get_fastest_response_agent(self, task: Task) -> Optional[str]:
        """获取响应最快的代理"""
        candidates = await self._get_available_agents(task)

        if not candidates:
            return None

        # 选择平均任务时间最短的代理
        fastest = min(
            candidates,
            key=lambda aid: self.agent_performance[aid].avg_task_time or float('inf')
        )

        return fastest

    def _get_agent_max_load(self, agent_id: str) -> int:
        """获取代理最大负载"""
        # 根据代理性能动态调整
        perf = self.agent_performance.get(agent_id)
        if perf and perf.success_rate > 0.9:
            return 5  # 高性能代理可以处理更多任务
        else:
            return 3  # 默认负载限制

    def _estimate_task_duration(self, task: Task) -> float:
        """估计任务执行时长"""
        # 基于任务类型和历史数据估计
        task_type_durations = {
            "conversation": 15.0,
            "code_analysis": 45.0,
            "code_generation": 120.0,
            "data_analysis": 90.0,
            "kb_qa": 30.0,
            "sql_query": 60.0,
            "file_processing": 45.0
        }

        base_duration = task_type_durations.get(task.type, 60.0)

        # 根据任务复杂度调整
        complexity_multiplier = 1.0
        if "complex" in task.description.lower():
            complexity_multiplier = 1.5
        elif "simple" in task.description.lower():
            complexity_multiplier = 0.7

        # 根据优先级调整
        priority_multiplier = 1.0
        if task.priority == TaskPriority.URGENT:
            priority_multiplier = 0.8  # 紧急任务执行更快

        return base_duration * complexity_multiplier * priority_multiplier

    def _get_task_deadline(self, task: Task) -> Optional[datetime]:
        """获取任务截止时间"""
        # 从任务输入或属性中获取截止时间
        deadline_str = task.input_data.get("deadline")
        if deadline_str:
            try:
                return datetime.fromisoformat(deadline_str)
            except:
                pass

        # 根据优先级推断默认截止时间
        if task.priority == TaskPriority.URGENT:
            return task.created_at + timedelta(minutes=5)
        elif task.priority == TaskPriority.HIGH:
            return task.created_at + timedelta(hours=1)
        elif task.priority == TaskPriority.NORMAL:
            return task.created_at + timedelta(hours=24)
        else:
            return task.created_at + timedelta(days=3)

    async def _update_load_history(self):
        """更新负载历史"""
        current_load = len([
            t for t in self.orchestrator.tasks.values()
            if t.status == TaskStatus.RUNNING
        ])

        now = datetime.now()
        self.load_history.append((now, current_load))

        # 保持历史记录在合理范围内
        cutoff = now - timedelta(hours=1)
        self.load_history = [
            (t, load) for t, load in self.load_history
            if t > cutoff
        ]

    async def predict_load(self, minutes_ahead: int = 5) -> float:
        """预测未来负载"""
        if len(self.load_history) < 2:
            return float(len(self.orchestrator.tasks))

        # 使用简单的线性回归预测
        times = [
            (t - self.load_history[0][0]).total_seconds()
            for t, _ in self.load_history
        ]
        loads = [load for _, load in self.load_history]

        # 计算趋势
        if len(times) > 1:
            slope = np.polyfit(times, loads, 1)[0]
            future_time = times[-1] + minutes_ahead * 60
            predicted_load = slope * future_time + loads[0]
        else:
            predicted_load = loads[-1]

        return max(0, predicted_load)

    async def _optimization_loop(self):
        """调度优化循环"""
        while True:
            try:
                await asyncio.sleep(self.optimization_interval)

                # 更新代理性能指标
                await self._update_agent_performance()

                # 动态调整调度策略
                await self._adjust_scheduling_strategy()

                # 预测负载并调整资源
                predicted_load = await self.predict_load()
                await self._adjust_resources(predicted_load)

                self.last_optimization = datetime.now()

            except Exception as e:
                logger.error(f"Scheduler optimization error: {str(e)}")

    async def _update_agent_performance(self):
        """更新代理性能指标"""
        # 分析最近完成的任务
        recent_tasks = [
            t for t in self.orchestrator.tasks.values()
            if t.status == TaskStatus.COMPLETED and
               t.completed_at and
               t.completed_at > datetime.now() - timedelta(hours=1)
        ]

        # 更新每个代理的性能
        for agent_id in self.orchestrator.agent_pool.keys():
            if agent_id not in self.agent_performance:
                self.agent_performance[agent_id] = AgentPerformance(agent_id=agent_id)

            perf = self.agent_performance[agent_id]

            # 统计该代理的任务
            agent_tasks = [
                t for t in recent_tasks
                if t.assigned_agent == agent_id
            ]

            if agent_tasks:
                # 更新统计信息
                perf.completed_tasks += len(agent_tasks)
                perf.total_duration += sum(
                    (t.completed_at - t.started_at).total_seconds()
                    for t in agent_tasks
                    if t.started_at and t.completed_at
                )
                perf.avg_task_time = perf.total_duration / perf.completed_tasks

                # 计算成功率
                failed_tasks = [
                    t for t in self.orchestrator.tasks.values()
                    if t.assigned_agent == agent_id and
                       t.status == TaskStatus.FAILED and
                       t.completed_at and
                       t.completed_at > datetime.now() - timedelta(hours=1)
                ]
                total_tasks = len(agent_tasks) + len(failed_tasks)
                perf.success_rate = len(agent_tasks) / max(1, total_tasks)

            perf.last_active = datetime.now()

    async def _adjust_scheduling_strategy(self):
        """动态调整调度策略"""
        # 根据当前系统状态调整策略权重
        current_load = len([
            t for t in self.orchestrator.tasks.values()
            if t.status == TaskStatus.RUNNING
        ])

        if current_load > self.max_concurrent_tasks * 0.8:
            # 高负载，更重视负载均衡
            self.strategy_weights[SchedulingStrategy.LOAD_BALANCED] = 0.5
            self.strategy_weights[SchedulingStrategy.PRIORITY] = 0.2
            self.strategy_weights[SchedulingStrategy.SHORTEST_JOB] = 0.1
            self.strategy_weights[SchedulingStrategy.DEADLINE_FIRST] = 0.2
        elif current_load < self.max_concurrent_tasks * 0.3:
            # 低负载，可以优化响应时间
            self.strategy_weights[SchedulingStrategy.PRIORITY] = 0.4
            self.strategy_weights[SchedulingStrategy.SHORTEST_JOB] = 0.3
            self.strategy_weights[SchedulingStrategy.LOAD_BALANCED] = 0.2
            self.strategy_weights[SchedulingStrategy.DEADLINE_FIRST] = 0.1
        else:
            # 中等负载，平衡各方面
            self.strategy_weights = {
                SchedulingStrategy.PRIORITY: 0.3,
                SchedulingStrategy.LOAD_BALANCED: 0.3,
                SchedulingStrategy.SHORTEST_JOB: 0.2,
                SchedulingStrategy.DEADLINE_FIRST: 0.2
            }

    async def _adjust_resources(self, predicted_load: float):
        """根据预测负载调整资源"""
        # 如果预测负载过高，可以：
        # 1. 预创建更多代理
        # 2. 限制低优先级任务
        # 3. 提示用户系统繁忙

        if predicted_load > self.max_concurrent_tasks * 0.9:
            logger.warning(f"High load predicted: {predicted_load:.1f} tasks")

            # TODO: 实现资源调整策略

    async def get_scheduling_metrics(self) -> Dict[str, Any]:
        """获取调度指标"""
        return {
            "strategy": self.strategy.value,
            "strategy_weights": self.strategy_weights,
            "current_load": len([
                t for t in self.orchestrator.tasks.values()
                if t.status == TaskStatus.RUNNING
            ]),
            "predicted_load": await self.predict_load(),
            "agent_performance": {
                aid: {
                    "completed_tasks": perf.completed_tasks,
                    "success_rate": perf.success_rate,
                    "avg_task_time": perf.avg_task_time
                }
                for aid, perf in self.agent_performance.items()
            },
            "last_optimization": self.last_optimization.isoformat()
        }