"""
嵌入管理器

提供文本向量化和相似度计算功能。
"""

import numpy as np
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import openai
import tiktoken

from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class EmbeddingModel:
    """嵌入模型基类"""

    def __init__(self, model_name: str):
        self.model_name = model_name

    async def encode(self, texts: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        将文本编码为向量

        Args:
            texts: 文本或文本列表

        Returns:
            向量或向量列表
        """
        raise NotImplementedError

    def get_dimension(self) -> int:
        """获取向量维度"""
        raise NotImplementedError


class OpenAIEmbedding(EmbeddingModel):
    """OpenAI嵌入模型"""

    def __init__(self, model_name: str = "text-embedding-ada-002"):
        super().__init__(model_name)
        self.client = openai.Client(api_key=settings.openai_api_key)
        self.dimension = 1536  # ada-002 的维度

    async def encode(self, texts: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """编码文本"""
        try:
            is_single = isinstance(texts, str)
            if is_single:
                texts = [texts]

            # 批量处理，避免超过限制
            batch_size = 100
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=batch
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

            embeddings = np.array(all_embeddings)

            if is_single:
                return embeddings[0]
            else:
                return embeddings

        except Exception as e:
            logger.error(f"OpenAI嵌入失败: {str(e)}")
            raise

    def get_dimension(self) -> int:
        return self.dimension


class LocalEmbedding(EmbeddingModel):
    """本地嵌入模型（使用sentence-transformers）"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        super().__init__(model_name)
        self._model = None
        self.dimension = 384  # MiniLM的维度

    @property
    def model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"加载本地嵌入模型: {self.model_name}")
            except ImportError:
                raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")
        return self._model

    async def encode(self, texts: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """编码文本"""
        try:
            is_single = isinstance(texts, str)
            if is_single:
                texts = [texts]

            embeddings = self.model.encode(texts, convert_to_numpy=True)

            if is_single:
                return embeddings[0]
            else:
                return embeddings

        except Exception as e:
            logger.error(f"本地嵌入失败: {str(e)}")
            raise

    def get_dimension(self) -> int:
        return self.dimension


class TokenCounter:
    """Token计数器"""

    def __init__(self, model_name: str = "cl100k_base"):
        self.encoding = tiktoken.get_encoding(model_name)

    def count_tokens(self, text: str) -> int:
        """计算文本的token数量"""
        return len(self.encoding.encode(text))

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """截断文本到指定token数"""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)


class EmbeddingCache:
    """嵌入缓存"""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or "./cache/embeddings")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, text: str, model_name: str) -> str:
        """生成缓存键"""
        import hashlib
        content = f"{text}_{model_name}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, text: str, model_name: str) -> Optional[np.ndarray]:
        """获取缓存的嵌入"""
        cache_key = self._get_cache_key(text, model_name)
        cache_file = self.cache_dir / f"{cache_key}.pkl"

        try:
            if cache_file.exists():
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
        except Exception as e:
            logger.error(f"读取缓存失败: {str(e)}")

        return None

    def set(self, text: str, model_name: str, embedding: np.ndarray):
        """设置缓存"""
        cache_key = self._get_cache_key(text, model_name)
        cache_file = self.cache_dir / f"{cache_key}.pkl"

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(embedding, f)
        except Exception as e:
            logger.error(f"写入缓存失败: {str(e)}")

    def clear(self):
        """清空缓存"""
        try:
            import shutil
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("嵌入缓存已清空")
        except Exception as e:
            logger.error(f"清空缓存失败: {str(e)}")


class EmbeddingManager:
    """嵌入管理器"""

    def __init__(
        self,
        model: Optional[EmbeddingModel] = None,
        use_cache: bool = True,
        cache_dir: Optional[str] = None,
    ):
        # 初始化模型
        if model is None:
            if settings.openai_api_key:
                self.model = OpenAIEmbedding()
            else:
                self.model = LocalEmbedding()
        else:
            self.model = model

        # 初始化缓存
        self.use_cache = use_cache
        self.cache = EmbeddingCache(cache_dir) if use_cache else None

        # Token计数器
        self.token_counter = TokenCounter()

        # 统计信息
        self.stats = {
            "total_embeddings": 0,
            "cache_hits": 0,
            "total_tokens": 0,
        }

    async def embed_texts(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 100,
        show_progress: bool = False,
    ) -> Union[np.ndarray, List[np.ndarray]]:
        """
        嵌入文本

        Args:
            texts: 文本或文本列表
            batch_size: 批处理大小
            show_progress: 是否显示进度

        Returns:
            嵌入向量
        """
        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]

        embeddings = []
        processed = 0

        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # 检查缓存
            cached_embeddings = []
            uncached_texts = []
            uncached_indices = []

            for j, text in enumerate(batch):
                if self.use_cache and self.cache:
                    cached = self.cache.get(text, self.model.model_name)
                    if cached is not None:
                        cached_embeddings.append(cached)
                        self.stats["cache_hits"] += 1
                    else:
                        uncached_texts.append(text)
                        uncached_indices.append(j)
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(j)

            # 编码未缓存的文本
            if uncached_texts:
                try:
                    new_embeddings = await self.model.encode(uncached_texts)

                    # 保存到缓存
                    if self.use_cache and self.cache:
                        for text, embedding in zip(uncached_texts, new_embeddings):
                            self.cache.set(text, self.model.model_name, embedding)

                    # 合并结果
                    batch_embeddings = []
                    cached_idx = 0
                    uncached_idx = 0
                    for k in range(len(batch)):
                        if k in uncached_indices:
                            batch_embeddings.append(new_embeddings[uncached_idx])
                            uncached_idx += 1
                        else:
                            batch_embeddings.append(cached_embeddings[cached_idx])
                            cached_idx += 1

                    embeddings.extend(batch_embeddings)
                except Exception as e:
                    logger.error(f"嵌入失败: {str(e)}")
                    # 使用零向量作为fallback
                    zero_embedding = np.zeros(self.model.get_dimension())
                    batch_embeddings = [zero_embedding] * len(batch)
                    embeddings.extend(batch_embeddings)
            else:
                embeddings.extend(cached_embeddings)

            # 更新统计
            processed += len(batch)
            self.stats["total_embeddings"] += len(batch)

            # 显示进度
            if show_progress:
                progress = processed / len(texts) * 100
                logger.info(f"嵌入进度: {progress:.1f}% ({processed}/{len(texts)})")

        # 转换为numpy数组
        embeddings = np.array(embeddings)

        if is_single:
            return embeddings[0]
        else:
            return embeddings

    async def embed_single_text(self, text: str) -> np.ndarray:
        """嵌入单个文本"""
        return await self.embed_texts(text)

    def get_dimension(self) -> int:
        """获取嵌入维度"""
        return self.model.get_dimension()

    def count_tokens(self, text: str) -> int:
        """计算token数"""
        return self.token_counter.count_tokens(text)

    def truncate_text(self, text: str, max_tokens: int) -> str:
        """截断文本"""
        return self.token_counter.truncate_to_tokens(text, max_tokens)

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        计算余弦相似度

        Args:
            embedding1: 向量1
            embedding2: 向量2

        Returns:
            相似度分数
        """
        # 确保向量是1维的
        if embedding1.ndim > 1:
            embedding1 = embedding1.flatten()
        if embedding2.ndim > 1:
            embedding2 = embedding2.flatten()

        # 计算余弦相似度
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def find_most_similar(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: List[np.ndarray],
        top_k: int = 5
    ) -> List[Tuple[int, float]]:
        """
        查找最相似的向量

        Args:
            query_embedding: 查询向量
            candidate_embeddings: 候选向量列表
            top_k: 返回数量

        Returns:
            (索引, 相似度)列表
        """
        similarities = []
        for i, embedding in enumerate(candidate_embeddings):
            similarity = self.compute_similarity(query_embedding, embedding)
            similarities.append((i, similarity))

        # 排序并返回top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        cache_hit_rate = 0
        if self.stats["total_embeddings"] > 0:
            cache_hit_rate = self.stats["cache_hits"] / self.stats["total_embeddings"] * 100

        return {
            "model_name": self.model.model_name,
            "dimension": self.get_dimension(),
            "total_embeddings": self.stats["total_embeddings"],
            "cache_hits": self.stats["cache_hits"],
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "use_cache": self.use_cache,
        }

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_embeddings": 0,
            "cache_hits": 0,
            "total_tokens": 0,
        }

    def clear_cache(self):
        """清空缓存"""
        if self.cache:
            self.cache.clear()
            logger.info("嵌入缓存已清空")