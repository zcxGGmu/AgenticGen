"""
工具执行API路由
"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from tools.python_executor import PythonExecutor
from tools.sql_executor import SQLExecutor
from tools.expanded_tools import expanded_tool_manager, GitTool, FilesystemTool, DataAnalysisTool
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


# ============ 扩展工具API ============

class ExpandedToolRequest(BaseModel):
    """扩展工具执行请求"""
    tool_name: str = Field(..., description="工具名称 (git, filesystem, data_analysis)")
    action: str = Field(..., description="操作名称")
    parameters: Dict[str, Any] = Field({}, description="操作参数")


@router.post("/expanded/execute")
async def execute_expanded_tool(
    request: ExpandedToolRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    执行扩展工具操作
    """
    try:
        # 添加用户ID到参数中
        request.parameters["user_id"] = user_id

        # 执行工具
        result = await expanded_tool_manager.execute_tool(
            tool_name=request.tool_name,
            action=request.action,
            parameters=request.parameters
        )

        return result

    except Exception as e:
        logger.error(f"Expanded tool execution failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# Git工具端点
@router.post("/git/status")
async def git_status(
    work_dir: Optional[str] = Body(None),
    user_id: str = Depends(get_current_user_id),
):
    """获取Git状态"""
    git_tool = expanded_tool_manager.get_git_tool(work_dir)
    return await git_tool.get_status()


@router.post("/git/log")
async def git_log(
    limit: int = Body(10),
    work_dir: Optional[str] = Body(None),
    user_id: str = Depends(get_current_user_id),
):
    """获取Git提交日志"""
    git_tool = expanded_tool_manager.get_git_tool(work_dir)
    return await git_tool.get_log(limit)


@router.post("/git/diff")
async def git_diff(
    file: Optional[str] = Body(None),
    work_dir: Optional[str] = Body(None),
    user_id: str = Depends(get_current_user_id),
):
    """获取Git差异"""
    git_tool = expanded_tool_manager.get_git_tool(work_dir)
    return await git_tool.get_diff(file)


@router.post("/git/commit")
async def git_commit(
    message: str = Body(...),
    files: Optional[List[str]] = Body(None),
    work_dir: Optional[str] = Body(None),
    user_id: str = Depends(get_current_user_id),
):
    """Git提交"""
    git_tool = expanded_tool_manager.get_git_tool(work_dir)

    # 添加文件
    if files:
        for file in files:
            await git_tool.add_file(file)

    # 提交
    return await git_tool.commit(message)


# 文件系统工具端点
@router.post("/filesystem/list")
async def list_directory(
    path: str = Body("."),
    user_id: str = Depends(get_current_user_id),
):
    """列出目录内容"""
    fs_tool = FilesystemTool()
    return await fs_tool.list_directory(path)


@router.post("/filesystem/read")
async def read_file(
    path: str = Body(...),
    max_size: int = Body(1024 * 1024),
    user_id: str = Depends(get_current_user_id),
):
    """读取文件"""
    fs_tool = FilesystemTool()
    return await fs_tool.read_file(path, max_size)


@router.post("/filesystem/write")
async def write_file(
    path: str = Body(...),
    content: str = Body(...),
    overwrite: bool = Body(False),
    user_id: str = Depends(get_current_user_id),
):
    """写入文件"""
    fs_tool = FilesystemTool()
    return await fs_tool.write_file(path, content, overwrite)


@router.post("/filesystem/delete")
async def delete_file(
    path: str = Body(...),
    user_id: str = Depends(get_current_user_id),
):
    """删除文件或目录"""
    fs_tool = FilesystemTool()
    return await fs_tool.delete_file(path)


# 数据分析工具端点
@router.post("/data/analyze-csv")
async def analyze_csv(
    file_path: str = Body(...),
    sample_size: int = Body(1000),
    user_id: str = Depends(get_current_user_id),
):
    """分析CSV文件"""
    data_tool = DataAnalysisTool()
    return await data_tool.analyze_csv(file_path, sample_size)


@router.post("/data/visualize")
async def create_visualization(
    data: Union[List[Dict], str] = Body(...),
    chart_type: str = Body(...),
    x_col: Optional[str] = Body(None),
    y_col: Optional[str] = Body(None),
    user_id: str = Depends(get_current_user_id),
):
    """创建数据可视化

    data可以是数据列表或CSV文件路径
    """
    import json

    data_tool = DataAnalysisTool()

    # 如果data是JSON字符串，解析它
    if isinstance(data, str) and data.endswith('.csv'):
        # 是文件路径
        return await data_tool.create_visualization(data, chart_type, x_col, y_col)
    else:
        # 是数据
        if isinstance(data, str):
            data = json.loads(data)
        return await data_tool.create_visualization(data, chart_type, x_col, y_col)


@router.post("/data/correlation")
async def correlation_analysis(
    file_path: str = Body(...),
    user_id: str = Depends(get_current_user_id),
):
    """相关性分析"""
    data_tool = DataAnalysisTool()
    return await data_tool.correlation_analysis(file_path)


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
            "expanded_tools": {
                "git": {"available": True},
                "filesystem": {"available": True},
                "data_analysis": {"available": True},
            }
        },
    }