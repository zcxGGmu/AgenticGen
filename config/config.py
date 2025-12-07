"""
主配置文件

管理所有应用程序配置，使用 Pydantic Settings 进行类型验证和加载。
"""

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseSettings, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用程序主配置类"""

    # 应用基础配置
    app_name: str = "AgenticGen"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 9000
    workers: int = 1

    # 数据库配置
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "agenticgen"
    db_pool_size: int = 20
    db_max_overflow: int = 30

    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0

    # OpenAI配置
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.7

    # JWT配置
    jwt_secret_key: str = "your-secret-key-here"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # 文件上传配置
    max_file_size: str = "100MB"
    upload_path: str = "./uploads"
    allowed_extensions: str = "txt,pdf,docx,doc,xlsx,xls,pptx,ppt,jpg,jpeg,png,gif"

    # 日志配置
    log_level: str = "INFO"
    log_file: str = "./logs/app.log"
    log_rotation: str = "1 day"
    log_retention: str = "30 days"

    # 安全配置
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS"
    cors_allow_headers: str = "*"

    # 速率限制配置
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # Docker配置
    use_docker: bool = False
    mysql_root_password: Optional[str] = None
    mysql_database: Optional[str] = None
    mysql_user: Optional[str] = None
    mysql_password: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("max_file_size")
    def parse_file_size(cls, v):
        """解析文件大小字符串为字节数"""
        if isinstance(v, str):
            v = v.upper()
            if v.endswith("KB"):
                return int(v[:-2]) * 1024
            elif v.endswith("MB"):
                return int(v[:-2]) * 1024 * 1024
            elif v.endswith("GB"):
                return int(v[:-2]) * 1024 * 1024 * 1024
            else:
                return int(v)
        return v

    @validator("allowed_extensions")
    def parse_extensions(cls, v):
        """解析允许的文件扩展名"""
        if isinstance(v, str):
            return [ext.strip().lower() for ext in v.split(",")]
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """获取CORS允许的源列表"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def cors_methods_list(self) -> List[str]:
        """获取CORS允许的方法列表"""
        return [method.strip() for method in self.cors_allow_methods.split(",")]

    @property
    def database_url(self) -> str:
        """生成数据库连接URL"""
        if self.use_docker:
            return f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.db_host}:{self.db_port}/{self.mysql_database}"
        else:
            return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        """生成Redis连接URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache()
def get_settings() -> Settings:
    """获取应用程序设置（单例模式）"""
    return Settings()


# 创建全局设置实例
settings = get_settings()