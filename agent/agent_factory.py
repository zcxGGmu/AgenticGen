"""
Agent工厂

创建和配置不同类型的Agent实例。
"""

from typing import Dict, Any, Optional, List
import openai
from openai import OpenAI, AsyncOpenAI

from agent.agent_config import AgentConfig, AgentType, PREDEFINED_AGENTS, ToolConfig
from config import settings
from config.prompts import PromptTemplates
from config.logging import get_logger

logger = get_logger(__name__)


class AgentFactory:
    """Agent工厂类"""

    def __init__(self):
        self.api_key = settings.openai_api_key
        self.client = None
        self.async_client = None

    def get_client(self, async_client: bool = False) -> openai.OpenAI:
        """
        获取OpenAI客户端

        Args:
            async_client: 是否使用异步客户端

        Returns:
            OpenAI客户端
        """
        if async_client:
            if self.async_client is None:
                self.async_client = AsyncOpenAI(api_key=self.api_key)
            return self.async_client
        else:
            if self.client is None:
                self.client = OpenAI(api_key=self.api_key)
            return self.client

    def create_agent(self, config: AgentConfig) -> "Agent":
        """
        创建Agent实例

        Args:
            config: Agent配置

        Returns:
            Agent实例
        """
        # 确保系统提示词
        if not config.system_prompt:
            config.system_prompt = PromptTemplates.get_system_prompt({
                "task_type": config.agent_type.value
            })

        # 创建Agent
        agent = Agent(
            config=config,
            client=self.get_client(async_client=False),
            async_client=self.get_client(async_client=True)
        )

        logger.info(f"创建Agent: {config.name} ({config.agent_type})")
        return agent

    def create_agent_from_type(
        self,
        agent_type: AgentType,
        **kwargs
    ) -> "Agent":
        """
        从类型创建Agent

        Args:
            agent_type: Agent类型
            **kwargs: 额外配置参数

        Returns:
            Agent实例
        """
        # 获取预定义配置
        if agent_type not in PREDEFINED_AGENTS:
            raise ValueError(f"不支持的Agent类型: {agent_type}")

        config = PREDEFINED_AGENTS[agent_type].copy(deep=True)

        # 更新配置
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return self.create_agent(config)

    def create_custom_agent(
        self,
        name: str,
        agent_type: AgentType,
        system_prompt: Optional[str] = None,
        tools: Optional[List[ToolConfig]] = None,
        **kwargs
    ) -> "Agent":
        """
        创建自定义Agent

        Args:
            name: Agent名称
            agent_type: Agent类型
            system_prompt: 系统提示词
            tools: 工具列表
            **kwargs: 其他配置参数

        Returns:
            Agent实例
        """
        config = AgentConfig(
            agent_id=f"custom_{name.lower().replace(' ', '_')}",
            name=name,
            agent_type=agent_type,
            system_prompt=system_prompt,
            tools=tools or [],
            **kwargs
        )

        return self.create_agent(config)


class Agent:
    """Agent类，代表一个AI助手实例"""

    def __init__(
        self,
        config: AgentConfig,
        client: openai.OpenAI,
        async_client: openai.AsyncOpenAI
    ):
        self.config = config
        self.client = client
        self.async_client = async_client
        self.conversation_history = []
        self.context = {}

    def add_message(self, role: str, content: str) -> None:
        """
        添加消息到对话历史

        Args:
            role: 角色（user/assistant/system）
            content: 消息内容
        """
        self.conversation_history.append({
            "role": role,
            "content": content
        })

        # 保持历史记录在限制范围内
        if len(self.conversation_history) > self.config.memory_limit * 2:
            # 保留系统消息和最近的对话
            system_messages = [m for m in self.conversation_history if m["role"] == "system"]
            recent_messages = self.conversation_history[-self.config.memory_limit * 2 + len(system_messages):]
            self.conversation_history = system_messages + recent_messages

    def clear_history(self) -> None:
        """清空对话历史"""
        self.conversation_history = []

    def set_context(self, key: str, value: Any) -> None:
        """
        设置上下文

        Args:
            key: 上下文键
            value: 上下文值
        """
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """
        获取上下文

        Args:
            key: 上下文键
            default: 默认值

        Returns:
            上下文值
        """
        return self.context.get(key, default)

    def _prepare_messages(self, user_message: str) -> List[Dict[str, str]]:
        """
        准备发送给API的消息

        Args:
            user_message: 用户消息

        Returns:
            消息列表
        """
        messages = []

        # 添加系统提示词
        if self.config.system_prompt:
            messages.append({
                "role": "system",
                "content": self.config.system_prompt
            })

        # 添加对话历史
        messages.extend(self.conversation_history)

        # 添加用户消息
        messages.append({
            "role": "user",
            "content": user_message
        })

        return messages

    def chat(self, message: str, **kwargs) -> str:
        """
        同步聊天

        Args:
            message: 用户消息
            **kwargs: 额外参数

        Returns:
            助手回复
        """
        try:
            # 准备消息
            messages = self._prepare_messages(message)

            # 准备API配置
            api_config = self.config.to_openai_config()
            api_config.update(kwargs)

            # 调用OpenAI API
            response = self.client.chat.completions.create(
                messages=messages,
                **api_config
            )

            # 获取回复
            reply = response.choices[0].message.content

            # 更新对话历史
            self.add_message("user", message)
            self.add_message("assistant", reply)

            return reply

        except Exception as e:
            logger.error(f"Agent聊天失败: {str(e)}")
            raise

    async def chat_async(self, message: str, **kwargs) -> str:
        """
        异步聊天

        Args:
            message: 用户消息
            **kwargs: 额外参数

        Returns:
            助手回复
        """
        try:
            # 准备消息
            messages = self._prepare_messages(message)

            # 准备API配置
            api_config = self.config.to_openai_config()
            api_config.update(kwargs)

            # 调用OpenAI API
            response = await self.async_client.chat.completions.create(
                messages=messages,
                **api_config
            )

            # 获取回复
            reply = response.choices[0].message.content

            # 更新对话历史
            self.add_message("user", message)
            self.add_message("assistant", reply)

            return reply

        except Exception as e:
            logger.error(f"Agent异步聊天失败: {str(e)}")
            raise

    def chat_stream(self, message: str, **kwargs):
        """
        流式聊天

        Args:
            message: 用户消息
            **kwargs: 额外参数

        Yields:
            回复片段
        """
        try:
            # 准备消息
            messages = self._prepare_messages(message)

            # 准备API配置
            api_config = self.config.to_openai_config()
            api_config.update(kwargs)
            api_config["stream"] = True

            # 调用OpenAI API
            stream = self.client.chat.completions.create(
                messages=messages,
                **api_config
            )

            # 收集完整回复
            full_reply = ""
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    full_reply += content
                    yield content

            # 更新对话历史
            self.add_message("user", message)
            self.add_message("assistant", full_reply)

        except Exception as e:
            logger.error(f"Agent流式聊天失败: {str(e)}")
            raise

    async def chat_stream_async(self, message: str, **kwargs):
        """
        异步流式聊天

        Args:
            message: 用户消息
            **kwargs: 额外参数

        Yields:
            回复片段
        """
        try:
            # 准备消息
            messages = self._prepare_messages(message)

            # 准备API配置
            api_config = self.config.to_openai_config()
            api_config.update(kwargs)
            api_config["stream"] = True

            # 调用OpenAI API
            stream = await self.async_client.chat.completions.create(
                messages=messages,
                **api_config
            )

            # 收集完整回复
            full_reply = ""
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    full_reply += content
                    yield content

            # 更新对话历史
            self.add_message("user", message)
            self.add_message("assistant", full_reply)

        except Exception as e:
            logger.error(f"Agent异步流式聊天失败: {str(e)}")
            raise

    def update_config(self, **kwargs) -> None:
        """
        更新Agent配置

        Args:
            **kwargs: 要更新的配置参数
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.debug(f"更新Agent配置: {key} = {value}")

    def get_status(self) -> Dict[str, Any]:
        """
        获取Agent状态

        Returns:
            状态信息
        """
        return {
            "agent_id": self.config.agent_id,
            "name": self.config.name,
            "type": self.config.agent_type,
            "model": self.config.model,
            "conversation_length": len(self.conversation_history),
            "context_keys": list(self.context.keys()),
            "tools_enabled": [t.name for t in self.config.tools if t.enabled],
        }