"""
编排系统API路由
提供任务提交、状态查询和代理管理功能
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field

from orchestration import (
    orchestrator,
    Task,
    TaskPriority,
    TaskStatus
)
from auth.middleware import get_current_user
from auth.permissions import check_user_permission, Permission

logger = logging.getLogger(__name__)
router = APIRouter(tags=["编排系统"])


# 请求/响应模型
class TaskCreateRequest(BaseModel):
    """任务创建请求"""
    type: str = Field(..., description="任务类型")
    description: str = Field(..., description="任务描述")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="输入数据")
    priority: str = Field("normal", description="优先级: low/normal/high/urgent")
    dependencies: List[str] = Field(default_factory=list, description="依赖任务ID列表")


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    type: str
    description: str
    status: str
    priority: int
    assigned_agent: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[Dict[str, Any]]
    error: Optional[str]


class AgentInfo(BaseModel):
    """代理信息"""
    id: str
    type: str
    status: str
    current_tasks: int
    max_tasks: int
    performance: Dict[str, float]


# API端点
@router.post("/tasks", summary="提交新任务")
async def submit_task(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, str]:
    """
    提交新任务到编排系统
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.TOOL_PYTHON
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: tool access required"
            )

        # 转换优先级
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT
        }
        priority = priority_map.get(request.priority, TaskPriority.NORMAL)

        # 提交任务
        task_id = await orchestrator.submit_task(
            task_type=request.type,
            description=request.description,
            input_data=request.input_data,
            priority=priority,
            dependencies=request.dependencies
        )

        return {"task_id": task_id, "message": "Task submitted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit task: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit task")


@router.get("/tasks/{task_id}", summary="获取任务状态")
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user)
) -> TaskResponse:
    """
    获取任务执行状态
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.TOOL_PYTHON
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: tool access required"
            )

        status = await orchestrator.get_task_status(task_id)

        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found"
            )

        return TaskResponse(**status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get task status")


@router.delete("/tasks/{task_id}", summary="取消任务")
async def cancel_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, str]:
    """
    取消正在执行或等待中的任务
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.TOOL_PYTHON
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: tool access required"
            )

        success = await orchestrator.cancel_task(task_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found or cannot be cancelled"
            )

        return {"message": f"Task {task_id} cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cancel task")


@router.get("/tasks", summary="获取任务列表")
async def list_tasks(
    status: Optional[str] = Query(None, description="过滤状态"),
    type: Optional[str] = Query(None, description="过滤类型"),
    limit: int = Query(50, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: dict = Depends(get_current_user)
) -> List[TaskResponse]:
    """
    获取任务列表
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.TOOL_PYTHON
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: tool access required"
            )

        # 获取所有任务
        all_tasks = []
        for task in orchestrator.tasks.values():
            task_status = await orchestrator.get_task_status(task.id)
            if task_status:
                # 应用过滤条件
                if status and task_status["status"] != status:
                    continue
                if type and task_status["type"] != type:
                    continue

                all_tasks.append(TaskResponse(**task_status))

        # 排序（按创建时间倒序）
        all_tasks.sort(key=lambda t: t.created_at, reverse=True)

        # 应用分页
        return all_tasks[offset:offset + limit]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list tasks: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list tasks")


@router.get("/agents", summary="获取代理列表")
async def list_agents(
    current_user: dict = Depends(get_current_user)
) -> List[AgentInfo]:
    """
    获取活跃代理列表
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.SYSTEM_MONITOR
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: system monitor required"
            )

        agents = []
        for agent_id, agent in orchestrator.agent_pool.items():
            # 获取代理负载
            current_load = orchestrator.agent_loads.get(agent_id, 0)

            # 获取代理性能（如果有调度器）
            performance = {}
            if hasattr(orchestrator, 'scheduler'):
                perf = orchestrator.scheduler.agent_performance.get(agent_id)
                if perf:
                    performance = {
                        "completed_tasks": perf.completed_tasks,
                        "success_rate": perf.success_rate,
                        "avg_task_time": perf.avg_task_time
                    }

            agents.append(AgentInfo(
                id=agent_id,
                type=agent.agent_type.value,
                status="active",  # TODO: 获取真实状态
                current_tasks=current_load,
                max_tasks=5,  # TODO: 从配置获取
                performance=performance
            ))

        return agents

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list agents")


@router.get("/metrics", summary="获取编排系统指标")
async def get_metrics(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取编排系统性能指标
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.SYSTEM_MONITOR
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: system monitor required"
            )

        # 获取基础指标
        metrics = await orchestrator.get_metrics()

        # 添加调度器指标（如果有）
        if hasattr(orchestrator, 'scheduler'):
            scheduler_metrics = await orchestrator.scheduler.get_scheduling_metrics()
            metrics["scheduler"] = scheduler_metrics

        # 添加任务类型统计
        task_type_stats = {}
        for task in orchestrator.tasks.values():
            task_type = task.type
            if task_type not in task_type_stats:
                task_type_stats[task_type] = {
                    "total": 0,
                    "completed": 0,
                    "failed": 0,
                    "running": 0,
                    "pending": 0
                }

            task_type_stats[task_type]["total"] += 1

            if task.status == TaskStatus.COMPLETED:
                task_type_stats[task_type]["completed"] += 1
            elif task.status == TaskStatus.FAILED:
                task_type_stats[task_type]["failed"] += 1
            elif task.status == TaskStatus.RUNNING:
                task_type_stats[task_type]["running"] += 1
            elif task.status == TaskStatus.PENDING:
                task_type_stats[task_type]["pending"] += 1

        metrics["task_types"] = task_type_stats

        return metrics

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@router.get("/capabilities", summary="获取系统能力")
async def get_capabilities(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取编排系统支持的能力
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.TOOL_PYTHON
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: tool access required"
            )

        capabilities = {}
        for name, cap in orchestrator.capabilities.items():
            capabilities[name] = {
                "description": cap.description,
                "agent_types": [t.value for t in cap.agent_types],
                "required_tools": cap.required_tools,
                "max_concurrent_tasks": cap.max_concurrent_tasks,
                "estimated_duration": cap.estimated_duration
            }

        return {
            "capabilities": capabilities,
            "total_capabilities": len(capabilities)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get capabilities")


@router.post("/batch", summary="批量提交任务")
async def submit_batch_tasks(
    tasks: List[TaskCreateRequest],
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    批量提交任务
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.TOOL_PYTHON
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: tool access required"
            )

        # 限制批量大小
        if len(tasks) > 100:
            raise HTTPException(
                status_code=400,
                detail="Batch size cannot exceed 100 tasks"
            )

        submitted_tasks = []
        errors = []

        # 提交每个任务
        for i, task_request in enumerate(tasks):
            try:
                # 转换优先级
                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                    "urgent": TaskPriority.URGENT
                }
                priority = priority_map.get(task_request.priority, TaskPriority.NORMAL)

                # 提交任务
                task_id = await orchestrator.submit_task(
                    task_type=task_request.type,
                    description=task_request.description,
                    input_data=task_request.input_data,
                    priority=priority,
                    dependencies=task_request.dependencies
                )

                submitted_tasks.append({
                    "index": i,
                    "task_id": task_id,
                    "status": "submitted"
                })

            except Exception as e:
                errors.append({
                    "index": i,
                    "error": str(e)
                })

        return {
            "submitted": len(submitted_tasks),
            "errors": len(errors),
            "tasks": submitted_tasks,
            "error_details": errors
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit batch tasks: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit batch tasks")