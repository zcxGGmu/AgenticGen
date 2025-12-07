"""
权限检查中间件
"""

from functools import wraps
from typing import List, Optional, Callable, Any
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from auth.rbac import rbac_manager, Permission, PermissionError
from auth.auth import get_current_user

logger = logging.getLogger(__name__)
security = HTTPBearer()

def require_permissions(permissions: List[Permission]):
    """
    权限检查装饰器工厂

    Args:
        permissions: 需要的权限列表
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # 获取请求对象
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                # 获取当前用户
                user = await get_current_user(request.credentials.credentials if request else None)
                if not user:
                    raise HTTPException(
                        status_code=401,
                        detail="Authentication required"
                    )

                user_id = user.get("id")
                if not user_id:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid user ID"
                    )

                # 检查权限
                if not rbac_manager.check_permissions(user_id, permissions):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Permission denied. Required: {[p.value for p in permissions]}"
                    )

                # 将用户信息添加到kwargs
                kwargs["current_user"] = user

                return await func(*args, **kwargs)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Permission check failed: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail="Internal server error"
                )

        return wrapper
    return decorator

def require_any_permission(permissions: List[Permission]):
    """
    任意权限检查装饰器工厂

    Args:
        permissions: 权限列表（满足任意一个即可）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # 获取请求对象
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                # 获取当前用户
                user = await get_current_user(request.credentials.credentials if request else None)
                if not user:
                    raise HTTPException(
                        status_code=401,
                        detail="Authentication required"
                    )

                user_id = user.get("id")
                if not user_id:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid user ID"
                    )

                # 检查权限
                if not rbac_manager.has_any_permission(user_id, permissions):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Permission denied. One of required: {[p.value for p in permissions]}"
                    )

                # 将用户信息添加到kwargs
                kwargs["current_user"] = user

                return await func(*args, **kwargs)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Permission check failed: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail="Internal server error"
                )

        return wrapper
    return decorator

def require_role(role_name: str):
    """
    角色检查装饰器工厂

    Args:
        role_name: 角色名称
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # 获取请求对象
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                # 获取当前用户
                user = await get_current_user(request.credentials.credentials if request else None)
                if not user:
                    raise HTTPException(
                        status_code=401,
                        detail="Authentication required"
                    )

                user_id = user.get("id")
                if not user_id:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid user ID"
                    )

                # 获取用户角色
                user_roles = rbac_manager.get_user_roles(user_id)
                if not any(role.name == role_name for role in user_roles):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Role required: {role_name}"
                    )

                # 将用户信息添加到kwargs
                kwargs["current_user"] = user

                return await func(*args, **kwargs)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Role check failed: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail="Internal server error"
                )

        return wrapper
    return decorator

# 权限检查工具函数
async def check_user_permission(user_id: str, permission: Permission) -> bool:
    """检查用户权限"""
    return rbac_manager.check_permission(user_id, permission)

async def check_user_permissions(user_id: str, permissions: List[Permission]) -> bool:
    """检查用户多个权限"""
    return rbac_manager.check_permissions(user_id, permissions)

async def check_user_any_permission(user_id: str, permissions: List[Permission]) -> bool:
    """检查用户是否有任意权限"""
    return rbac_manager.has_any_permission(user_id, permissions)

async def get_user_permissions(user_id: str) -> List[str]:
    """获取用户权限列表"""
    permissions = rbac_manager.get_user_permissions(user_id)
    return [p.value for p in permissions]

# 常用权限组合
class PermissionGroup:
    """权限组合"""
    USER_MANAGEMENT = [
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE
    ]

    CHAT_MANAGEMENT = [
        Permission.CHAT_READ,
        Permission.CHAT_WRITE,
        Permission.CHAT_DELETE
    ]

    KB_MANAGEMENT = [
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.KB_DELETE
    ]

    FILE_MANAGEMENT = [
        Permission.FILE_READ,
        Permission.FILE_WRITE,
        Permission.FILE_DELETE
    ]

    TOOL_ACCESS = [
        Permission.TOOL_PYTHON,
        Permission.TOOL_SQL,
        Permission.TOOL_GIT,
        Permission.TOOL_DATA
    ]

    SYSTEM_ACCESS = [
        Permission.SYSTEM_MONITOR,
        Permission.SYSTEM_CONFIG,
        Permission.SYSTEM_ADMIN
    ]

    ADMIN = [
        Permission.USER_ADMIN,
        Permission.CHAT_ADMIN,
        Permission.KB_ADMIN,
        Permission.FILE_ADMIN,
        Permission.TOOL_ADMIN,
        Permission.SYSTEM_ADMIN,
        Permission.API_ADMIN
    ]

# 便捷装饰器
def require_user_management(func):
    """需要用户管理权限"""
    return require_permissions(PermissionGroup.USER_MANAGEMENT)(func)

def require_chat_management(func):
    """需要聊天管理权限"""
    return require_permissions(PermissionGroup.CHAT_MANAGEMENT)(func)

def require_kb_management(func):
    """需要知识库管理权限"""
    return require_permissions(PermissionGroup.KB_MANAGEMENT)(func)

def require_file_management(func):
    """需要文件管理权限"""
    return require_permissions(PermissionGroup.FILE_MANAGEMENT)(func)

def require_tool_access(func):
    """需要工具访问权限"""
    return require_permissions(PermissionGroup.TOOL_ACCESS)(func)

def require_system_access(func):
    """需要系统访问权限"""
    return require_permissions(PermissionGroup.SYSTEM_ACCESS)(func)

def require_admin(func):
    """需要管理员权限"""
    return require_permissions(PermissionGroup.ADMIN)(func)

# 资源级权限检查
class ResourcePermissionChecker:
    """资源级权限检查器"""

    @staticmethod
    async def check_chat_access(
        user_id: str,
        chat_id: str,
        required_permission: Permission = Permission.CHAT_READ
    ) -> bool:
        """
        检查聊天访问权限
        """
        # 管理员可以访问所有聊天
        if await check_user_permission(user_id, Permission.CHAT_ADMIN):
            return True

        # 检查基础权限
        if not await check_user_permission(user_id, required_permission):
            return False

        # TODO: 检查聊天所有者
        # 这里需要查询数据库验证聊天所有者

        return True

    @staticmethod
    async def check_kb_access(
        user_id: str,
        kb_id: str,
        required_permission: Permission = Permission.KB_READ
    ) -> bool:
        """
        检查知识库访问权限
        """
        # 管理员可以访问所有知识库
        if await check_user_permission(user_id, Permission.KB_ADMIN):
            return True

        # 检查基础权限
        if not await check_user_permission(user_id, required_permission):
            return False

        # TODO: 检查知识库所有者或共享权限
        # 这里需要查询数据库验证知识库权限

        return True

    @staticmethod
    async def check_file_access(
        user_id: str,
        file_id: str,
        required_permission: Permission = Permission.FILE_READ
    ) -> bool:
        """
        检查文件访问权限
        """
        # 管理员可以访问所有文件
        if await check_user_permission(user_id, Permission.FILE_ADMIN):
            return True

        # 检查基础权限
        if not await check_user_permission(user_id, required_permission):
            return False

        # TODO: 检查文件所有者
        # 这里需要查询数据库验证文件所有者

        return True