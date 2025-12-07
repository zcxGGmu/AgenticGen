"""
高级语义搜索引擎
基于向量嵌入和相似度的智能文档检索
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from dataclasses import dataclass
from datetime import datetime
import json

from knowledge.vector_store import VectorStore
from knowledge.document_processor import DocumentProcessor
from ai_models.model_manager import ModelManager
from cache.multi_level_cache import MultiLevelCache

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]
    chunk_id: str
    doc_id: str


@dataclass
class SearchQuery:
    """搜索查询"""
    text: str
    filters: Dict[str, Any] = None
    limit: int = 10
    min_score: float = 0.5
    rerank: bool = True


class SemanticSearchEngine:
    """语义搜索引擎"""

    def __init__(self):
        self.vector_store = VectorStore()
        self.doc_processor = DocumentProcessor()
        self.model_manager = ModelManager()
        self.cache = MultiLevelCache()

        # 搜索配置
        self.embedding_model = "text-embedding-3-large"
        self.rerank_model = "gpt-4"  # 用于重排序
        self.max_chunks_per_doc = 50
        self.similarity_threshold = 0.7

        # 预处理缓存
        self.embedding_cache = {}
        self.document_cache = {}

    async def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        索引文档到语义搜索系统
        """
        try:
            logger.info(f"Indexing document {doc_id}")

            # 检查是否已索引
            if await self._is_document_indexed(doc_id):
                await self._remove_document(doc_id)

            # 处理文档
            chunks = await self._process_document(content, metadata or {})

            # 生成嵌入向量
            embeddings = await self._generate_embeddings([c["text"] for c in chunks])

            # 存储到向量数据库
            vectors = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                vector_data = {
                    "id": f"{doc_id}_chunk_{i}",
                    "text": chunk["text"],
                    "embedding": embedding.tolist(),
                    "metadata": {
                        **chunk["metadata"],
                        "doc_id": doc_id,
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    }
                }
                vectors.append(vector_data)

            success = await self.vector_store.add_vectors(vectors)

            if success:
                # 缓存文档信息
                await self.cache.set(
                    f"doc_index:{doc_id}",
                    {
                        "indexed_at": datetime.now().isoformat(),
                        "chunk_count": len(chunks),
                        "metadata": metadata or {}
                    }
                )
                logger.info(f"Successfully indexed {len(chunks)} chunks for document {doc_id}")
            else:
                logger.error(f"Failed to index document {doc_id}")

            return success

        except Exception as e:
            logger.error(f"Error indexing document {doc_id}: {str(e)}")
            return False

    async def search(
        self,
        query: Union[str, SearchQuery]
    ) -> List[SearchResult]:
        """
        执行语义搜索
        """
        try:
            # 标准化查询
            if isinstance(query, str):
                search_query = SearchQuery(text=query)
            else:
                search_query = query

            logger.info(f"Searching for: {search_query.text[:100]}...")

            # 生成查询嵌入
            query_embedding = await self._generate_query_embedding(search_query.text)

            # 执行向量搜索
            vector_results = await self.vector_store.search(
                query_embedding,
                limit=search_query.limit * 2,  # 获取更多结果用于重排序
                filters=search_query.filters
            )

            # 转换为搜索结果
            results = []
            for result in vector_results:
                if result["score"] < search_query.min_score:
                    continue

                search_result = SearchResult(
                    content=result["text"],
                    source=result["metadata"].get("source", "unknown"),
                    score=result["score"],
                    metadata=result["metadata"],
                    chunk_id=result["id"],
                    doc_id=result["metadata"].get("doc_id")
                )
                results.append(search_result)

            # 重排序（如果启用）
            if search_query.rerank and len(results) > 1:
                results = await self._rerank_results(
                    search_query.text,
                    results
                )

            # 应用文档限制
            results = self._limit_chunks_per_doc(results)

            # 限制最终结果数量
            results = results[:search_query.limit]

            logger.info(f"Found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return []

    async def hybrid_search(
        self,
        query: str,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        混合搜索（语义 + 关键词）
        """
        try:
            # 语义搜索
            semantic_results = await self.search(query, limit=limit)

            # 关键词搜索（使用文本匹配）
            keyword_results = await self._keyword_search(query, limit=limit)

            # 合并和重新评分
            combined_results = self._combine_search_results(
                semantic_results,
                keyword_results,
                semantic_weight,
                keyword_weight
            )

            # 限制结果数量
            return combined_results[:limit]

        except Exception as e:
            logger.error(f"Hybrid search error: {str(e)}")
            return await self.search(query, limit=limit)

    async def _process_document(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        处理文档，分割为块
        """
        # 使用文档处理器
        chunks = await self.doc_processor.chunk_text(content)

        processed_chunks = []
        for i, chunk in enumerate(chunks):
            processed_chunks.append({
                "text": chunk,
                "metadata": {
                    **metadata,
                    "chunk_length": len(chunk),
                    "chunk_position": i
                }
            })

        return processed_chunks

    async def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        生成文本嵌入向量
        """
        # 检查缓存
        cached_embeddings = []
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cache_key = f"embedding:{hash(text)}"
            cached = await self.cache.get(cache_key)
            if cached:
                cached_embeddings.append((i, np.array(cached)))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # 生成未缓存的嵌入
        if uncached_texts:
            try:
                # 使用OpenAI嵌入模型
                response = await self.model_manager.generate_embeddings(
                    uncached_texts,
                    model=self.embedding_model
                )

                # 缓存新嵌入
                for text, embedding, idx in zip(uncached_texts, response, uncached_indices):
                    cache_key = f"embedding:{hash(text)}"
                    await self.cache.set(cache_key, embedding.tolist())
                    cached_embeddings.append((idx, embedding))

            except Exception as e:
                logger.error(f"Failed to generate embeddings: {str(e)}")
                # 返回零向量作为后备
                zero_embedding = np.zeros(1536)  # OpenAI嵌入维度
                for idx in uncached_indices:
                    cached_embeddings.append((idx, zero_embedding))

        # 按原始顺序排列嵌入
        embeddings = np.zeros((len(texts), 1536))
        for idx, embedding in cached_embeddings:
            embeddings[idx] = embedding

        return embeddings

    async def _generate_query_embedding(self, query: str) -> np.ndarray:
        """
        生成查询嵌入向量
        """
        embeddings = await self._generate_embeddings([query])
        return embeddings[0]

    async def _rerank_results(
        self,
        query: str,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        使用语言模型重排序搜索结果
        """
        try:
            # 构建重排序提示
            prompt = f"""
            Please rank the following search results by relevance to the query.

            Query: {query}

            Results:
            {json.dumps([
                {
                    "content": r.content[:200] + "...",
                    "source": r.source,
                    "score": r.score
                }
                for r in results[:10]  # 限制重排序数量
            ], indent=2)}

            Return only the indices of the top 5 results in order, separated by commas.
            """

            # 获取重排序
            response = await self.model_manager.chat_completion(
                model_name=self.rerank_model,
                messages=[
                    {"role": "system", "content": "You are a search result reranking assistant."},
                    {"role": "user", "content": prompt}
                ],
                stream=False
            )

            # 解析响应
            try:
                ranks = [int(x.strip()) for x in response["choices"][0]["message"]["content"].split(",")]
                ranked_results = []
                for rank in ranks[:len(results)]:
                    if rank < len(results):
                        ranked_results.append(results[rank])
                return ranked_results
            except:
                # 解析失败，返回原始结果
                return results

        except Exception as e:
            logger.error(f"Reranking failed: {str(e)}")
            return results

    async def _keyword_search(self, query: str, limit: int) -> List[SearchResult]:
        """
        关键词搜索
        """
        # TODO: 实现基于Elasticsearch或类似的关键词搜索
        # 这里返回空列表，实际应用中应该实现关键词匹配
        return []

    def _combine_search_results(
        self,
        semantic_results: List[SearchResult],
        keyword_results: List[SearchResult],
        semantic_weight: float,
        keyword_weight: float
    ) -> List[SearchResult]:
        """
        合并语义搜索和关键词搜索结果
        """
        # 合并结果，避免重复
        seen_ids = set()
        combined_results = []

        # 添加语义搜索结果
        for result in semantic_results:
            if result.chunk_id not in seen_ids:
                result.score *= semantic_weight
                combined_results.append(result)
                seen_ids.add(result.chunk_id)

        # 添加关键词搜索结果
        for result in keyword_results:
            if result.chunk_id not in seen_ids:
                result.score *= keyword_weight
                combined_results.append(result)
                seen_ids.add(result.chunk_id)
            else:
                # 合并重复结果的分数
                for existing in combined_results:
                    if existing.chunk_id == result.chunk_id:
                        existing.score += result.score
                        break

        # 按分数排序
        combined_results.sort(key=lambda x: x.score, reverse=True)

        return combined_results

    def _limit_chunks_per_doc(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        限制每个文档的块数量
        """
        doc_chunk_counts = {}
        filtered_results = []

        for result in results:
            doc_id = result.doc_id
            chunk_count = doc_chunk_counts.get(doc_id, 0)

            if chunk_count < self.max_chunks_per_doc:
                filtered_results.append(result)
                doc_chunk_counts[doc_id] = chunk_count + 1

        return filtered_results

    async def _is_document_indexed(self, doc_id: str) -> bool:
        """
        检查文档是否已索引
        """
        cached = await self.cache.get(f"doc_index:{doc_id}")
        return cached is not None

    async def _remove_document(self, doc_id: str):
        """
        移除文档索引
        """
        try:
            # 从向量存储删除
            await self.vector_store.delete_by_metadata({"doc_id": doc_id})

            # 清除缓存
            await self.cache.delete(f"doc_index:{doc_id}")

            logger.info(f"Removed document {doc_id} from index")

        except Exception as e:
            logger.error(f"Failed to remove document {doc_id}: {str(e)}")

    async def get_document_chunks(self, doc_id: str) -> List[SearchResult]:
        """
        获取文档的所有块
        """
        try:
            # 从向量存储查询
            vectors = await self.vector_store.get_by_metadata({"doc_id": doc_id})

            chunks = []
            for vector in vectors:
                chunk = SearchResult(
                    content=vector["text"],
                    source=vector["metadata"].get("source"),
                    score=1.0,  # 完全匹配
                    metadata=vector["metadata"],
                    chunk_id=vector["id"],
                    doc_id=doc_id
                )
                chunks.append(chunk)

            # 按块索引排序
            chunks.sort(key=lambda x: x.metadata.get("chunk_index", 0))

            return chunks

        except Exception as e:
            logger.error(f"Failed to get chunks for document {doc_id}: {str(e)}")
            return []

    async def update_document_metadata(
        self,
        doc_id: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        更新文档元数据
        """
        try:
            # 获取所有块
            chunks = await self.get_document_chunks(doc_id)

            if not chunks:
                return False

            # 更新每个块的元数据
            for chunk in chunks:
                new_metadata = {**chunk.metadata, **metadata}
                await self.vector_store.update_metadata(
                    chunk.chunk_id,
                    new_metadata
                )

            # 更新缓存
            cached = await self.cache.get(f"doc_index:{doc_id}")
            if cached:
                cached["metadata"] = {**cached.get("metadata", {}), **metadata}
                await self.cache.set(f"doc_index:{doc_id}", cached)

            return True

        except Exception as e:
            logger.error(f"Failed to update metadata for document {doc_id}: {str(e)}")
            return False


# 全局实例
semantic_search = SemanticSearchEngine()