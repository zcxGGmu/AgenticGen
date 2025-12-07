"""
AI模型管理API路由
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ai_models import (
    get_available_ai_models,
    model_manager,
    model_comparator,
    run_model_comparison,
    ModelEvaluationMetrics,
    ComparisonResult
)
from auth.middleware import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["AI Models"])

# 请求/响应模型
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    context: Optional[List[Dict[str, str]]] = None
    stream: bool = True

class ModelConfigUpdate(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None

class ComparisonRequest(BaseModel):
    models: List[str]
    test_prompts: Optional[List[str]] = None

# API端点
@router.get("/", summary="获取可用模型列表")
async def list_models(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    获取所有可用的AI模型列表
    """
    try:
        models = get_available_ai_models()
        return models
    except Exception as e:
        logger.error(f"Failed to get models: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve models")

@router.get("/{model_id}", summary="获取模型详细信息")
async def get_model_info(
    model_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取特定模型的详细信息
    """
    try:
        info = model_manager.get_model_info(model_id)
        if not info:
            raise HTTPException(status_code=404, detail="Model not found")
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model info")

@router.post("/{model_id}/test", summary="测试模型")
async def test_model(
    model_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    测试模型是否可用
    """
    try:
        result = await model_manager.test_model(model_id)
        return result
    except Exception as e:
        logger.error(f"Failed to test model: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to test model")

@router.post("/chat", summary="与AI模型聊天")
async def chat_with_model(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    与指定的AI模型进行聊天
    """
    try:
        from ai_models import chat_with_ai

        response = await chat_with_ai(
            message=request.message,
            model=request.model,
            context=request.context,
            stream=request.stream
        )

        if request.stream:
            from fastapi.responses import StreamingResponse

            async def stream_response():
                async for chunk in response:
                    yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_response(),
                media_type="text/plain",
                headers={"Cache-Control": "no-cache"}
            )
        else:
            return response

    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat request failed")

@router.post("/compare", summary="比较模型性能")
async def compare_models(
    request: ComparisonRequest,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    比较多个模型的性能
    """
    try:
        # 验证模型是否存在
        available_models = get_available_ai_models()
        available_ids = [m["id"] for m in available_models]

        for model in request.models:
            if model not in available_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model not available: {model}"
                )

        # 运行比较
        if request.test_prompts:
            # 使用自定义测试用例
            test_cases = [{"prompt": p} for p in request.test_prompts]
            comparison = await model_comparator.compare_models(
                request.models,
                test_cases
            )
        else:
            # 使用默认测试用例
            comparison = await run_model_comparison(request.models)

        # 生成报告
        report = model_comparator.generate_report(comparison)

        return {
            "comparison": {
                "models": [asdict(m) for m in comparison.models],
                "winner_speed": comparison.winner_speed,
                "winner_quality": comparison.winner_quality,
                "winner_cost": comparison.winner_cost,
                "overall_score": comparison.overall_score,
                "timestamp": comparison.timestamp.isoformat()
            },
            "report": report
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Model comparison failed")

@router.get("/embeddings", summary="获取文本嵌入")
async def get_embeddings(
    texts: List[str] = Query(...),
    model: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user)
) -> List[List[float]]:
    """
    获取文本的向量嵌入
    """
    try:
        from ai_models import get_text_embeddings

        embeddings = await get_text_embeddings(texts)
        return embeddings

    except Exception as e:
        logger.error(f"Failed to get embeddings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get embeddings")

@router.get("/stats", summary="获取模型使用统计")
async def get_model_stats(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取模型使用统计信息
    """
    try:
        # 这里可以实现统计功能
        # 例如：调用次数、错误率、平均响应时间等
        return {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time": 0,
            "models_used": {}
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")

@router.get("/health", summary="检查模型服务健康状态")
async def health_check() -> Dict[str, Any]:
    """
    检查所有模型服务的健康状态
    """
    try:
        models = get_available_ai_models()
        health_status = {}

        for model in models:
            try:
                # 快速测试模型
                result = await model_manager.test_model(model["id"])
                health_status[model["id"]] = {
                    "status": "healthy" if result["status"] == "success" else "unhealthy",
                    "last_check": result.get("duration", "N/A"),
                    "error": result.get("error") if result.get("status") == "error" else None
                }
            except Exception as e:
                health_status[model["id"]] = {
                    "status": "unhealthy",
                    "last_check": "N/A",
                    "error": str(e)
                }

        return {
            "overall": "healthy" if all(
                h["status"] == "healthy" for h in health_status.values()
            ) else "degraded",
            "models": health_status
        }

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")