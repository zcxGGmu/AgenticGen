"""
聊天相关API路由
"""

import json
import uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.agent_manager import get_agent_manager
from agent.agent_config import AgentType
from auth.decorators import get_current_user_id
from config.logging import get_logger
import json

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息")
    thread_id: Optional[str] = Field(None, description="会话ID")
    agent_type: Optional[str] = Field("general", description="Agent类型")
    stream: Optional[bool] = Field(False, description="是否使用流式响应")
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool
    response: Optional[str] = None
    thread_id: Optional[str] = None
    agent_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    发送聊天消息
    """
    try:
        # 获取Agent管理器
        agent_manager = get_agent_manager()

        # 生成或使用现有的thread_id
        thread_id = request.thread_id or str(uuid.uuid4())

        # 确定Agent类型
        agent_type = AgentType.GENERAL
        if request.agent_type:
            try:
                agent_type = AgentType(request.agent_type)
            except ValueError:
                logger.warning(f"未知的Agent类型: {request.agent_type}")
                agent_type = AgentType.GENERAL

        # 获取或创建Agent
        agent = await agent_manager.get_or_create_agent(
            thread_id=thread_id,
            agent_type=agent_type
        )

        # 设置上下文
        if request.context:
            for key, value in request.context.items():
                agent.set_context(key, value)

        # 处理消息
        if request.stream:
            # 流式响应
            return StreamingResponse(
                stream_chat_response(agent, request.message, thread_id),
                media_type="text/event-stream",
            )
        else:
            # 普通响应
            response = await agent.chat_async(request.message)

            # 保存状态
            await agent_manager.save_agent_state(thread_id)

            return ChatResponse(
                success=True,
                response=response,
                thread_id=thread_id,
                agent_id=agent.config.agent_id,
                context=agent.context,
            )

    except Exception as e:
        logger.error(f"聊天处理失败: {str(e)}")
        return ChatResponse(
            success=False,
            error=str(e),
        )


@router.get("/threads/{thread_id}/history")
async def get_chat_history(
    thread_id: str,
    limit: int = Query(50, ge=1, le=200, description="历史记录数量限制"),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取聊天历史
    """
    try:
        # TODO: 从数据库获取聊天历史
        # 这里简化实现
        return {
            "success": True,
            "thread_id": thread_id,
            "history": [],
            "message": "功能开发中",
        }

    except Exception as e:
        logger.error(f"获取聊天历史失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    删除会话
    """
    try:
        agent_manager = get_agent_manager()
        success = await agent_manager.remove_agent(thread_id)

        return {
            "success": success,
            "message": "会话删除成功" if success else "会话不存在",
        }

    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/threads")
async def list_threads(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取用户的会话列表
    """
    try:
        # TODO: 从数据库获取会话列表
        # 这里简化实现
        return {
            "success": True,
            "threads": [],
            "total": 0,
            "page": page,
            "size": size,
            "message": "功能开发中",
        }

    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/agents/types")
async def get_agent_types():
    """
    获取可用的Agent类型
    """
    return {
        "success": True,
        "agent_types": [
            {
                "value": "general",
                "label": "通用助手",
                "description": "通用的AI助手，可以回答各种问题和执行各种任务",
            },
            {
                "value": "coding",
                "label": "编程助手",
                "description": "专业的编程助手，精通各种编程语言和技术",
            },
            {
                "value": "data_analysis",
                "label": "数据分析助手",
                "description": "专业的数据分析师，擅长数据清洗、分析、可视化和机器学习",
            },
            {
                "value": "sql",
                "label": "SQL助手",
                "description": "专业的SQL专家，能够将自然语言转换为SQL查询",
            },
            {
                "value": "knowledge",
                "label": "知识库助手",
                "description": "基于知识库的问答助手，能够从知识库中检索和回答问题",
            },
        ],
    }


async def stream_chat_response(agent, message: str, thread_id: str):
    """
    流式聊天响应生成器
    """
    try:
        full_response = ""

        # 发送SSE头
        yield f"data: {json.dumps({'type': 'start', 'thread_id': thread_id})}\n\n"

        # 流式响应
        async for chunk in agent.chat_stream_async(message):
            full_response += chunk

            # 发送内容块
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        # 保存状态
        agent_manager = get_agent_manager()
        await agent_manager.save_agent_state(thread_id)

        # 发送结束事件
        yield f"data: {json.dumps({'type': 'end', 'full_response': full_response})}\n\n"

    except Exception as e:
        logger.error(f"流式响应失败: {str(e)}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@router.post("/threads/{thread_id}/context")
async def update_thread_context(
    thread_id: str,
    context: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    更新会话上下文
    """
    try:
        agent_manager = get_agent_manager()
        agent = await agent_manager.get_or_create_agent(thread_id)

        # 更新上下文
        for key, value in context.items():
            agent.set_context(key, value)

        # 保存状态
        await agent_manager.save_agent_state(thread_id)

        return {
            "success": True,
            "message": "上下文更新成功",
            "context": agent.context,
        }

    except Exception as e:
        logger.error(f"更新上下文失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/threads/{thread_id}/status")
async def get_thread_status(
    thread_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    获取会话状态
    """
    try:
        agent_manager = get_agent_manager()
        status = await agent_manager.get_agent_status(thread_id)

        if status:
            return {
                "success": True,
                "status": status,
            }
        else:
            return {
                "success": False,
                "error": "会话不存在",
            }

    except Exception as e:
        logger.error(f"获取会话状态失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }