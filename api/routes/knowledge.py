"""
知识库API路由
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from knowledge.knowledge_base import KnowledgeBase
from db.database import get_db
from auth.decorators import get_current_user_id
from config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 存储知识库实例
knowledge_bases: Dict[str, KnowledgeBase] = {}


class KnowledgeBaseRequest(BaseModel):
    """知识库请求模型"""
    name: str = Field(..., description="知识库名称")
    description: Optional[str] = Field(None, description="知识库描述")
    embedding_model: Optional[str] = Field(None, description="嵌入模型")
    chunk_size: Optional[int] = Field(1000, description="分块大小")
    chunk_overlap: Optional[int] = Field(200, description="分块重叠")


class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str = Field(..., description="搜索查询")
    top_k: Optional[int] = Field(5, description="返回数量")
    filters: Optional[Dict[str, Any]] = Field(None, description="过滤条件")


@router.post("/create", response_model=Dict[str, Any])
async def create_knowledge_base(
    request: KnowledgeBaseRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    创建知识库
    """
    try:
        # 创建知识库实例
        kb = KnowledgeBase(
            name=request.name,
            description=request.description,
            user_id=user_id,
            embedding_model=request.embedding_model,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        # 保存到数据库
        result = await kb.create(db)

        if result["success"]:
            # 存储到内存
            knowledge_bases[str(kb.id)] = kb

            return {
                "success": True,
                "knowledge_base_id": kb.id,
                "message": "知识库创建成功",
            }
        else:
            return result

    except Exception as e:
        logger.error(f"创建知识库失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/list")
async def list_knowledge_bases(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取用户的知识库列表
    """
    try:
        from db.models import KnowledgeBase as KBModel

        # 查询知识库列表
        kbs = db.query(KBModel).filter(
            KBModel.user_id == user_id,
            KBModel.is_active == True,
        ).all()

        # 转换为响应格式
        kb_list = []
        for kb in kbs:
            kb_list.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "total_documents": kb.total_documents,
                "total_chunks": kb.total_chunks,
                "embedding_model": kb.embedding_model,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            })

        return {
            "success": True,
            "knowledge_bases": kb_list,
            "total": len(kb_list),
        }

    except Exception as e:
        logger.error(f"获取知识库列表失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/{kb_id}")
async def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取知识库详情
    """
    try:
        # 从内存获取或加载
        kb = knowledge_bases.get(str(kb_id))
        if not kb:
            kb = await KnowledgeBase.load(kb_id, db)
            if kb:
                knowledge_bases[str(kb_id)] = kb

        if not kb:
            return {
                "success": False,
                "error": "知识库不存在",
            }

        # 获取统计信息
        stats = await kb.get_statistics(db)

        return stats

    except Exception as e:
        logger.error(f"获取知识库详情失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    删除知识库
    """
    try:
        from db.models import KnowledgeBase as KBModel

        # 查询知识库
        kb = db.query(KBModel).filter(
            KBModel.id == kb_id,
            KBModel.user_id == user_id,
        ).first()

        if not kb:
            return {
                "success": False,
                "error": "知识库不存在",
            }

        # 软删除
        kb.is_active = False
        db.commit()

        # 从内存移除
        if str(kb_id) in knowledge_bases:
            del knowledge_bases[str(kb_id)]

        return {
            "success": True,
            "message": "知识库删除成功",
        }

    except Exception as e:
        db.rollback()
        logger.error(f"删除知识库失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/{kb_id}/documents")
async def add_document(
    kb_id: int,
    file_path: str = Body(..., embed=True),
    metadata: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    添加文档到知识库
    """
    try:
        # 获取知识库
        kb = knowledge_bases.get(str(kb_id))
        if not kb:
            kb = await KnowledgeBase.load(kb_id, db)
            if kb:
                knowledge_bases[str(kb_id)] = kb

        if not kb:
            return {
                "success": False,
                "error": "知识库不存在",
            }

        # 添加文档
        result = await kb.add_document(
            file_path=file_path,
            db=db,
            metadata=metadata,
        )

        return result

    except Exception as e:
        logger.error(f"添加文档失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/{kb_id}/documents/upload")
async def upload_document(
    kb_id: int,
    file_path: str = Body(..., embed=True),
    metadata: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    上传文档到知识库（通过文件路径）
    """
    # 与add_document相同，只是接口名称不同
    return await add_document(kb_id, file_path, metadata, db, user_id)


@router.get("/{kb_id}/search")
async def search_knowledge_base(
    kb_id: int,
    query: str = Query(..., description="搜索查询"),
    top_k: int = Query(5, description="返回数量"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    搜索知识库
    """
    try:
        # 获取知识库
        kb = knowledge_bases.get(str(kb_id))
        if not kb:
            kb = await KnowledgeBase.load(kb_id, db)
            if kb:
                knowledge_bases[str(kb_id)] = kb

        if not kb:
            return {
                "success": False,
                "error": "知识库不存在",
            }

        # 执行搜索
        result = await kb.search(
            query=query,
            top_k=top_k,
            db=db,
        )

        return result

    except Exception as e:
        logger.error(f"搜索知识库失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.post("/{kb_id}/search")
async def search_knowledge_base_post(
    kb_id: int,
    request: SearchRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    搜索知识库（POST方式）
    """
    return await search_knowledge_base(
        kb_id=kb_id,
        query=request.query,
        top_k=request.top_k,
        db=db,
        user_id=user_id,
    )


@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    获取知识库文档列表
    """
    try:
        from db.models import KnowledgeDocument

        # 查询文档列表
        documents = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.knowledge_base_id == kb_id,
        ).offset((page - 1) * size).limit(size).all()

        # 获取总数
        total = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.knowledge_base_id == kb_id,
        ).count()

        # 转换格式
        doc_list = []
        for doc in documents:
            doc_list.append({
                "id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "chunk_count": doc.chunk_count,
                "processing_status": doc.processing_status,
                "created_at": doc.created_at.isoformat(),
            })

        return {
            "success": True,
            "documents": doc_list,
            "total": total,
            "page": page,
            "size": size,
        }

    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    删除文档
    """
    try:
        # 获取知识库
        kb = knowledge_bases.get(str(kb_id))
        if not kb:
            kb = await KnowledgeBase.load(kb_id, db)
            if kb:
                knowledge_bases[str(kb_id)] = kb

        if not kb:
            return {
                "success": False,
                "error": "知识库不存在",
            }

        # 删除文档
        result = await kb.delete_document(doc_id, db)

        return result

    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@router.put("/{kb_id}")
async def update_knowledge_base(
    kb_id: int,
    updates: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    更新知识库配置
    """
    try:
        # 获取知识库
        kb = knowledge_bases.get(str(kb_id))
        if not kb:
            kb = await KnowledgeBase.load(kb_id, db)
            if kb:
                knowledge_bases[str(kb_id)] = kb

        if not kb:
            return {
                "success": False,
                "error": "知识库不存在",
            }

        # 更新配置
        result = await kb.update_config(db, **updates)

        return result

    except Exception as e:
        logger.error(f"更新知识库失败: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }