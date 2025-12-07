"""
AI模型管理器
统一管理多种AI模型（OpenAI、Claude、Gemini等）
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union, AsyncGenerator
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import json
import time
from openai import AsyncOpenAI
import anthropic
import google.generativeai as genai

from config.config import settings

logger = logging.getLogger(__name__)

class ModelProvider(Enum):
    """AI模型提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"

@dataclass
class ModelConfig:
    """模型配置"""
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = True
    timeout: int = 60

class BaseAIModel(ABC):
    """AI模型基类"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = None
        self._setup_client()

    @abstractmethod
    def _setup_client(self):
        """设置客户端"""
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        stream: bool = None
    ) -> Union[Dict[str, Any], AsyncGenerator]:
        """聊天完成"""
        pass

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """获取文本嵌入"""
        pass

    @abstractmethod
    def get_token_count(self, text: str) -> int:
        """计算token数量"""
        pass

class OpenAIModel(BaseAIModel):
    """OpenAI模型实现"""

    def _setup_client(self):
        """设置OpenAI客户端"""
        self.client = AsyncOpenAI(
            api_key=self.config.api_key or settings.OPENAI_API_KEY,
            base_url=self.config.base_url or settings.OPENAI_BASE_URL,
            timeout=self.config.timeout
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        stream: bool = None
    ) -> Union[Dict[str, Any], AsyncGenerator]:
        """OpenAI聊天完成"""
        stream = stream if stream is not None else self.config.stream

        try:
            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                stream=stream
            )

            if stream:
                async def stream_generator():
                    async for chunk in response:
                        if chunk.choices[0].delta.content is not None:
                            yield {
                                "type": "content",
                                "content": chunk.choices[0].delta.content
                            }
                    yield {"type": "end"}
                return stream_generator()
            else:
                return {
                    "content": response.choices[0].message.content,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                }

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """获取OpenAI嵌入"""
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-ada-002",
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI embeddings error: {str(e)}")
            raise

    def get_token_count(self, text: str) -> int:
        """计算OpenAI token数量"""
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model(self.config.model_name)
            return len(encoding.encode(text))
        except:
            # 如果没有找到特定的编码，使用默认的
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))

class ClaudeModel(BaseAIModel):
    """Claude模型实现"""

    def _setup_client(self):
        """设置Claude客户端"""
        self.client = anthropic.AsyncAnthropic(
            api_key=self.config.api_key,
            timeout=self.config.timeout
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        stream: bool = None
    ) -> Union[Dict[str, Any], AsyncGenerator]:
        """Claude聊天完成"""
        stream = stream if stream is not None else self.config.stream

        # 转换消息格式
        system_message = ""
        claude_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        try:
            response = await self.client.messages.create(
                model=self.config.model_name,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system_message,
                messages=claude_messages,
                stream=stream
            )

            if stream:
                async def stream_generator():
                    async for chunk in response:
                        if chunk.type == "content_block_delta":
                            yield {
                                "type": "content",
                                "content": chunk.delta.text
                            }
                    yield {"type": "end"}
                return stream_generator()
            else:
                return {
                    "content": response.content[0].text,
                    "usage": {
                        "prompt_tokens": response.usage.input_tokens,
                        "completion_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                    }
                }

        except Exception as e:
            logger.error(f"Claude API error: {str(e)}")
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Claude不支持嵌入API，使用OpenAI"""
        logger.warning("Claude does not support embeddings, falling back to OpenAI")
        openai_config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="text-embedding-ada-002"
        )
        openai_model = OpenAIModel(openai_config)
        return await openai_model.get_embeddings(texts)

    def get_token_count(self, text: str) -> int:
        """计算Claude token数量"""
        # Claude使用类似的token计算方式
        import tiktoken
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            # 粗略估算：1 token ≈ 4 characters
            return len(text) // 4

class GeminiModel(BaseAIModel):
    """Gemini模型实现"""

    def _setup_client(self):
        """设置Gemini客户端"""
        genai.configure(api_key=self.config.api_key)
        self.model = genai.GenerativeModel(self.config.model_name)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        stream: bool = None
    ) -> Union[Dict[str, Any], AsyncGenerator]:
        """Gemini聊天完成"""
        stream = stream if stream is not None else self.config.stream

        # 转换消息格式
        gemini_messages = []
        system_instruction = ""

        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                gemini_messages.append(msg["content"])
            elif msg["role"] == "assistant" and gemini_messages:
                gemini_messages[-1] = f"Previous response: {msg['content']}\n\nUser: {gemini_messages[-1]}"

        try:
            if system_instruction:
                self.model._system_instruction = system_instruction

            if stream:
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    gemini_messages,
                    stream=True
                )

                async def stream_generator():
                    for chunk in response:
                        if chunk.text:
                            yield {
                                "type": "content",
                                "content": chunk.text
                            }
                    yield {"type": "end"}
                return stream_generator()
            else:
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    gemini_messages
                )

                return {
                    "content": response.text,
                    "usage": {
                        # Gemini不返回详细的token信息
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None
                    }
                }

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Gemini不支持嵌入API，使用OpenAI"""
        logger.warning("Gemini does not support embeddings, falling back to OpenAI")
        openai_config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="text-embedding-ada-002"
        )
        openai_model = OpenAIModel(openai_config)
        return await openai_model.get_embeddings(texts)

    def get_token_count(self, text: str) -> int:
        """计算Gemini token数量"""
        # 粗略估算
        return len(text) // 4

class ModelManager:
    """模型管理器"""

    def __init__(self):
        self.models: Dict[str, BaseAIModel] = {}
        self.default_model: Optional[str] = None
        self._load_models()

    def _load_models(self):
        """加载模型配置"""
        # 从配置文件或环境变量加载模型
        model_configs = [
            # OpenAI模型
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_name="gpt-4-turbo-preview",
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                max_tokens=4000
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                max_tokens=3000
            ),

            # Claude模型（如果有API密钥）
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model_name="claude-3-opus-20240229",
                api_key=settings.get("ANTHROPIC_API_KEY"),
                max_tokens=4000
            ),
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model_name="claude-3-sonnet-20240229",
                api_key=settings.get("ANTHROPIC_API_KEY"),
                max_tokens=4000
            ),

            # Gemini模型（如果有API密钥）
            ModelConfig(
                provider=ModelProvider.GOOGLE,
                model_name="gemini-pro",
                api_key=settings.get("GOOGLE_API_KEY"),
                max_tokens=2048
            )
        ]

        # 初始化模型
        for config in model_configs:
            if config.api_key or (config.provider == ModelProvider.OPENAI and config.api_key):
                model_key = f"{config.provider.value}:{config.model_name}"
                try:
                    if config.provider == ModelProvider.OPENAI:
                        self.models[model_key] = OpenAIModel(config)
                    elif config.provider == ModelProvider.ANTHROPIC:
                        self.models[model_key] = ClaudeModel(config)
                    elif config.provider == ModelProvider.GOOGLE:
                        self.models[model_key] = GeminiModel(config)

                    # 设置默认模型
                    if not self.default_model and config.provider == ModelProvider.OPENAI:
                        self.default_model = model_key

                    logger.info(f"Loaded model: {model_key}")
                except Exception as e:
                    logger.error(f"Failed to load model {model_key}: {str(e)}")

    async def chat_completion(
        self,
        model_name: Optional[str] = None,
        messages: List[Dict[str, str]] = None,
        stream: bool = True
    ) -> Union[Dict[str, Any], AsyncGenerator]:
        """聊天完成"""
        model_key = model_name or self.default_model

        if not model_key or model_key not in self.models:
            raise ValueError(f"Model not available: {model_key}")

        return await self.models[model_key].chat_completion(messages, stream)

    async def get_embeddings(
        self,
        texts: List[str],
        model_name: Optional[str] = None
    ) -> List[List[float]]:
        """获取文本嵌入"""
        # 默认使用OpenAI的嵌入模型
        if not model_name:
            model_key = "openai:text-embedding-ada-002"
            if model_key not in self.models:
                openai_config = ModelConfig(
                    provider=ModelProvider.OPENAI,
                    model_name="text-embedding-ada-002"
                )
                self.models[model_key] = OpenAIModel(openai_config)
        else:
            model_key = model_name

        return await self.models[model_key].get_embeddings(texts)

    def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        models = []
        for key, model in self.models.items():
            provider, name = key.split(":", 1)
            models.append({
                "id": key,
                "provider": provider,
                "name": name,
                "is_default": key == self.default_model,
                "max_tokens": model.config.max_tokens,
                "supports_streaming": model.config.stream,
                "supports_embeddings": hasattr(model, 'get_embeddings')
            })
        return models

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取模型信息"""
        if model_name not in self.models:
            return None

        model = self.models[model_name]
        return {
            "provider": model.config.provider.value,
            "model_name": model.config.model_name,
            "max_tokens": model.config.max_tokens,
            "temperature": model.config.temperature,
            "supports_streaming": model.config.stream,
            "supports_embeddings": hasattr(model, 'get_embeddings')
        }

    async def test_model(self, model_name: str) -> Dict[str, Any]:
        """测试模型是否可用"""
        start_time = time.time()

        try:
            messages = [{"role": "user", "content": "Hello, respond with just 'OK'"}]
            response = await self.chat_completion(
                model_name=model_name,
                messages=messages,
                stream=False
            )

            duration = time.time() - start_time

            if isinstance(response, dict) and "content" in response:
                return {
                    "status": "success",
                    "response": response["content"][:100],  # 只返回前100个字符
                    "duration": f"{duration:.2f}s",
                    "model_info": self.get_model_info(model_name)
                }
            else:
                return {
                    "status": "error",
                    "error": "Invalid response format"
                }

        except Exception as e:
            duration = time.time() - start_time
            return {
                "status": "error",
                "error": str(e),
                "duration": f"{duration:.2f}s"
            }

# 全局模型管理器实例
model_manager = ModelManager()

# 便捷函数
async def chat_with_ai(
    message: str,
    model: Optional[str] = None,
    context: Optional[List[Dict[str, str]]] = None,
    stream: bool = True
) -> Union[Dict[str, Any], AsyncGenerator]:
    """与AI模型聊天"""
    messages = context or []
    messages.append({"role": "user", "content": message})

    return await model_manager.chat_completion(
        model_name=model,
        messages=messages,
        stream=stream
    )

async def get_text_embeddings(texts: List[str]) -> List[List[float]]:
    """获取文本嵌入"""
    return await model_manager.get_embeddings(texts)

def get_available_ai_models() -> List[Dict[str, Any]]:
    """获取可用AI模型列表"""
    return model_manager.get_available_models()