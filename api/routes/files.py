"""
文件管理API路由
"""

from typing import Dict, Any, List, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from tools.file_manager import FileManager
from auth.decorators import get_current_user_id
from config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 全局文件管理器实例
file_manager = FileManager()


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    success: bool
    file_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FileListResponse(BaseModel):
    """文件列表响应"""
    success: bool
    files: List[Dict[str, Any]] = []
    total: int = 0
    error: Optional[str] = None


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    """
    上传文件
    """
    try:
        # 读取文件内容
        content = await file.read()

        # 保存文件
        result = await file_manager.save_uploaded_file(
            file_content=content,
            filename=file.filename,
            content_type=file.content_type,
            user_id=user_id,
        )

        if result["success"]:
            # 添加描述到元数据
            if description:
                # TODO: 更新数据库中的文件信息
                pass

            return FileUploadResponse(
                success=True,
                file_info=result,
            )
        else:
            return FileUploadResponse(
                success=False,
                error=result["error"],
            )

    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        return FileUploadResponse(
            success=False,
            error=str(e),
        )


@router.get("/list", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    file_type: Optional[str] = Query(None, description="文件类型过滤"),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取文件列表
    """
    try:
        # 获取文件列表
        files = file_manager.list_files(user_id=user_id, filter_ext=[file_type] if file_type else None)

        # 分页
        total = len(files)
        start = (page - 1) * size
        end = start + size
        paginated_files = files[start:end]

        return FileListResponse(
            success=True,
            files=paginated_files,
            total=total,
        )

    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        return FileListResponse(
            success=False,
            error=str(e),
        )


@router.get("/{file_id}")
async def get_file_info(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    获取文件信息
    """
    try:
        # TODO: 从数据库获取文件信息
        # 这里简化实现，使用file_path作为file_id
        file_info = file_manager.get_file_info(file_id)

        if file_info:
            return {
                "success": True,
                "file_info": file_info,
            }
        else:
            return {
                "success": False,
                "error": "文件不存在",
            }

    except Exception as e:
        logger.error(f"获取文件信息失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    下载文件
    """
    try:
        # 获取文件信息
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")

        # 安全检查
        file_path = file_info["file_path"]
        if not file_path.startswith(file_manager.upload_dir):
            raise HTTPException(status_code=403, detail="无权限访问此文件")

        # 返回文件
        return FileResponse(
            path=file_path,
            filename=file_info["filename"],
            media_type=file_info.get("mime_type", "application/octet-stream"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    删除文件
    """
    try:
        # 删除文件
        result = file_manager.delete_file(file_id)

        if result["success"]:
            return {
                "success": True,
                "message": "文件删除成功",
            }
        else:
            return {
                "success": False,
                "error": result["error"],
            }

    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/{file_id}/extract-text")
async def extract_text_from_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    从文件中提取文本
    """
    try:
        # 获取文件信息
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            return {
                "success": False,
                "error": "文件不存在",
            }

        # 提取文本
        text = await file_manager.extract_text_from_file(file_info["file_path"])

        if text is not None:
            return {
                "success": True,
                "text": text,
                "file_info": file_info,
            }
        else:
            return {
                "success": False,
                "error": "无法从文件中提取文本",
            }

    except Exception as e:
        logger.error(f"提取文本失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/supported-types")
async def get_supported_file_types():
    """
    获取支持的文件类型
    """
    return {
        "success": True,
        "supported_types": [
            {
                "extension": "txt",
                "mime_type": "text/plain",
                "description": "纯文本文件",
            },
            {
                "extension": "md",
                "mime_type": "text/markdown",
                "description": "Markdown文件",
            },
            {
                "extension": "pdf",
                "mime_type": "application/pdf",
                "description": "PDF文档",
            },
            {
                "extension": "docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "description": "Word文档",
            },
            {
                "extension": "xlsx",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "description": "Excel表格",
            },
            {
                "extension": "pptx",
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "description": "PowerPoint演示文稿",
            },
            {
                "extension": "json",
                "mime_type": "application/json",
                "description": "JSON文件",
            },
            {
                "extension": "xml",
                "mime_type": "application/xml",
                "description": "XML文件",
            },
            {
                "extension": "csv",
                "mime_type": "text/csv",
                "description": "CSV文件",
            },
            {
                "extension": "py",
                "mime_type": "text/x-python",
                "description": "Python文件",
            },
            {
                "extension": "js",
                "mime_type": "text/javascript",
                "description": "JavaScript文件",
            },
            {
                "extension": "html",
                "mime_type": "text/html",
                "description": "HTML文件",
            },
        ],
    }


@router.post("/batch-upload")
async def batch_upload_files(
    files: List[UploadFile] = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    批量上传文件
    """
    try:
        results = []

        for file in files:
            # 读取文件内容
            content = await file.read()

            # 保存文件
            result = await file_manager.save_uploaded_file(
                file_content=content,
                filename=file.filename,
                content_type=file.content_type,
                user_id=user_id,
            )

            results.append({
                "filename": file.filename,
                "success": result["success"],
                "error": result.get("error"),
                "file_info": result if result["success"] else None,
            })

        # 统计结果
        success_count = sum(1 for r in results if r["success"])

        return {
            "success": True,
            "results": results,
            "summary": {
                "total": len(files),
                "success": success_count,
                "failed": len(files) - success_count,
            },
        }

    except Exception as e:
        logger.error(f"批量上传失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }