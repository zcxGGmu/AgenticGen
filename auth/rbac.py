"""
RBAC (Role-Based Access Control) 权限系统
实现基于角色的访问控制
"""

from enum import Enum
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Permission(Enum):
    """权限枚举"""
    # 用户管理权限
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    USER_ADMIN = "user:admin"

    # 聊天权限
    CHAT_READ = "chat:read"
    CHAT_WRITE = "chat:write"
    CHAT_DELETE = "chat:delete"
    CHAT_ADMIN = "chat:admin"

    # 知识库权限
    KB_READ = "kb:read"
    KB_WRITE = "kb:write"
    KB_DELETE = "kb:delete"
    KB_ADMIN = "kb:admin"

    # 文件权限
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    FILE_DELETE = "file:delete"
    FILE_ADMIN = "file:admin"

    # 工具权限
    TOOL_PYTHON = "tool:python"
    TOOL_SQL = "tool:sql"
    TOOL_GIT = "tool:git"
    TOOL_DATA = "tool:data"
    TOOL_ADMIN = "tool:admin"

    # 系统权限
    SYSTEM_MONITOR = "system:monitor"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_ADMIN = "system:admin"

    # API权限
    API_ACCESS = "api:access"
    API_ADMIN = "api:admin"

    @classmethod
    def all_permissions(cls) -> Set['Permission']:
        """获取所有权限"""
        return set(cls)

class Role(Enum):
    """角色枚举"""
    # 系统角色
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"

    # 业务角色
    DEVELOPER = "developer"
    ANALYST = "analyst"
    EDITOR = "editor"
    VIEWER = "viewer"

    # 自定义角色前缀
    CUSTOM = "custom"

@dataclass
class RoleDefinition:
    """角色定义"""
    name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    is_system_role: bool = True
    parent_roles: Set[Role] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

# 预定义角色权限映射
PREDEFINED_ROLES: Dict[Role, RoleDefinition] = {
    Role.SUPER_ADMIN: RoleDefinition(
        name="超级管理员",
        description="拥有所有权限的系统管理员",
        permissions=set(Permission),
        is_system_role=True
    ),

    Role.ADMIN: RoleDefinition(
        name="管理员",
        description="拥有大部分管理权限的管理员",
        permissions={
            Permission.USER_READ, Permission.USER_WRITE,
            Permission.CHAT_READ, Permission.CHAT_WRITE, Permission.CHAT_DELETE,
            Permission.KB_READ, Permission.KB_WRITE, Permission.KB_DELETE,
            Permission.FILE_READ, Permission.FILE_WRITE, Permission.FILE_DELETE,
            Permission.TOOL_PYTHON, Permission.TOOL_SQL, Permission.TOOL_GIT, Permission.TOOL_DATA,
            Permission.SYSTEM_MONITOR,
            Permission.API_ACCESS
        },
        is_system_role=True
    ),

    Role.MODERATOR: RoleDefinition(
        name="版主",
        description="内容审核和管理者",
        permissions={
            Permission.CHAT_READ, Permission.CHAT_WRITE, Permission.CHAT_DELETE,
            Permission.KB_READ, Permission.KB_WRITE,
            Permission.FILE_READ,
            Permission.SYSTEM_MONITOR
        },
        is_system_role=True
    ),

    Role.DEVELOPER: RoleDefinition(
        name="开发者",
        description="编程开发者",
        permissions={
            Permission.CHAT_READ, Permission.CHAT_WRITE,
            Permission.KB_READ, Permission.KB_WRITE,
            Permission.FILE_READ, Permission.FILE_WRITE,
            Permission.TOOL_PYTHON, Permission.TOOL_SQL, Permission.TOOL_GIT,
            Permission.API_ACCESS
        },
        is_system_role=True
    ),

    Role.ANALYST: RoleDefinition(
        name="数据分析师",
        description="数据分析员",
        permissions={
            Permission.CHAT_READ, Permission.CHAT_WRITE,
            Permission.KB_READ, Permission.KB_WRITE,
            Permission.FILE_READ, Permission.FILE_WRITE,
            Permission.TOOL_PYTHON, Permission.TOOL_SQL, Permission.TOOL_DATA,
            Permission.API_ACCESS
        },
        is_system_role=True
    ),

    Role.EDITOR: RoleDefinition(
        name="编辑者",
        description="内容编辑者",
        permissions={
            Permission.CHAT_READ, Permission.CHAT_WRITE,
            Permission.KB_READ, Permission.KB_WRITE,
            Permission.FILE_READ, Permission.FILE_WRITE,
            Permission.API_ACCESS
        },
        is_system_role=True
    ),

    Role.VIEWER: RoleDefinition(
        name="查看者",
        description="只读用户",
        permissions={
            Permission.CHAT_READ,
            Permission.KB_READ,
            Permission.FILE_READ,
            Permission.API_ACCESS
        },
        is_system_role=True
    )
}

class RBACManager:
    """RBAC管理器"""

    def __init__(self):
        self.roles: Dict[str, RoleDefinition] = {}
        self.user_roles: Dict[str, Set[str]] = {}  # user_id -> set of role_names
        self.role_hierarchy: Dict[str, Set[str]] = {}  # role_name -> set of parent roles
        self.custom_roles: Dict[str, RoleDefinition] = {}
        self._initialize_roles()

    def _initialize_roles(self):
        """初始化预定义角色"""
        for role, definition in PREDEFINED_ROLES.items():
            self.roles[role.value] = definition

        # 建立角色层次结构
        self.role_hierarchy = {
            "viewer": set(),
            "editor": {"viewer"},
            "analyst": {"viewer"},
            "developer": {"viewer"},
            "moderator": {"viewer", "editor"},
            "admin": {"moderator", "developer", "analyst"},
            "super_admin": {"admin"}
        }

    def create_custom_role(
        self,
        name: str,
        description: str,
        permissions: List[Permission],
        parent_roles: Optional[List[str]] = None
    ) -> bool:
        """
        创建自定义角色

        Args:
            name: 角色名称
            description: 角色描述
            permissions: 权限列表
            parent_roles: 父角色列表

        Returns:
            是否创建成功
        """
        try:
            if name in self.roles:
                logger.warning(f"Role already exists: {name}")
                return False

            # 验证父角色
            if parent_roles:
                for parent in parent_roles:
                    if parent not in self.roles:
                        logger.error(f"Parent role not found: {parent}")
                        return False

            custom_role = RoleDefinition(
                name=f"{Role.CUSTOM.value}:{name}",
                description=description,
                permissions=set(permissions),
                is_system_role=False,
                parent_roles=set(parent_roles) if parent_roles else set()
            )

            self.roles[custom_role.name] = custom_role
            self.custom_roles[custom_role.name] = custom_role

            logger.info(f"Created custom role: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create custom role: {str(e)}")
            return False

    def assign_role_to_user(self, user_id: str, role_name: str) -> bool:
        """
        为用户分配角色

        Args:
            user_id: 用户ID
            role_name: 角色名称

        Returns:
            是否分配成功
        """
        try:
            if role_name not in self.roles:
                logger.error(f"Role not found: {role_name}")
                return False

            if user_id not in self.user_roles:
                self.user_roles[user_id] = set()

            self.user_roles[user_id].add(role_name)
            logger.info(f"Assigned role {role_name} to user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to assign role: {str(e)}")
            return False

    def remove_role_from_user(self, user_id: str, role_name: str) -> bool:
        """
        移除用户的角色

        Args:
            user_id: 用户ID
            role_name: 角色名称

        Returns:
            是否移除成功
        """
        try:
            if user_id in self.user_roles and role_name in self.user_roles[user_id]:
                self.user_roles[user_id].remove(role_name)
                logger.info(f"Removed role {role_name} from user {user_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to remove role: {str(e)}")
            return False

    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """
        获取用户的所有权限（包括继承的权限）

        Args:
            user_id: 用户ID

        Returns:
            权限集合
        """
        permissions = set()

        if user_id not in self.user_roles:
            return permissions

        # 获取用户的所有角色及其父角色
        all_roles = set()
        for role_name in self.user_roles[user_id]:
            all_roles.add(role_name)
            # 添加继承的角色
            all_roles.update(self._get_inherited_roles(role_name))

        # 收集所有权限
        for role_name in all_roles:
            if role_name in self.roles:
                permissions.update(self.roles[role_name].permissions)

        return permissions

    def _get_inherited_roles(self, role_name: str) -> Set[str]:
        """获取角色继承的所有父角色"""
        inherited = set()
        to_check = [role_name]

        while to_check:
            current = to_check.pop()
            if current in self.role_hierarchy:
                for parent in self.role_hierarchy[current]:
                    if parent not in inherited:
                        inherited.add(parent)
                        to_check.append(parent)

        return inherited

    def check_permission(self, user_id: str, permission: Permission) -> bool:
        """
        检查用户是否有特定权限

        Args:
            user_id: 用户ID
            permission: 权限

        Returns:
            是否有权限
        """
        user_permissions = self.get_user_permissions(user_id)
        return permission in user_permissions

    def check_permissions(self, user_id: str, permissions: List[Permission]) -> bool:
        """
        检查用户是否有所有指定权限

        Args:
            user_id: 用户ID
            permissions: 权限列表

        Returns:
            是否有所有权限
        """
        user_permissions = self.get_user_permissions(user_id)
        return all(perm in user_permissions for perm in permissions)

    def has_any_permission(self, user_id: str, permissions: List[Permission]) -> bool:
        """
        检查用户是否有任意一个指定权限

        Args:
            user_id: 用户ID
            permissions: 权限列表

        Returns:
           是否有任意权限
        """
        user_permissions = self.get_user_permissions(user_id)
        return any(perm in user_permissions for perm in permissions)

    def get_user_roles(self, user_id: str) -> List[RoleDefinition]:
        """
        获取用户的所有角色

        Args:
            user_id: 用户ID

        Returns:
            角色定义列表
        """
        if user_id not in self.user_roles:
            return []

        role_definitions = []
        for role_name in self.user_roles[user_id]:
            if role_name in self.roles:
                role_definitions.append(self.roles[role_name])

        return role_definitions

    def get_all_roles(self) -> List[RoleDefinition]:
        """
        获取所有角色定义

        Returns:
            角色定义列表
        """
        return list(self.roles.values())

    def get_custom_roles(self) -> List[RoleDefinition]:
        """
        获取所有自定义角色

        Returns:
            自定义角色列表
        """
        return list(self.custom_roles.values())

    def update_role_permissions(
        self,
        role_name: str,
        permissions: List[Permission]
    ) -> bool:
        """
        更新角色权限（仅限自定义角色）

        Args:
            role_name: 角色名称
            permissions: 新的权限列表

        Returns:
            是否更新成功
        """
        try:
            if role_name not in self.roles:
                logger.error(f"Role not found: {role_name}")
                return False

            role = self.roles[role_name]
            if role.is_system_role:
                logger.error(f"Cannot modify system role: {role_name}")
                return False

            role.permissions = set(permissions)
            role.updated_at = datetime.now()

            logger.info(f"Updated permissions for role: {role_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update role permissions: {str(e)}")
            return False

    def delete_custom_role(self, role_name: str) -> bool:
        """
        删除自定义角色

        Args:
            role_name: 角色名称

        Returns:
            是否删除成功
        """
        try:
            if role_name not in self.roles:
                return False

            role = self.roles[role_name]
            if role.is_system_role:
                logger.error(f"Cannot delete system role: {role_name}")
                return False

            # 检查是否有用户使用该角色
            for user_id, user_role_set in self.user_roles.items():
                if role_name in user_role_set:
                    logger.error(f"Cannot delete role, still in use by user: {user_id}")
                    return False

            del self.roles[role_name]
            if role_name in self.custom_roles:
                del self.custom_roles[role_name]

            logger.info(f"Deleted custom role: {role_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete role: {str(e)}")
            return False

    def get_role_statistics(self) -> Dict[str, Any]:
        """
        获取角色统计信息

        Returns:
            统计信息字典
        """
        stats = {
            "total_roles": len(self.roles),
            "system_roles": 0,
            "custom_roles": len(self.custom_roles),
            "total_users": len(self.user_roles),
            "role_usage": {},
            "permission_distribution": {}
        }

        # 统计系统角色和自定义角色
        for role in self.roles.values():
            if role.is_system_role:
                stats["system_roles"] += 1

        # 统计角色使用情况
        role_usage = {role_name: 0 for role_name in self.roles.keys()}
        for user_roles in self.user_roles.values():
            for role_name in user_roles:
                role_usage[role_name] = role_usage.get(role_name, 0) + 1
        stats["role_usage"] = role_usage

        # 统计权限分布
        permission_count = {perm.value: 0 for perm in Permission}
        for role in self.roles.values():
            for perm in role.permissions:
                permission_count[perm.value] = permission_count.get(perm.value, 0) + 1
        stats["permission_distribution"] = permission_count

        return stats

# 全局RBAC管理器实例
rbac_manager = RBACManager()

# 权限装饰器
def require_permission(permission: Permission):
    """
    权限装饰器

    Args:
        permission: 需要的权限
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 这里需要从请求中获取用户ID
            # 具体实现取决于框架
            user_id = kwargs.get('user_id')
            if not user_id:
                raise PermissionError("User not authenticated")

            if not rbac_manager.check_permission(user_id, permission):
                raise PermissionError(f"Permission required: {permission.value}")

            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_permissions(permissions: List[Permission]):
    """
    多权限装饰器

    Args:
        permissions: 需要的权限列表
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            user_id = kwargs.get('user_id')
            if not user_id:
                raise PermissionError("User not authenticated")

            if not rbac_manager.check_permissions(user_id, permissions):
                raise PermissionError(f"Permissions required: {[p.value for p in permissions]}")

            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_any_permission(permissions: List[Permission]):
    """
    任意权限装饰器

    Args:
        permissions: 权限列表（满足任意一个即可）
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            user_id = kwargs.get('user_id')
            if not user_id:
                raise PermissionError("User not authenticated")

            if not rbac_manager.has_any_permission(user_id, permissions):
                raise PermissionError(f"One of permissions required: {[p.value for p in permissions]}")

            return await func(*args, **kwargs)
        return wrapper
    return decorator

class PermissionError(Exception):
    """权限错误"""
    pass