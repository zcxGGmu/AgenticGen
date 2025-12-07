"""
安全模块初始化
提供安全管理相关的工具和中间件
"""

from .security_utils import (
    # 加密管理
    EncryptionManager,
    encryption_manager,

    # 令牌管理
    TokenManager,
    token_manager,

    # 密码管理
    PasswordManager,
    password_manager,

    # API密钥管理
    APIKeyManager,
    api_key_manager,

    # 安全验证
    SecurityValidator,
    security_validator,

    # 安全审计
    SecurityAuditor,
    security_auditor,

    # 便捷函数
    hash_password,
    verify_password,
    generate_token,
    verify_token,
)

from .middleware import (
    # 安全中间件
    SecurityHeadersMiddleware,
    CSRFMiddleware,
    InputValidationMiddleware,
    RateLimitingMiddleware,
    RequestLoggingMiddleware,
    SessionSecurityMiddleware,
    SQLInjectionProtectionMiddleware,

    # 中间件工厂
    add_security_middleware,
)

__all__ = [
    # 加密相关
    "EncryptionManager",
    "encryption_manager",

    # 令牌相关
    "TokenManager",
    "token_manager",

    # 密码相关
    "PasswordManager",
    "password_manager",

    # API密钥相关
    "APIKeyManager",
    "api_key_manager",

    # 验证相关
    "SecurityValidator",
    "security_validator",

    # 审计相关
    "SecurityAuditor",
    "security_auditor",

    # 中间件
    "SecurityHeadersMiddleware",
    "CSRFMiddleware",
    "InputValidationMiddleware",
    "RateLimitingMiddleware",
    "RequestLoggingMiddleware",
    "SessionSecurityMiddleware",
    "SQLInjectionProtectionMiddleware",
    "add_security_middleware",

    # 便捷函数
    "hash_password",
    "verify_password",
    "generate_token",
    "verify_token",
]

# 初始化函数
def init_security():
    """初始化安全模块"""
    logger = logging.getLogger(__name__)
    logger.info("Security module initialized")