"""
智能代理编排系统
实现多代理协作、任务分发和智能调度
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime

from agent.base_agent import BaseAgent
from agent.agent_factory import AgentFactory, AgentType
from ai_models.model_manager import ModelManager
from cache.multi_level_cache import MultiLevelCache

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentCapability:
    """代理能力定义"""
    name: str
    description: str
    agent_types: List[AgentType]
    required_tools: List[str] = field(default_factory=list)
    max_concurrent_tasks: int = 3
    estimated_duration: float = 30.0  # 秒


@dataclass
class Task:
    """任务定义"""
    id: str
    type: str
    description: str
    input_data: Dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    parent_task: Optional[str] = None


class AgentOrchestrator:
    """智能代理编排器"""

    def __init__(self):
        self.model_manager = ModelManager()
        self.agent_factory = AgentFactory()
        self.cache = MultiLevelCache()

        # 代理池
        self.agent_pool: Dict[str, BaseAgent] = {}

        # 任务队列
        self.task_queue = asyncio.PriorityQueue()

        # 任务跟踪
        self.tasks: Dict[str, Task] = {}

        # 能力注册表
        self.capabilities: Dict[str, AgentCapability] = {}

        # 代理负载跟踪
        self.agent_loads: Dict[str, int] = {}

        # 性能指标
        self.metrics = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "avg_duration": 0.0,
            "agent_utilization": {}
        }

        # 注册标准能力
        self._register_standard_capabilities()

    def _register_standard_capabilities(self):
        """注册标准代理能力"""
        capabilities = [
            AgentCapability(
                name="code_analysis",
                description="代码分析和理解",
                agent_types=[AgentType.CODING],
                required_tools=["python_executor"],
                max_concurrent_tasks=5,
                estimated_duration=45.0
            ),
            AgentCapability(
                name="code_generation",
                description="代码生成和优化",
                agent_types=[AgentType.CODING],
                required_tools=["python_executor", "git_tool"],
                max_concurrent_tasks=3,
                estimated_duration=120.0
            ),
            AgentCapability(
                name="data_analysis",
                description="数据分析和可视化",
                agent_types=[AgentType.CODING],
                required_tools=["python_executor", "data_analysis"],
                max_concurrent_tasks=3,
                estimated_duration=90.0
            ),
            AgentCapability(
                name="kb_qa",
                description="知识库问答",
                agent_types=[AgentType.GENERAL],
                required_tools=["knowledge_base"],
                max_concurrent_tasks=10,
                estimated_duration=30.0
            ),
            AgentCapability(
                name="sql_query",
                description="SQL查询和分析",
                agent_types=[AgentType.GENERAL],
                required_tools=["sql_executor"],
                max_concurrent_tasks=5,
                estimated_duration=60.0
            ),
            AgentCapability(
                name="file_processing",
                description="文件处理和转换",
                agent_types=[AgentType.GENERAL],
                required_tools=["file_tool"],
                max_concurrent_tasks=5,
                estimated_duration=45.0
            ),
            AgentCapability(
                name="conversation",
                description="通用对话交流",
                agent_types=[AgentType.GENERAL],
                max_concurrent_tasks=20,
                estimated_duration=15.0
            )
        ]

        for cap in capabilities:
            self.capabilities[cap.name] = cap

    async def submit_task(
        self,
        task_type: str,
        description: str,
        input_data: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: List[str] = None
    ) -> str:
        """提交任务"""
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.tasks)}"

        task = Task(
            id=task_id,
            type=task_type,
            description=description,
            input_data=input_data,
            priority=priority,
            dependencies=dependencies or []
        )

        self.tasks[task_id] = task

        # 检查依赖
        if await self._check_dependencies(task):
            await self.task_queue.put((
                -priority.value,  # 负数用于优先级队列
                task_id
            ))
            logger.info(f"Task {task_id} queued for execution")
        else:
            logger.info(f"Task {task_id} waiting for dependencies")

        self.metrics["total_tasks"] += 1

        # 缓存任务信息
        await self.cache.set(f"task:{task_id}", task.__dict__)

        return task_id

    async def _check_dependencies(self, task: Task) -> bool:
        """检查任务依赖"""
        for dep_id in task.dependencies:
            if dep_id not in self.tasks:
                logger.warning(f"Dependency {dep_id} not found for task {task.id}")
                return False

            dep_task = self.tasks[dep_id]
            if dep_task.status != TaskStatus.COMPLETED:
                return False

        return True

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        # 先从缓存获取
        cached = await self.cache.get(f"task:{task_id}")
        if cached:
            return cached

        # 从内存获取
        task = self.tasks.get(task_id)
        if task:
            return {
                "id": task.id,
                "type": task.type,
                "status": task.status.value,
                "priority": task.priority.value,
                "assigned_agent": task.assigned_agent,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "result": task.result,
                "error": task.error
            }

        return None

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return False

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()

        # 如果任务正在执行，通知代理停止
        if task.assigned_agent and task.assigned_agent in self.agent_pool:
            agent = self.agent_pool[task.assigned_agent]
            try:
                # TODO: 实现代理任务中断机制
                pass
            except Exception as e:
                logger.error(f"Failed to cancel task {task_id}: {str(e)}")

        logger.info(f"Task {task_id} cancelled")
        return True

    async def _get_best_agent(self, task: Task) -> Optional[str]:
        """选择最适合的代理"""
        # 获取任务对应的能力
        capability = self.capabilities.get(task.type)
        if not capability:
            logger.warning(f"Unknown task type: {task.type}")
            return None

        # 筛选能够处理该任务的代理
        candidates = []

        for agent_id, agent in self.agent_pool.items():
            # 检查代理类型
            if agent.agent_type not in capability.agent_types:
                continue

            # 检查负载
            current_load = self.agent_loads.get(agent_id, 0)
            if current_load >= capability.max_concurrent_tasks:
                continue

            # 计算适合度分数
            score = self._calculate_agent_score(agent_id, capability)
            candidates.append((score, agent_id))

        if not candidates:
            # 创建新代理
            new_agent = await self._create_agent_for_task(task, capability)
            if new_agent:
                return new_agent

        # 选择分数最高的代理
        candidates.sort(reverse=True)
        return candidates[0][1] if candidates else None

    def _calculate_agent_score(self, agent_id: str, capability: AgentCapability) -> float:
        """计算代理适合度分数"""
        score = 100.0

        # 负载惩罚
        load = self.agent_loads.get(agent_id, 0)
        score -= load * 20

        # 历史性能奖励
        # TODO: 基于历史完成时间和质量调整分数

        return max(0, score)

    async def _create_agent_for_task(self, task: Task, capability: AgentCapability) -> Optional[str]:
        """为任务创建新代理"""
        try:
            # 选择代理类型
            agent_type = capability.agent_types[0]

            # 创建代理
            agent_id = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.agent_pool)}"
            agent = await self.agent_factory.create_agent(
                thread_id=f"orchestrated_{task.id}",
                agent_type=agent_type
            )

            if agent:
                self.agent_pool[agent_id] = agent
                self.agent_loads[agent_id] = 0

                logger.info(f"Created new agent {agent_id} for task {task.id}")
                return agent_id

        except Exception as e:
            logger.error(f"Failed to create agent for task {task.id}: {str(e)}")

        return None

    async def _execute_task(self, task: Task, agent_id: str):
        """执行任务"""
        agent = self.agent_pool[agent_id]

        try:
            # 更新任务状态
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            task.assigned_agent = agent_id
            self.agent_loads[agent_id] += 1

            logger.info(f"Executing task {task.id} with agent {agent_id}")

            # 根据任务类型执行不同的逻辑
            if task.type == "conversation":
                result = await self._execute_conversation_task(task, agent)
            elif task.type == "code_analysis":
                result = await self._execute_code_analysis_task(task, agent)
            elif task.type == "code_generation":
                result = await self._execute_code_generation_task(task, agent)
            elif task.type == "data_analysis":
                result = await self._execute_data_analysis_task(task, agent)
            elif task.type == "kb_qa":
                result = await self._execute_kb_qa_task(task, agent)
            elif task.type == "sql_query":
                result = await self._execute_sql_query_task(task, agent)
            elif task.type == "file_processing":
                result = await self._execute_file_processing_task(task, agent)
            else:
                result = await self._execute_general_task(task, agent)

            # 更新任务结果
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()

            # 更新指标
            self.metrics["completed_tasks"] += 1
            duration = (task.completed_at - task.started_at).total_seconds()
            self._update_avg_duration(duration)

            logger.info(f"Task {task.id} completed successfully")

        except Exception as e:
            # 任务失败
            task.error = str(e)
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()

            self.metrics["failed_tasks"] += 1

            logger.error(f"Task {task.id} failed: {str(e)}")

        finally:
            # 释放代理负载
            if agent_id in self.agent_loads:
                self.agent_loads[agent_id] -= 1

            # 检查并激活依赖任务
            await self._activate_dependent_tasks(task.id)

    async def _execute_conversation_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行对话任务"""
        message = task.input_data.get("message", "")
        context = task.input_data.get("context", {})

        response = await agent.chat_async(message, context)

        return {
            "response": response,
            "type": "conversation"
        }

    async def _execute_code_analysis_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行代码分析任务"""
        code = task.input_data.get("code", "")
        analysis_type = task.input_data.get("analysis_type", "general")

        prompt = f"Please analyze the following code ({analysis_type}):\n\n{code}"
        response = await agent.chat_async(prompt)

        return {
            "analysis": response,
            "type": "code_analysis"
        }

    async def _execute_code_generation_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行代码生成任务"""
        requirements = task.input_data.get("requirements", "")
        language = task.input_data.get("language", "python")

        prompt = f"Generate {language} code for the following requirements:\n\n{requirements}"
        response = await agent.chat_async(prompt)

        return {
            "code": response,
            "language": language,
            "type": "code_generation"
        }

    async def _execute_data_analysis_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行数据分析任务"""
        data_description = task.input_data.get("data_description", "")
        analysis_goal = task.input_data.get("analysis_goal", "")

        prompt = f"""
        Analyze the following data:

        Data Description: {data_description}
        Analysis Goal: {analysis_goal}

        Provide insights, visualizations, and recommendations.
        """
        response = await agent.chat_async(prompt)

        return {
            "analysis": response,
            "type": "data_analysis"
        }

    async def _execute_kb_qa_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行知识库问答任务"""
        question = task.input_data.get("question", "")
        kb_ids = task.input_data.get("kb_ids", [])

        # TODO: 集成知识库检索
        response = await agent.chat_async(question)

        return {
            "answer": response,
            "sources": [],  # TODO: 返回引用来源
            "type": "kb_qa"
        }

    async def _execute_sql_query_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行SQL查询任务"""
        query_description = task.input_data.get("query_description", "")
        schema = task.input_data.get("schema", "")

        prompt = f"""
        Generate an SQL query based on the following:

        Database Schema: {schema}
        Query Description: {query_description}

        Provide the SQL query and explanation.
        """
        response = await agent.chat_async(prompt)

        return {
            "query": response,
            "type": "sql_query"
        }

    async def _execute_file_processing_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行文件处理任务"""
        file_info = task.input_data.get("file_info", {})
        processing_goal = task.input_data.get("processing_goal", "")

        prompt = f"""
        Process the following file:

        File Information: {file_info}
        Processing Goal: {processing_goal}

        Provide processing steps and results.
        """
        response = await agent.chat_async(prompt)

        return {
            "result": response,
            "type": "file_processing"
        }

    async def _execute_general_task(self, task: Task, agent: BaseAgent) -> Dict[str, Any]:
        """执行通用任务"""
        prompt = f"""
        Task: {task.description}
        Input Data: {json.dumps(task.input_data, indent=2)}

        Please complete this task to the best of your ability.
        """
        response = await agent.chat_async(prompt)

        return {
            "result": response,
            "type": "general"
        }

    async def _activate_dependent_tasks(self, completed_task_id: str):
        """激活依赖已完成任务的任务"""
        for task_id, task in self.tasks.items():
            if (task.status == TaskStatus.PENDING and
                completed_task_id in task.dependencies):

                if await self._check_dependencies(task):
                    await self.task_queue.put((
                        -task.priority.value,
                        task_id
                    ))
                    logger.info(f"Activated dependent task {task_id}")

    def _update_avg_duration(self, duration: float):
        """更新平均任务时长"""
        total = self.metrics["completed_tasks"]
        if total == 1:
            self.metrics["avg_duration"] = duration
        else:
            current_avg = self.metrics["avg_duration"]
            self.metrics["avg_duration"] = (
                (current_avg * (total - 1) + duration) / total
            )

    async def get_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        return {
            **self.metrics,
            "active_agents": len(self.agent_pool),
            "queued_tasks": self.task_queue.qsize(),
            "pending_tasks": len([
                t for t in self.tasks.values()
                if t.status == TaskStatus.PENDING
            ]),
            "running_tasks": len([
                t for t in self.tasks.values()
                if t.status == TaskStatus.RUNNING
            ]),
            "agent_loads": self.agent_loads.copy()
        }

    async def start_orchestration(self):
        """启动编排循环"""
        logger.info("Starting agent orchestration loop")

        while True:
            try:
                # 获取待执行任务
                if not self.task_queue.empty():
                    _, task_id = await self.task_queue.get()
                    task = self.tasks.get(task_id)

                    if task and task.status == TaskStatus.PENDING:
                        # 选择代理
                        agent_id = await self._get_best_agent(task)

                        if agent_id:
                            # 执行任务
                            asyncio.create_task(
                                self._execute_task(task, agent_id)
                            )
                        else:
                            # 没有可用代理，重新排队
                            await self.task_queue.put((_, task_id))
                            await asyncio.sleep(1)

                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Orchestration loop error: {str(e)}")
                await asyncio.sleep(1)

    async def shutdown(self):
        """关闭编排器"""
        logger.info("Shutting down agent orchestrator")

        # 等待所有任务完成或取消
        for task in self.tasks.values():
            if task.status == TaskStatus.RUNNING:
                await self.cancel_task(task.id)

        # 清理代理
        for agent_id, agent in self.agent_pool.items():
            try:
                await agent.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up agent {agent_id}: {str(e)}")

        self.agent_pool.clear()
        self.agent_loads.clear()

        logger.info("Agent orchestrator shutdown complete")


# 全局实例
orchestrator = AgentOrchestrator()