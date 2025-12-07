"""
Agent管理器

管理Agent的生命周期、配置和状态。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable

from agent.agent_factory import AgentFactory, Agent
from agent.agent_config import AgentConfig, AgentType
from cache.thread_cache import ThreadCache
from config.logging import get_logger
from ai_models import get_available_ai_models, model_manager

logger = get_logger(__name__)


class AgentManager:
    """Agent管理器"""

    def __init__(self):
        self.factory = AgentFactory()
        self.thread_cache = ThreadCache()
        self.active_agents: Dict[str, Agent] = {}
        self.agent_configs: Dict[str, AgentConfig] = {}
        self.cleanup_interval = 300  # 5分钟清理一次
        self.agent_timeout = 3600  # 1小时不活动后清理

    async def get_or_create_agent(
        self,
        thread_id: str,
        agent_type: AgentType = AgentType.GENERAL,
        config: Optional[AgentConfig] = None,
        **kwargs
    ) -> Agent:
        """
        获取或创建Agent

        Args:
            thread_id: 会话ID
            agent_type: Agent类型
            config: 自定义配置
            **kwargs: 额外配置参数

        Returns:
            Agent实例
        """
        # 检查是否已存在活跃的Agent
        if thread_id in self.active_agents:
            agent = self.active_agents[thread_id]
            # 更新配置（如果有）
            if config or kwargs:
                self._update_agent_config(agent, config, **kwargs)
            return agent

        # 从缓存加载会话信息
        thread_info = await self.thread_cache.get_thread_info(thread_id)

        # 创建或加载配置
        if config:
            agent_config = config
        elif thread_info and "agent_config" in thread_info:
            agent_config = AgentConfig(**thread_info["agent_config"])
        else:
            # 使用默认配置
            agent_config = self._get_default_config(agent_type, **kwargs)

        # 创建Agent
        agent = self.factory.create_agent(agent_config)

        # 加载对话历史
        await self._load_conversation_history(agent, thread_id)

        # 加载上下文
        context = await self.thread_cache.get_context(thread_id)
        if context:
            for key, value in context.items():
                agent.set_context(key, value)

        # 保存到活跃Agent列表
        self.active_agents[thread_id] = agent
        self.agent_configs[thread_id] = agent_config

        logger.info(f"创建/获取Agent: {thread_id} -> {agent_config.name}")
        return agent

    async def save_agent_state(self, thread_id: str) -> bool:
        """
        保存Agent状态

        Args:
            thread_id: 会话ID

        Returns:
            是否成功
        """
        if thread_id not in self.active_agents:
            return False

        try:
            agent = self.active_agents[thread_id]
            config = self.agent_configs[thread_id]

            # 保存会话信息
            thread_info = {
                "agent_id": config.agent_id,
                "agent_type": config.agent_type.value,
                "agent_config": config.dict(),
                "last_active": datetime.utcnow().isoformat(),
            }
            await self.thread_cache.set_thread_info(thread_id, thread_info)

            # 保存对话历史
            messages = agent.conversation_history
            for message in messages:
                await self.thread_cache.add_message(thread_id, message)

            # 保存上下文
            if agent.context:
                await self.thread_cache.set_context(thread_id, agent.context)

            logger.debug(f"保存Agent状态: {thread_id}")
            return True

        except Exception as e:
            logger.error(f"保存Agent状态失败 {thread_id}: {str(e)}")
            return False

    async def remove_agent(self, thread_id: str) -> bool:
        """
        移除Agent

        Args:
            thread_id: 会话ID

        Returns:
            是否成功
        """
        # 保存状态
        await self.save_agent_state(thread_id)

        # 从活跃列表中移除
        if thread_id in self.active_agents:
            del self.active_agents[thread_id]
            del self.agent_configs[thread_id]

        logger.info(f"移除Agent: {thread_id}")
        return True

    async def cleanup_inactive_agents(self) -> int:
        """
        清理不活跃的Agent

        Returns:
            清理的Agent数量
        """
        cleaned_count = 0
        current_time = datetime.utcnow()

        threads_to_remove = []
        for thread_id, agent in self.active_agents.items():
            # 检查最后活动时间
            if hasattr(agent, 'last_activity'):
                last_activity = agent.last_activity
            else:
                # 使用会话信息的最后活动时间
                thread_info = await self.thread_cache.get_thread_info(thread_id)
                if thread_info and "last_active" in thread_info:
                    last_activity = datetime.fromisoformat(thread_info["last_active"])
                else:
                    last_activity = current_time

            # 如果超过超时时间，标记为待清理
            if current_time - last_activity > timedelta(seconds=self.agent_timeout):
                threads_to_remove.append(thread_id)

        # 清理标记的Agent
        for thread_id in threads_to_remove:
            await self.remove_agent(thread_id)
            cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"清理不活跃Agent: {cleaned_count} 个")

        return cleaned_count

    async def get_agent_status(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        获取Agent状态

        Args:
            thread_id: 会话ID

        Returns:
            状态信息
        """
        if thread_id not in self.active_agents:
            return None

        agent = self.active_agents[thread_id]
        config = self.agent_configs[thread_id]

        # 获取基础状态
        status = agent.get_status()

        # 添加额外信息
        status.update({
            "thread_id": thread_id,
            "config": config.dict(),
            "memory_usage": len(agent.conversation_history),
            "context_size": len(agent.context),
        })

        return status

    async def list_active_agents(self) -> List[Dict[str, Any]]:
        """
        列出所有活跃的Agent

        Returns:
            Agent状态列表
        """
        agents = []
        for thread_id in self.active_agents.keys():
            status = await self.get_agent_status(thread_id)
            if status:
                agents.append(status)
        return agents

    async def execute_agent_function(
        self,
        thread_id: str,
        function_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        执行Agent功能

        Args:
            thread_id: 会话ID
            function_name: 功能名称
            arguments: 参数

        Returns:
            执行结果
        """
        agent = await self.get_or_create_agent(thread_id)

        # 检查是否有对应的工具
        tool = agent.config.get_tool_by_name(function_name)
        if not tool or not tool.enabled:
            raise ValueError(f"工具 {function_name} 不存在或未启用")

        # 执行功能
        if function_name == "execute_python":
            return await self._execute_python(agent, arguments.get("code"))
        elif function_name == "execute_sql":
            return await self._execute_sql(agent, arguments.get("query"))
        elif function_name == "search_knowledge":
            return await self._search_knowledge(
                agent,
                arguments.get("query"),
                arguments.get("knowledge_base_id")
            )
        else:
            raise ValueError(f"未知的功能: {function_name}")

    def _get_default_config(
        self,
        agent_type: AgentType,
        **kwargs
    ) -> AgentConfig:
        """
        获取默认配置

        Args:
            agent_type: Agent类型
            **kwargs: 额外配置参数

        Returns:
            Agent配置
        """
        if agent_type in self.factory.create_agent_from_type.__defaults__:
            config = self.factory.create_agent_from_type(agent_type, **kwargs).config
        else:
            config = AgentConfig(
                agent_id=f"default_{agent_type.value}",
                name=f"默认{agent_type.value}助手",
                agent_type=agent_type,
                **kwargs
            )

        return config

    def _update_agent_config(
        self,
        agent: Agent,
        config: Optional[AgentConfig] = None,
        **kwargs
    ) -> None:
        """
        更新Agent配置

        Args:
            agent: Agent实例
            config: 新配置
            **kwargs: 配置参数
        """
        if config:
            # 完全替换配置
            agent.config = config
        else:
            # 部分更新配置
            agent.update_config(**kwargs)

        logger.debug(f"更新Agent配置: {agent.config.agent_id}")

    async def _load_conversation_history(self, agent: Agent, thread_id: str) -> None:
        """
        加载对话历史

        Args:
            agent: Agent实例
            thread_id: 会话ID
        """
        try:
            messages = await self.thread_cache.get_messages(thread_id)

            # 过滤系统消息，因为系统提示词会单独处理
            for message in messages:
                if message.get("role") != "system":
                    agent.conversation_history.append(message)

            logger.debug(f"加载对话历史: {thread_id}, {len(messages)} 条消息")

        except Exception as e:
            logger.error(f"加载对话历史失败 {thread_id}: {str(e)}")

    async def _execute_python(self, agent: Agent, code: str) -> Any:
        """执行Python代码"""
        # 这里应该调用tools模块的Python执行器
        from tools.python_executor import PythonExecutor
        executor = PythonExecutor()
        return await executor.execute(code)

    async def _execute_sql(self, agent: Agent, query: str) -> Any:
        """执行SQL查询"""
        # 这里应该调用tools模块的SQL执行器
        from tools.sql_executor import SQLExecutor
        executor = SQLExecutor()
        return await executor.execute(query)

    async def _search_knowledge(
        self,
        agent: Agent,
        query: str,
        knowledge_base_id: Optional[str] = None
    ) -> Any:
        """搜索知识库"""
        # 这里应该调用knowledge模块的检索功能
        from knowledge.retrieval import KnowledgeRetrieval
        retrieval = KnowledgeRetrieval()
        return await retrieval.search(query, knowledge_base_id)

    async def start_cleanup_task(self):
        """启动清理任务"""
        async def cleanup_loop():
            while True:
                try:
                    await self.cleanup_inactive_agents()
                except Exception as e:
                    logger.error(f"清理任务执行失败: {str(e)}")

                await asyncio.sleep(self.cleanup_interval)

        # 创建后台任务
        asyncio.create_task(cleanup_loop())
        logger.info("启动Agent清理任务")

    async def shutdown(self):
        """关闭管理器"""
        # 保存所有Agent状态
        for thread_id in list(self.active_agents.keys()):
            await self.save_agent_state(thread_id)

        # 清空活跃列表
        self.active_agents.clear()
        self.agent_configs.clear()

        logger.info("Agent管理器已关闭")


# 创建全局Agent管理器实例
_agent_manager = None


def get_agent_manager() -> AgentManager:
    """获取Agent管理器实例（单例模式）"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager