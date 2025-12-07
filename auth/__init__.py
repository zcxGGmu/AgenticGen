"""
身份验证模块

提供API密钥管理、加密解密、身份验证、RBAC权限管理等功能。
"""

from .identity_verification import IdentityVerifier, get_identity_verifier
from .crypto import CryptoManager, get_crypto_manager
from .middleware import AuthMiddleware, rate_limit_middleware
from .decorators import require_auth, rate_limit
from .rbac import (
    rbac_manager,
    Permission,
    Role,
    RoleDefinition,
    PREDEFINED_ROLES,
    RBACManager,
    require_permission,
    require_permissions,
    require_any_permission,
    PermissionError
)
from .permissions import (
    require_permissions as api_require_permissions,
    require_any_permission as api_require_any_permission,
    require_role as api_require_role,
    check_user_permission,
    check_user_permissions,
    check_user_any_permission,
    get_user_permissions,
    PermissionGroup,
    require_user_management,
    require_chat_management,
    require_kb_management,
    require_file_management,
    require_tool_access,
    require_system_access,
    require_admin,
    ResourcePermissionChecker
)

__all__ = [
    # 核心验证
    "IdentityVerifier",
    "get_identity_verifier",
    "CryptoManager",
    "get_crypto_manager",

    # 中间件
    "AuthMiddleware",
    "rate_limit_middleware",

    # 装饰器
    "require_auth",
    "rate_limit",

    # RBAC系统
    "rbac_manager",
    "Permission",
    "Role",
    "RoleDefinition",
    "PREDEFINED_ROLES",
    "RBACManager",

    # 权限装饰器
    "require_permission",
    "require_permissions",
    "require_any_permission",
    "PermissionError",

    # API权限装饰器
    "api_require_permissions",
    "api_require_any_permission",
    "api_require_role",

    # 权限检查函数
    "check_user_permission",
    "check_user_permissions",
    "check_user_any_permission",
    "get_user_permissions",

    # 权限组
    "PermissionGroup",
    "require_user_management",
    "require_chat_management",
    "require_kb_management",
    "require_file_management",
    "require_tool_access",
    "require_system_access",
    "require_admin",

    # 资源权限检查
    "ResourcePermissionChecker",
]