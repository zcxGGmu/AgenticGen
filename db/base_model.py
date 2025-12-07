"""
基础数据模型

定义所有模型的基础类和通用字段。
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, Integer, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BaseModel(Base):
    """基础模型类，包含通用字段"""

    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间"
    )
    metadata_json = Column(JSON, nullable=True, comment="额外元数据")

    def to_dict(self) -> Dict[str, Any]:
        """
        将模型转换为字典

        Returns:
            模型字典
        """
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """
        从字典更新模型

        Args:
            data: 更新数据
        """
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.utcnow()

    def set_metadata(self, key: str, value: Any) -> None:
        """
        设置元数据

        Args:
            key: 元数据键
            value: 元数据值
        """
        if self.metadata_json is None:
            self.metadata_json = {}
        self.metadata_json[key] = value
        self.updated_at = datetime.utcnow()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        获取元数据

        Args:
            key: 元数据键
            default: 默认值

        Returns:
            元数据值
        """
        if self.metadata_json is None:
            return default
        return self.metadata_json.get(key, default)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"