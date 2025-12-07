"""
工具执行API路由
"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from tools.python_executor import PythonExecutor
from tools.sql_executor import SQLExecutor
from auth.decorators import get_current_user_id
from config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 全局执行器实例
python_executor = PythonExecutor()
sql_executor = SQLExecutor()


class PythonCodeRequest(BaseModel):
    """Python代码执行请求"""
    code: str = Field(..., description="Python代码")
    timeout: Optional[int] = Field(30, description="超时时间（秒）")
    capture_output: Optional[bool] = Field(True, description="是否捕获输出")


class SQLQueryRequest(BaseModel):
    """SQL查询请求"""
    query: str = Field(..., description="SQL查询")
    parameters: Optional[Dict[str, Any]] = Field(None, description="参数")
    timeout: Optional[int] = Field(30, description="超时时间（秒）")
    limit: Optional[int] = Field(1000, description="结果数量限制")


class ToolExecutionResponse(BaseModel):
    """工具执行响应"""
    success: bool
    result: Optional[Any] = None
    output: Optional[str] = None
    error_output: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    row_count: Optional[int] = None


@router.post("/python/execute", response_model=ToolExecutionResponse)
async def execute_python_code(
    request: PythonCodeRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    执行Python代码
    """
    try:
        # 验证代码
        validation = await python_executor.check_syntax(request.code)
        if not validation["valid"]:
            return ToolExecutionResponse(
                success=False,
                error=f"代码语法错误: {validation['error']}",
            )

        # 执行代码
        result = await python_executor.execute(
            code=request.code,
            timeout=request.timeout,
            capture_output=request.capture_output,
        )

        return ToolExecutionResponse(
            success=result["success"],
            result=result.get("result"),
            output=result.get("output", ""),
            error_output=result.get("error_output", ""),
            error=result.get("error"),
            execution_time=result.get("execution_time", 0),
        )

    except Exception as e:
        logger.error(f"Python代码执行失败: {str(e)}")
        return ToolExecutionResponse(
            success=False,
            error=str(e),
        )


@router.post("/python/validate")
async def validate_python_code(
    code: str = Body(..., embed=True),
    user_id: str = Depends(get_current_user_id),
):
    """
    验证Python代码
    """
    try:
        result = await python_executor.check_syntax(code)

        return {
            "success": True,
            "validation": result,
        }

    except Exception as e:
        logger.error(f"代码验证失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/python/format")
async def format_python_code(
    code: str = Body(..., embed=True),
    user_id: str = Depends(get_current_user_id),
):
    """
    格式化Python代码
    """
    try:
        result = await python_executor.format_code(code)

        return {
            "success": result["success"],
            "formatted_code": result.get("formatted_code"),
            "error": result.get("error"),
        }

    except Exception as e:
        logger.error(f"代码格式化失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/sql/execute", response_model=ToolExecutionResponse)
async def execute_sql_query(
    request: SQLQueryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    执行SQL查询
    """
    try:
        # 验证SQL
        validation = await sql_executor.validate_and_format(request.sql)
        if not validation["validation"]["valid"]:
            return ToolExecutionResponse(
                success=False,
                error=f"SQL错误: {validation['validation']['error']}",
            )

        # 执行查询
        result = await sql_executor.execute(
            sql=request.sql,
            parameters=request.parameters,
            timeout=request.timeout,
            limit=request.limit,
        )

        return ToolExecutionResponse(
            success=result["success"],
            result=result.get("data"),
            output=result.get("data", []),
            error=result.get("error"),
            execution_time=result.get("execution_time", 0),
            row_count=result.get("row_count", 0),
        )

    except Exception as e:
        logger.error(f"SQL执行失败: {str(e)}")
        return ToolExecutionResponse(
            success=False,
            error=str(e),
        )


@router.post("/sql/explain")
async def explain_sql_query(
    sql: str = Body(..., embed=True),
    analyze: bool = Body(False, embed=True),
    parameters: Optional[Dict[str, Any]] = Body(None, embed=True),
    user_id: str = Depends(get_current_user_id),
):
    """
    执行SQL查询计划
    """
    try:
        result = await sql_executor.explain(
            sql=sql,
            analyze=analyze,
            parameters=parameters,
        )

        return {
            "success": result["success"],
            "plan": result.get("plan"),
            "error": result.get("error"),
        }

    except Exception as e:
        logger.error(f"SQL解释失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/sql/schema")
async def get_database_schema(
    table_name: Optional[str] = None,
    include_sample: bool = False,
    sample_size: int = 5,
    user_id: str = Depends(get_current_user_id),
):
    """
    获取数据库模式信息
    """
    try:
        result = await sql_executor.get_schema_info(
            table_name=table_name,
            include_sample=include_sample,
            sample_size=sample_size,
        )

        return result

    except Exception as e:
        logger.error(f"获取数据库模式失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/sql/suggest")
async def get_sql_suggestions(
    partial_query: str = Body(..., embed=True),
    limit: int = Body(10, embed=True),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取SQL建议
    """
    try:
        suggestions = await sql_executor.get_suggestions(
            partial_query=partial_query,
            limit=limit,
        )

        return {
            "success": True,
            "suggestions": suggestions,
        }

    except Exception as e:
        logger.error(f"获取SQL建议失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/capabilities")
async def get_tool_capabilities():
    """
    获取工具能力信息
    """
    return {
        "success": True,
        "capabilities": {
            "python": {
                "supported": True,
                "features": [
                    "Code execution",
                    "Syntax validation",
                    "Code formatting",
                    "Matplotlib support",
                    "Data analysis",
                    "Machine learning",
                ],
                "allowed_libraries": [
                    "numpy", "pandas", "matplotlib", "seaborn", "plotly",
                    "scipy", "sklearn", "torch", "tensorflow",
                ],
                "sandbox": True,
                "resource_limits": {
                    "max_cpu_time": 30,
                    "max_memory": "512MB",
                    "max_file_size": "10MB",
                },
            },
            "sql": {
                "supported": True,
                "features": [
                    "Query execution",
                    "Query validation",
                    "Query formatting",
                    "Explain plan",
                    "Schema introspection",
                ],
                "allowed_operations": [
                    "SELECT", "SHOW", "DESCRIBE", "EXPLAIN",
                ],
                "safety_features": [
                    "SQL injection protection",
                    "Dangerous keyword blocking",
                    "Result size limiting",
                ],
            },
        },
    }


@router.get("/status")
async def get_tools_status():
    """
    获取工具状态
    """
    python_stats = python_executor.get_stats() if hasattr(python_executor, 'get_stats') else {}
    sql_stats = sql_executor.get_stats() if hasattr(sql_executor, 'get_stats') else {}

    return {
        "success": True,
        "status": {
            "python_executor": {
                "available": True,
                "stats": python_stats,
            },
            "sql_executor": {
                "available": True,
                "stats": sql_stats,
            },
        },
    }