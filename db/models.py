"""
数据模型定义

定义所有数据库模型类。
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    LargeBinary,
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.dialects.mysql import LONGTEXT

from .base_model import BaseModel


class DbBase(BaseModel):
    """数据库连接配置模型"""

    __tablename__ = "db_bases"

    name = Column(String(100), nullable=False, unique=True, comment="数据库名称")
    host = Column(String(255), nullable=False, comment="数据库主机")
    port = Column(Integer, nullable=False, comment="端口号")
    username = Column(String(100), nullable=False, comment="用户名")
    password = Column(String(255), nullable=False, comment="密码")
    database = Column(String(100), nullable=False, comment="数据库名")
    driver = Column(String(50), default="mysql", comment="数据库驱动")
    charset = Column(String(20), default="utf8mb4", comment="字符集")
    is_active = Column(Boolean, default=True, comment="是否激活")
    description = Column(Text, nullable=True, comment="描述")

    # 关系
    threads = relationship("ThreadModel", back_populates="db_connection")

    @validates('port')
    def validate_port(self, key, value):
        if not 1 <= value <= 65535:
            raise ValueError('端口号必须在1-65535之间')
        return value


class SecretModel(BaseModel):
    """密钥管理模型"""

    __tablename__ = "secrets"

    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    name = Column(String(200), nullable=False, comment="密钥名称")
    secret_value = Column(Text, nullable=False, comment="加密的密钥值")
    secret_type = Column(String(50), nullable=False, comment="密钥类型")
    is_active = Column(Boolean, default=True, comment="是否激活")
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    last_used_at = Column(DateTime, nullable=True, comment="最后使用时间")
    usage_count = Column(Integer, default=0, comment="使用次数")

    # 关系
    threads = relationship("ThreadModel", back_populates="secret")

    @validates('expires_at')
    def validate_expires_at(self, key, value):
        if value and value <= datetime.utcnow():
            raise ValueError('过期时间必须是未来时间')
        return value

    def is_expired(self) -> bool:
        """检查密钥是否过期"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class ThreadModel(BaseModel):
    """会话线程模型"""

    __tablename__ = "threads"

    thread_id = Column(String(100), nullable=False, unique=True, index=True, comment="线程ID")
    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    title = Column(String(500), nullable=True, comment="线程标题")
    status = Column(String(50), default="active", comment="状态")
    secret_id = Column(Integer, ForeignKey("secrets.id"), nullable=True, comment="关联密钥ID")
    db_base_id = Column(Integer, ForeignKey("db_bases.id"), nullable=True, comment="数据库连接ID")
    model_name = Column(String(100), nullable=True, comment="使用的模型名称")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    context = Column(JSON, nullable=True, comment="上下文信息")
    is_archived = Column(Boolean, default=False, comment="是否归档")

    # 关系
    secret = relationship("SecretModel", back_populates="threads")
    db_connection = relationship("DbBase", back_populates="threads")
    messages = relationship("MessageModel", back_populates="thread", cascade="all, delete-orphan")

    @validates('status')
    def validate_status(self, key, value):
        allowed_statuses = ['active', 'paused', 'completed', 'error', 'archived']
        if value not in allowed_statuses:
            raise ValueError(f'状态必须是以下之一: {allowed_statuses}')
        return value


class KnowledgeBase(BaseModel):
    """知识库模型"""

    __tablename__ = "knowledge_bases"

    name = Column(String(200), nullable=False, comment="知识库名称")
    description = Column(Text, nullable=True, comment="描述")
    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    embedding_model = Column(String(100), nullable=True, comment="嵌入模型")
    chunk_size = Column(Integer, default=1000, comment="分块大小")
    chunk_overlap = Column(Integer, default=200, comment="分块重叠")
    total_documents = Column(Integer, default=0, comment="文档总数")
    total_chunks = Column(Integer, default=0, comment="分块总数")
    is_public = Column(Boolean, default=False, comment="是否公开")
    is_active = Column(Boolean, default=True, comment="是否激活")
    metadata = Column(JSON, nullable=True, comment="知识库元数据")

    # 关系
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base")


class KnowledgeDocument(BaseModel):
    """知识库文档模型"""

    __tablename__ = "knowledge_documents"

    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="知识库ID")
    filename = Column(String(500), nullable=False, comment="文件名")
    file_path = Column(String(1000), nullable=False, comment="文件路径")
    file_size = Column(Integer, nullable=False, comment="文件大小")
    file_type = Column(String(50), nullable=False, comment="文件类型")
    content_hash = Column(String(64), nullable=False, comment="内容哈希")
    chunk_count = Column(Integer, default=0, comment="分块数量")
    processing_status = Column(String(50), default="pending", comment="处理状态")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 关系
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(BaseModel):
    """知识库文档分块模型"""

    __tablename__ = "knowledge_chunks"

    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=False, comment="文档ID")
    chunk_index = Column(Integer, nullable=False, comment="分块索引")
    content = Column(LONGTEXT, nullable=False, comment="分块内容")
    token_count = Column(Integer, nullable=False, comment="token数量")
    embedding = Column(LargeBinary, nullable=True, comment="嵌入向量")
    metadata = Column(JSON, nullable=True, comment="分块元数据")

    # 关系
    document = relationship("KnowledgeDocument", back_populates="chunks")


class MessageModel(BaseModel):
    """消息模型"""

    __tablename__ = "messages"

    thread_id = Column(String(100), ForeignKey("threads.thread_id"), nullable=False, comment="线程ID")
    role = Column(String(50), nullable=False, comment="角色")
    content = Column(LONGTEXT, nullable=False, comment="消息内容")
    token_count = Column(Integer, nullable=True, comment="token数量")
    model_name = Column(String(100), nullable=True, comment="使用的模型")
    finish_reason = Column(String(50), nullable=True, comment="完成原因")
    function_call = Column(JSON, nullable=True, comment="函数调用信息")
    tool_calls = Column(JSON, nullable=True, comment="工具调用信息")
    parent_message_id = Column(String(100), nullable=True, comment="父消息ID")
    metadata = Column(JSON, nullable=True, comment="消息元数据")

    # 关系
    thread = relationship("ThreadModel", back_populates="messages")

    @validates('role')
    def validate_role(self, key, value):
        allowed_roles = ['user', 'assistant', 'system', 'function', 'tool']
        if value not in allowed_roles:
            raise ValueError(f'角色必须是以下之一: {allowed_roles}')
        return value


class FileInfo(BaseModel):
    """文件信息模型"""

    __tablename__ = "file_info"

    filename = Column(String(500), nullable=False, comment="文件名")
    original_filename = Column(String(500), nullable=False, comment="原始文件名")
    file_path = Column(String(1000), nullable=False, comment="文件路径")
    file_size = Column(Integer, nullable=False, comment="文件大小")
    file_type = Column(String(50), nullable=False, comment="文件类型")
    mime_type = Column(String(100), nullable=True, comment="MIME类型")
    content_hash = Column(String(64), nullable=False, comment="内容哈希")
    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    thread_id = Column(String(100), nullable=True, comment="关联线程ID")
    is_temp = Column(Boolean, default=False, comment="是否临时文件")
    download_count = Column(Integer, default=0, comment="下载次数")
    last_accessed_at = Column(DateTime, nullable=True, comment="最后访问时间")

    @validates('file_size')
    def validate_file_size(self, key, value):
        if value < 0:
            raise ValueError('文件大小不能为负数')
        return value

    def increment_download(self) -> None:
        """增加下载次数"""
        self.download_count += 1
        self.last_accessed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class UserSession(BaseModel):
    """用户会话模型"""

    __tablename__ = "user_sessions"

    session_id = Column(String(100), nullable=False, unique=True, index=True, comment="会话ID")
    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    ip_address = Column(String(45), nullable=True, comment="IP地址")
    user_agent = Column(Text, nullable=True, comment="用户代理")
    is_active = Column(Boolean, default=True, comment="是否激活")
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    last_activity_at = Column(DateTime, default=datetime.utcnow, comment="最后活动时间")
    session_data = Column(JSON, nullable=True, comment="会话数据")

    def is_expired(self) -> bool:
        """检查会话是否过期"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def update_activity(self) -> None:
        """更新最后活动时间"""
        self.last_activity_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()