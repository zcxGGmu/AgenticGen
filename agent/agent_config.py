"""
Agent配置

定义Agent的配置类和类型。
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Agent类型枚举"""
    GENERAL = "general"  # 通用助手
    CODING = "coding"  # 编程助手
    DATA_ANALYSIS = "data_analysis"  # 数据分析助手
    SQL = "sql"  # SQL生成助手
    KNOWLEDGE = "knowledge"  # 知识库问答助手
    DOCUMENT = "document"  # 文档处理助手
    CONVERSATION = "conversation"  # 对话管理助手


class ToolConfig(BaseModel):
    """工具配置"""
    name: str
    description: str
    enabled: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timeout: int = 30


class AgentConfig(BaseModel):
    """Agent配置类"""

    # 基础配置
    agent_id: str
    name: str
    agent_type: AgentType
    description: Optional[str] = None

    # OpenAI配置
    model: str = "gpt-4-turbo-preview"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    # 系统提示词
    system_prompt: Optional[str] = None

    # 工具配置
    tools: List[ToolConfig] = Field(default_factory=list)
    tool_choice: str = "auto"  # auto, none, required

    # 流式响应配置
    stream: bool = True
    stream_chunk_size: int = 1000

    # 记忆管理
    memory_limit: int = 10  # 最大记忆轮次
    context_window_size: int = 8192  # 上下文窗口大小

    # 其他配置
    timeout: int = 60  # 请求超时时间（秒）
    retry_count: int = 3  # 重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True

    def to_openai_config(self) -> Dict[str, Any]:
        """
        转换为OpenAI API配置格式

        Returns:
            OpenAI配置字典
        """
        config = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": self.stream,
        }

        # 添加工具配置
        if self.tools:
            config["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in self.tools if tool.enabled
            ]
            config["tool_choice"] = self.tool_choice

        return config

    def get_tool_by_name(self, name: str) -> Optional[ToolConfig]:
        """
        根据名称获取工具配置

        Args:
            name: 工具名称

        Returns:
            工具配置或None
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def add_tool(self, tool: ToolConfig) -> None:
        """
        添加工具配置

        Args:
            tool: 工具配置
        """
        # 检查是否已存在
        for i, existing_tool in enumerate(self.tools):
            if existing_tool.name == tool.name:
                self.tools[i] = tool
                return

        # 添加新工具
        self.tools.append(tool)

    def remove_tool(self, name: str) -> bool:
        """
        移除工具配置

        Args:
            name: 工具名称

        Returns:
            是否成功移除
        """
        for i, tool in enumerate(self.tools):
            if tool.name == name:
                del self.tools[i]
                return True
        return False

    def enable_tool(self, name: str) -> bool:
        """
        启用工具

        Args:
            name: 工具名称

        Returns:
            是否成功
        """
        tool = self.get_tool_by_name(name)
        if tool:
            tool.enabled = True
            return True
        return False

    def disable_tool(self, name: str) -> bool:
        """
        禁用工具

        Args:
            name: 工具名称

        Returns:
            是否成功
        """
        tool = self.get_tool_by_name(name)
        if tool:
            tool.enabled = False
            return True
        return False


# 预定义的Agent配置模板
PREDEFINED_AGENTS = {
    AgentType.GENERAL: AgentConfig(
        agent_id="general_assistant",
        name="通用助手",
        agent_type=AgentType.GENERAL,
        description="通用的AI助手，可以回答各种问题和执行各种任务",
        system_prompt="你是一个有用的AI助手，能够回答问题、提供建议和帮助用户解决问题。",
    ),

    AgentType.CODING: AgentConfig(
        agent_id="coding_assistant",
        name="编程助手",
        agent_type=AgentType.CODING,
        description="专业的编程助手，擅长各种编程语言和技术",
        system_prompt="你是一个专业的编程助手，精通多种编程语言，能够编写、调试和优化代码。",
        tools=[
            ToolConfig(
                name="execute_python",
                description="执行Python代码",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要执行的Python代码"
                        }
                    },
                    "required": ["code"]
                }
            )
        ]
    ),

    AgentType.DATA_ANALYSIS: AgentConfig(
        agent_id="data_analysis_assistant",
        name="数据分析助手",
        agent_type=AgentType.DATA_ANALYSIS,
        description="专业的数据分析助手，能够处理和分析各种数据",
        system_prompt="你是一个专业的数据分析师，擅长数据清洗、分析、可视化和机器学习。",
        tools=[
            ToolConfig(
                name="execute_python",
                description="执行Python代码进行数据分析",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要执行的Python数据分析代码"
                        }
                    },
                    "required": ["code"]
                }
            ),
            ToolConfig(
                name="execute_sql",
                description="执行SQL查询",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "要执行的SQL查询语句"
                        }
                    },
                    "required": ["query"]
                }
            )
        ]
    ),

    AgentType.SQL: AgentConfig(
        agent_id="sql_assistant",
        name="SQL助手",
        agent_type=AgentType.SQL,
        description="专业的SQL助手，能够生成和优化SQL查询",
        system_prompt="你是一个专业的SQL专家，能够将自然语言转换为SQL查询，并优化查询性能。",
        tools=[
            ToolConfig(
                name="execute_sql",
                description="执行SQL查询",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "要执行的SQL查询语句"
                        }
                    },
                    "required": ["query"]
                }
            )
        ]
    ),

    AgentType.KNOWLEDGE: AgentConfig(
        agent_id="knowledge_assistant",
        name="知识库问答助手",
        agent_type=AgentType.KNOWLEDGE,
        description="基于知识库的问答助手，能够从知识库中检索和回答问题",
        system_prompt="你是一个知识库问答助手，基于提供的知识内容回答用户的问题。",
        tools=[
            ToolConfig(
                name="search_knowledge",
                description="搜索知识库",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询"
                        },
                        "knowledge_base_id": {
                            "type": "string",
                            "description": "知识库ID"
                        }
                    },
                    "required": ["query"]
                }
            )
        ]
    ),
}