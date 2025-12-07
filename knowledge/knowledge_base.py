"""
知识库核心

提供知识库的创建、管理和查询功能。
"""

import hashlib
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional

import numpy as np
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import (
    KnowledgeBase as KBModel,
    KnowledgeDocument,
    KnowledgeChunk,
)
from knowledge.document_processor import DocumentProcessor, DocumentChunker
from knowledge.embeddings import EmbeddingManager
from knowledge.retrieval import KnowledgeRetrieval, RetrievalConfig
from config.logging import get_logger

logger = get_logger(__name__)


class KnowledgeBase:
    """知识库类"""

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        embedding_model: Optional[str] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        max_tokens: int = 8192,
    ):
        self.name = name
        self.description = description or f"知识库: {name}"
        self.user_id = user_id
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_tokens = max_tokens

        # 初始化组件
        self.document_processor = DocumentProcessor(
            chunker=DocumentChunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                min_chunk_size=100,
            )
        )
        self.embedding_manager = EmbeddingManager()
        self.retrieval = KnowledgeRetrieval(
            embedding_manager=self.embedding_manager,
            config=RetrievalConfig(
                top_k=5,
                similarity_threshold=0.7,
                rerank=True,
            )
        )

        # 数据库ID
        self.id = None

    async def create(self, db: Session) -> Dict[str, Any]:
        """
        在数据库中创建知识库

        Args:
            db: 数据库会话

        Returns:
            创建结果
        """
        try:
            # 检查是否已存在
            existing = db.query(KBModel).filter(
                KBModel.name == self.name,
                KBModel.user_id == self.user_id,
            ).first()

            if existing:
                self.id = existing.id
                return {
                    "success": False,
                    "error": f"知识库 '{self.name}' 已存在",
                    "id": existing.id,
                }

            # 创建新知识库
            kb = KBModel(
                name=self.name,
                description=self.description,
                user_id=self.user_id,
                embedding_model=self.embedding_model,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

            db.add(kb)
            db.commit()
            db.refresh(kb)

            self.id = kb.id

            logger.info(f"创建知识库成功: {self.name} (ID: {self.id})")
            return {
                "success": True,
                "id": self.id,
                "message": "知识库创建成功",
            }

        except Exception as e:
            db.rollback()
            logger.error(f"创建知识库失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    async def add_document(
        self,
        file_path: str,
        db: Session,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        添加文档到知识库

        Args:
            file_path: 文件路径
            db: 数据库会话
            metadata: 文档元数据

        Returns:
            添加结果
        """
        if not self.id:
            return {
                "success": False,
                "error": "知识库未初始化",
            }

        try:
            # 处理文档
            from pathlib import Path
            path = Path(file_path)

            # 更新元数据
            if not metadata:
                metadata = {}

            metadata.update({
                "filename": path.name,
                "file_path": str(path),
                "file_size": path.stat().st_size,
                "added_at": datetime.utcnow().isoformat(),
            })

            process_result = await self.document_processor.process_document(
                file_path,
                metadata
            )

            if not process_result["success"]:
                return process_result

            # 创建文档记录
            doc = KnowledgeDocument(
                knowledge_base_id=self.id,
                filename=path.name,
                file_path=str(path),
                file_size=path.stat().st_size,
                file_type=path.suffix.lower().lstrip('.'),
                content_hash=hashlib.md5(process_result["text"].encode()).hexdigest(),
                chunk_count=len(process_result["chunks"]),
                processing_status="processing",
            )

            db.add(doc)
            db.commit()
            db.refresh(doc)

            # 处理文档块
            chunks_added = await self._process_chunks(
                doc.id,
                process_result["chunks"],
                db
            )

            # 更新文档状态
            doc.processing_status = "completed"
            db.commit()

            # 更新知识库统计
            self._update_statistics(db)

            logger.info(f"添加文档成功: {file_path}, {chunks_added} 个块")
            return {
                "success": True,
                "document_id": doc.id,
                "chunk_count": chunks_added,
                "message": "文档添加成功",
            }

        except Exception as e:
            db.rollback()
            logger.error(f"添加文档失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _process_chunks(
        self,
        document_id: int,
        chunks: List[Dict[str, Any]],
        db: Session,
    ) -> int:
        """处理文档块"""
        try:
            # 提取文本
            texts = [chunk["text"] for chunk in chunks]

            # 生成嵌入
            embeddings = await self.embedding_manager.embed_texts(texts)
            if isinstance(embeddings, np.ndarray) and embeddings.ndim == 1:
                embeddings = embeddings.reshape(1, -1)

            # 保存到数据库
            for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
                chunk = KnowledgeChunk(
                    document_id=document_id,
                    chunk_index=i,
                    content=chunk_data["text"],
                    token_count=self.embedding_manager.count_tokens(chunk_data["text"]),
                    embedding=embedding.tobytes(),
                    metadata=chunk_data.get("metadata", {}),
                )

                db.add(chunk)

            db.commit()

            # 添加到检索器
            await self.retrieval.add_documents([
                {
                    "id": f"{document_id}_{i}",
                    "text": chunk["text"],
                    "metadata": {
                        "document_id": document_id,
                        "chunk_index": i,
                        **chunk.get("metadata", {}),
                    },
                }
                for i, chunk in enumerate(chunks)
            ])

            return len(chunks)

        except Exception as e:
            db.rollback()
            logger.error(f"处理文档块失败: {str(e)}")
            raise

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        搜索知识库

        Args:
            query: 查询
            top_k: 返回数量
            filters: 过滤条件
            db: 数据库会话

        Returns:
            搜索结果
        """
        try:
            # 添加知识库过滤
            if not filters:
                filters = {}

            filters["knowledge_base_id"] = self.id

            # 执行搜索
            results = await self.retrieval.search(query, top_k=top_k, filters=filters)

            # 构建上下文
            context = await self.retrieval.get_context(results)

            return {
                "success": True,
                "query": query,
                "results": [result.to_dict() for result in results],
                "context": context,
                "result_count": len(results),
            }

        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "context": "",
            }

    async def delete_document(
        self,
        document_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """
        删除文档

        Args:
            document_id: 文档ID
            db: 数据库会话

        Returns:
            删除结果
        """
        try:
            # 获取文档
            doc = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.knowledge_base_id == self.id,
            ).first()

            if not doc:
                return {
                    "success": False,
                    "error": "文档不存在",
                }

            # 删除文档块
            db.query(KnowledgeChunk).filter(
                KnowledgeChunk.document_id == document_id
            ).delete()

            # 删除文档
            db.delete(doc)
            db.commit()

            # 从检索器中移除
            self._remove_from_retrieval(document_id)

            # 更新统计
            self._update_statistics(db)

            logger.info(f"删除文档成功: {document_id}")
            return {
                "success": True,
                "message": "文档删除成功",
            }

        except Exception as e:
            db.rollback()
            logger.error(f"删除文档失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    def _remove_from_retrieval(self, document_id: int):
        """从检索器中移除文档"""
        # 这里需要实现从检索器中移除特定文档的逻辑
        # 简化实现：重新构建检索器
        pass

    def _update_statistics(self, db: Session):
        """更新知识库统计"""
        try:
            # 统计文档数
            doc_count = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.knowledge_base_id == self.id
            ).count()

            # 统计块数
            chunk_count = db.query(KnowledgeChunk).join(KnowledgeDocument).filter(
                KnowledgeDocument.knowledge_base_id == self.id
            ).count()

            # 更新知识库记录
            kb = db.query(KBModel).filter(KBModel.id == self.id).first()
            if kb:
                kb.total_documents = doc_count
                kb.total_chunks = chunk_count
                db.commit()

        except Exception as e:
            logger.error(f"更新统计失败: {str(e)}")

    async def get_statistics(self, db: Session) -> Dict[str, Any]:
        """
        获取知识库统计信息

        Args:
            db: 数据库会话

        Returns:
            统计信息
        """
        try:
            # 获取知识库信息
            kb = db.query(KBModel).filter(KBModel.id == self.id).first()
            if not kb:
                return {
                    "success": False,
                    "error": "知识库不存在",
                }

            # 获取文档列表
            documents = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.knowledge_base_id == self.id
            ).all()

            # 构建统计信息
            stats = {
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "user_id": kb.user_id,
                "total_documents": kb.total_documents,
                "total_chunks": kb.total_chunks,
                "embedding_model": kb.embedding_model,
                "chunk_size": kb.chunk_size,
                "chunk_overlap": kb.chunk_overlap,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
                "documents": [
                    {
                        "id": doc.id,
                        "filename": doc.filename,
                        "file_type": doc.file_type,
                        "file_size": doc.file_size,
                        "chunk_count": doc.chunk_count,
                        "processing_status": doc.processing_status,
                        "created_at": doc.created_at.isoformat(),
                    }
                    for doc in documents
                ],
            }

            # 获取检索统计
            stats["retrieval_stats"] = self.retrieval.get_stats()

            return {
                "success": True,
                "statistics": stats,
            }

        except Exception as e:
            logger.error(f"获取统计失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    async def update_config(
        self,
        db: Session,
        **kwargs
    ) -> Dict[str, Any]:
        """
        更新知识库配置

        Args:
            db: 数据库会话
            **kwargs: 配置参数

        Returns:
            更新结果
        """
        try:
            # 获取知识库记录
            kb = db.query(KBModel).filter(KBModel.id == self.id).first()
            if not kb:
                return {
                    "success": False,
                    "error": "知识库不存在",
                }

            # 更新配置
            allowed_fields = [
                "name", "description", "embedding_model",
                "chunk_size", "chunk_overlap"
            ]

            for field, value in kwargs.items():
                if field in allowed_fields and hasattr(kb, field):
                    setattr(kb, field, value)
                    setattr(self, field, value)

            db.commit()

            # 更新文档处理器配置
            if "chunk_size" in kwargs or "chunk_overlap" in kwargs:
                self.document_processor.update_chunking_strategy(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )

            logger.info(f"更新知识库配置成功: {self.id}")
            return {
                "success": True,
                "message": "配置更新成功",
            }

        except Exception as e:
            db.rollback()
            logger.error(f"更新配置失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    @classmethod
    async def load(
        cls,
        kb_id: int,
        db: Session,
    ) -> Optional["KnowledgeBase"]:
        """
        加载现有知识库

        Args:
            kb_id: 知识库ID
            db: 数据库会话

        Returns:
            知识库实例
        """
        try:
            # 获取知识库记录
            kb = db.query(KBModel).filter(KBModel.id == kb_id).first()
            if not kb:
                return None

            # 创建实例
            instance = cls(
                name=kb.name,
                description=kb.description,
                user_id=kb.user_id,
                embedding_model=kb.embedding_model,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
            )
            instance.id = kb.id

            # 加载文档到检索器
            await instance._load_documents_to_retrieval(db)

            return instance

        except Exception as e:
            logger.error(f"加载知识库失败: {str(e)}")
            return None

    async def _load_documents_to_retrieval(self, db: Session):
        """加载文档到检索器"""
        try:
            # 获取所有文档块
            chunks = db.query(KnowledgeChunk).join(KnowledgeDocument).filter(
                KnowledgeDocument.knowledge_base_id == self.id,
                KnowledgeDocument.processing_status == "completed",
            ).all()

            # 转换为检索器格式
            documents = []
            for chunk in chunks:
                # 解析嵌入
                import numpy as np
                embedding = np.frombuffer(chunk.embedding, dtype=np.float32)

                documents.append({
                    "id": f"{chunk.document_id}_{chunk.chunk_index}",
                    "text": chunk.content,
                    "metadata": {
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                        "token_count": chunk.token_count,
                        **chunk.metadata,
                    },
                })

            # 添加到检索器
            if documents:
                await self.retrieval.add_documents(documents)
                logger.info(f"加载 {len(documents)} 个文档块到检索器")

        except Exception as e:
            logger.error(f"加载文档到检索器失败: {str(e)}")