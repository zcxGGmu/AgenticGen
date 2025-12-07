"""
检索引擎

提供知识检索和相关性排序功能。
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import numpy as np

from knowledge.embeddings import EmbeddingManager
from cache.response_cache import ResponseCache
from config.logging import get_logger

logger = get_logger(__name__)


class SearchResult:
    """搜索结果"""

    def __init__(
        self,
        content: str,
        score: float,
        source: Dict[str, Any],
        chunk_index: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.content = content
        self.score = score
        self.source = source
        self.chunk_index = chunk_index
        self.metadata = metadata or {}
        self.highlighted_text = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "content": self.content,
            "score": self.score,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
            "highlighted_text": self.highlighted_text,
        }


class QueryProcessor:
    """查询处理器"""

    def __init__(self):
        self.stop_words = {
            'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and',
            'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by',
            '的', '是', '在', '和', '与', '或', '但是', '在', '为', '了'
        }

    def process_query(self, query: str) -> str:
        """
        处理查询

        Args:
            query: 原始查询

        Returns:
            处理后的查询
        """
        # 转换为小写
        query = query.lower().strip()

        # 移除标点符号
        import re
        query = re.sub(r'[^\w\s]', '', query)

        # 移除停用词
        words = query.split()
        words = [word for word in words if word not in self.stop_words]

        return ' '.join(words)

    def expand_query(self, query: str, synonyms: Optional[Dict[str, List[str]]] = None) -> List[str]:
        """
        扩展查询

        Args:
            query: 原始查询
            synonyms: 同义词典

        Returns:
            扩展后的查询列表
        """
        if not synonyms:
            return [query]

        words = query.split()
        expanded_queries = [query]

        # 为每个词找同义词并生成新查询
        for word in words:
            if word in synonyms:
                for synonym in synonyms[word]:
                    new_query = query.replace(word, synonym)
                    if new_query not in expanded_queries:
                        expanded_queries.append(new_query)

        return expanded_queries


class RetrievalConfig:
    """检索配置"""

    def __init__(
        self,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
        rerank: bool = True,
        include_metadata: bool = True,
        max_context_length: int = 4000,
    ):
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.rerank = rerank
        self.include_metadata = include_metadata
        self.max_context_length = max_context_length


class KnowledgeRetrieval:
    """知识检索器"""

    def __init__(
        self,
        embedding_manager: Optional[EmbeddingManager] = None,
        config: Optional[RetrievalConfig] = None,
    ):
        self.embedding_manager = embedding_manager or EmbeddingManager()
        self.config = config or RetrievalConfig()
        self.query_processor = QueryProcessor()
        self.cache = ResponseCache()

        # 存储的知识库数据
        self.documents = []  # [(content, embedding, metadata), ...]
        self.document_index = {}  # id -> index

    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """
        添加文档到知识库

        Args:
            documents: 文档列表，每个文档包含 text 和 metadata
            batch_size: 批处理大小

        Returns:
            添加的文档数量
        """
        added_count = 0

        # 批量处理
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            # 提取文本
            texts = [doc.get("text", "") for doc in batch]
            if not all(texts):
                logger.warning("部分文档为空")
                continue

            # 生成嵌入
            try:
                embeddings = await self.embedding_manager.embed_texts(texts)
                if isinstance(embeddings, np.ndarray) and embeddings.ndim == 1:
                    embeddings = embeddings.reshape(1, -1)

                # 添加到知识库
                for j, (doc, text, embedding) in enumerate(zip(batch, texts, embeddings)):
                    doc_id = doc.get("id", f"doc_{len(self.documents)}")

                    self.documents.append({
                        "id": doc_id,
                        "text": text,
                        "embedding": embedding,
                        "metadata": doc.get("metadata", {}),
                    })

                    self.document_index[doc_id] = len(self.documents) - 1
                    added_count += 1

                logger.debug(f"批处理完成: {len(batch)} 个文档")

            except Exception as e:
                logger.error(f"批处理失败: {str(e)}")
                continue

        logger.info(f"添加文档完成: {added_count} 个文档")
        return added_count

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        rerank: Optional[bool] = None,
    ) -> List[SearchResult]:
        """
        搜索知识

        Args:
            query: 查询
            top_k: 返回数量
            filters: 过滤条件
            rerank: 是否重排序

        Returns:
            搜索结果
        """
        # 检查缓存
        cache_key = f"search:{hash(query)}:{top_k or self.config.top_k}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.debug(f"搜索缓存命中: {query[:50]}...")
            return [SearchResult(**r) for r in cached_result]

        # 处理查询
        processed_query = self.query_processor.process_query(query)

        # 生成查询嵌入
        query_embedding = await self.embedding_manager.embed_single_text(processed_query)

        # 搜索相似文档
        candidates = self._find_similar_documents(query_embedding, filters)

        # 应用阈值过滤
        filtered = [
            (doc, score) for doc, score in candidates
            if score >= self.config.similarity_threshold
        ]

        # 排序并限制数量
        filtered.sort(key=lambda x: x[1], reverse=True)
        target_count = top_k or self.config.top_k
        selected = filtered[:target_count]

        # 重排序（如果需要）
        if rerank or (rerank is None and self.config.rerank):
            selected = await self._rerank_results(query, selected)

        # 转换为SearchResult
        results = []
        for doc, score in selected:
            result = SearchResult(
                content=doc["text"],
                score=score,
                source=doc["metadata"],
                chunk_index=doc.get("chunk_index"),
                metadata=doc["metadata"],
            )
            results.append(result)

        # 缓存结果
        cache_data = [r.to_dict() for r in results]
        await self.cache.set(cache_key, cache_data, expire=300)  # 5分钟缓存

        logger.info(f"搜索完成: {query}, 找到 {len(results)} 个结果")
        return results

    def _find_similar_documents(
        self,
        query_embedding: np.ndarray,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Dict, float]]:
        """查找相似文档"""
        candidates = []

        for doc in self.documents:
            # 应用过滤条件
            if filters:
                if not self._apply_filters(doc["metadata"], filters):
                    continue

            # 计算相似度
            similarity = self.embedding_manager.compute_similarity(
                query_embedding,
                doc["embedding"]
            )

            candidates.append((doc, similarity))

        return candidates

    def _apply_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """应用过滤条件"""
        for key, value in filters.items():
            if key not in metadata:
                return False

            if isinstance(value, list):
                if metadata[key] not in value:
                    return False
            elif isinstance(value, dict):
                if value.get("min") is not None and metadata[key] < value["min"]:
                    return False
                if value.get("max") is not None and metadata[key] > value["max"]:
                    return False
            else:
                if metadata[key] != value:
                    return False

        return True

    async def _rerank_results(
        self,
        query: str,
        candidates: List[Tuple[Dict, float]]
    ) -> List[Tuple[Dict, float]]:
        """重排序结果"""
        # 简单的重排序：基于关键词匹配
        query_words = set(query.lower().split())

        reranked = []
        for doc, initial_score in candidates:
            text = doc["text"].lower()

            # 计算关键词匹配度
            word_matches = sum(1 for word in query_words if word in text)
            word_score = word_matches / len(query_words)

            # 组合分数
            final_score = 0.7 * initial_score + 0.3 * word_score

            reranked.append((doc, final_score))

        # 排序
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    async def get_context(
        self,
        results: List[SearchResult],
        max_length: Optional[int] = None,
        separator: str = "\n\n---\n\n",
    ) -> str:
        """
        构建上下文

        Args:
            results: 搜索结果
            max_length: 最大长度
            separator: 分隔符

        Returns:
            上下文文本
        """
        if not results:
            return ""

        max_length = max_length or self.config.max_context_length
        context_parts = []
        current_length = 0

        for result in results:
            text = result.content

            # 添加来源信息
            if self.config.include_metadata and result.source:
                source_info = f"\n来源: {result.source.get('title', '未知')}"
                text += source_info

            # 检查长度
            if current_length + len(text) > max_length:
                # 截断最后一个结果
                remaining_length = max_length - current_length - len(separator)
                if remaining_length > 50:  # 至少保留50个字符
                    truncated_text = text[:remaining_length] + "..."
                    context_parts.append(truncated_text)
                break

            context_parts.append(text)
            current_length += len(text)

        return separator.join(context_parts)

    async def hybrid_search(
        self,
        query: str,
        keyword_weight: float = 0.3,
        top_k: Optional[int] = None,
    ) -> List[SearchResult]:
        """
        混合搜索（向量 + 关键词）

        Args:
            query: 查询
            keyword_weight: 关键词权重
            top_k: 返回数量

        Returns:
            搜索结果
        """
        # 向量搜索
        vector_results = await self.search(query, top_k=top_k * 2)

        # 关键词搜索
        keyword_results = self._keyword_search(query, top_k=top_k * 2)

        # 合并结果
        combined = self._combine_search_results(
            vector_results,
            keyword_results,
            keyword_weight
        )

        # 限制数量
        target_count = top_k or self.config.top_k
        return combined[:target_count]

    def _keyword_search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """关键词搜索"""
        query_words = set(query.lower().split())
        results = []

        for doc in self.documents:
            text = doc["text"].lower()

            # 计算关键词匹配分数
            word_matches = sum(1 for word in query_words if word in text)
            if word_matches > 0:
                score = word_matches / len(query_words)
                result = SearchResult(
                    content=doc["text"],
                    score=score,
                    source=doc["metadata"],
                    metadata=doc["metadata"],
                )
                results.append(result)

        # 排序并限制数量
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _combine_search_results(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        keyword_weight: float,
    ) -> List[SearchResult]:
        """合并搜索结果"""
        combined = {}

        # 处理向量搜索结果
        for result in vector_results:
            doc_id = result.source.get("id", result.content[:50])
            combined[doc_id] = {
                "result": result,
                "vector_score": result.score,
                "keyword_score": 0.0,
            }

        # 处理关键词搜索结果
        for result in keyword_results:
            doc_id = result.source.get("id", result.content[:50])
            if doc_id in combined:
                combined[doc_id]["keyword_score"] = result.score
            else:
                combined[doc_id] = {
                    "result": result,
                    "vector_score": 0.0,
                    "keyword_score": result.score,
                }

        # 计算组合分数并排序
        final_results = []
        for doc_id, data in combined.items():
            combined_score = (
                (1 - keyword_weight) * data["vector_score"] +
                keyword_weight * data["keyword_score"]
            )
            data["result"].score = combined_score
            final_results.append(data["result"])

        final_results.sort(key=lambda x: x.score, reverse=True)
        return final_results

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "document_count": len(self.documents),
            "embedding_dimension": self.embedding_manager.get_dimension(),
            "config": {
                "top_k": self.config.top_k,
                "similarity_threshold": self.config.similarity_threshold,
                "rerank": self.config.rerank,
            },
        }

    def clear(self):
        """清空知识库"""
        self.documents.clear()
        self.document_index.clear()
        logger.info("知识库已清空")