"""
RBAC权限管理API路由
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Body, Query
from pydantic import BaseModel, Field

from auth import (
    rbac_manager,
    Permission,
    Role,
    RoleDefinition,
    PREDEFINED_ROLES
)
from auth.permissions import check_user_permission, check_user_permissions
from auth.middleware import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rbac", tags=["RBAC权限管理"])

# 请求/响应模型
class RoleCreateRequest(BaseModel):
    """角色创建请求"""
    name: str = Field(..., description="角色名称", min_length=1, max_length=50)
    description: str = Field(..., description="角色描述", min_length=1, max_length=200)
    permissions: List[str] = Field(..., description="权限列表")
    parent_roles: Optional[List[str]] = Field([], description="父角色列表")

class RoleUpdateRequest(BaseModel):
    """角色更新请求"""
    description: Optional[str] = Field(None, description="角色描述")
    permissions: Optional[List[str]] = Field(None, description="权限列表")
    parent_roles: Optional[List[str]] = Field(None, description="父角色列表")

class UserRoleAssignmentRequest(BaseModel):
    """用户角色分配请求"""
    user_id: str = Field(..., description="用户ID")
    role_name: str = Field(..., description="角色名称")

# API端点
@router.get("/roles", summary="获取所有角色")
async def list_roles(
    include_system: bool = Query(True, description="是否包含系统角色"),
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    获取所有角色列表
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_READ
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:read required"
            )

        roles = rbac_manager.get_all_roles()
        result = []

        for role in roles:
            # 过滤系统角色
            if not include_system and role.is_system_role:
                continue

            result.append({
                "name": role.name,
                "description": role.description,
                "permissions": [p.value for p in role.permissions],
                "is_system_role": role.is_system_role,
                "parent_roles": list(role.parent_roles),
                "created_at": role.created_at.isoformat(),
                "updated_at": role.updated_at.isoformat()
            })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list roles: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve roles")

@router.post("/roles", summary="创建自定义角色")
async def create_role(
    request: RoleCreateRequest,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    创建自定义角色
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_ADMIN
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:admin required"
            )

        # 验证权限
        valid_permissions = [p.value for p in Permission]
        for perm in request.permissions:
            if perm not in valid_permissions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid permission: {perm}"
                )

        # 转换为权限枚举
        permissions = [Permission(perm) for perm in request.permissions]

        # 创建角色
        success = rbac_manager.create_custom_role(
            name=request.name,
            description=request.description,
            permissions=permissions,
            parent_roles=request.parent_roles
        )

        if success:
            return {"message": f"Role '{request.name}' created successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create role"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create role: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create role")

@router.put("/roles/{role_name}", summary="更新角色")
async def update_role(
    role_name: str,
    request: RoleUpdateRequest,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    更新角色信息
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_ADMIN
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:admin required"
            )

        # 验证权限
        if request.permissions:
            valid_permissions = [p.value for p in Permission]
            for perm in request.permissions:
                if perm not in valid_permissions:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid permission: {perm}"
                    )

        # 更新角色
        if request.description:
            # 这里需要实现更新描述的方法
            pass

        if request.permissions is not None:
            permissions = [Permission(perm) for perm in request.permissions]
            success = rbac_manager.update_role_permissions(role_name, permissions)
            if not success:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to update role permissions"
                )

        return {"message": f"Role '{role_name}' updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update role: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update role")

@router.delete("/roles/{role_name}", summary="删除角色")
async def delete_role(
    role_name: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    删除角色
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_ADMIN
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:admin required"
            )

        success = rbac_manager.delete_custom_role(role_name)

        if success:
            return {"message": f"Role '{role_name}' deleted successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to delete role or role not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete role: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete role")

@router.post("/users/{user_id}/roles", summary="为用户分配角色")
async def assign_role(
    user_id: str,
    request: UserRoleAssignmentRequest,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    为用户分配角色
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_WRITE
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:write required"
            )

        # 分配角色
        success = rbac_manager.assign_role_to_user(user_id, request.role_name)

        if success:
            return {"message": f"Role '{request.role_name}' assigned to user '{user_id}'"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to assign role or role not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign role: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to assign role")

@router.delete("/users/{user_id}/roles/{role_name}", summary="移除用户角色")
async def remove_role(
    user_id: str,
    role_name: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    移除用户角色
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_WRITE
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:write required"
            )

        # 移除角色
        success = rbac_manager.remove_role_from_user(user_id, role_name)

        if success:
            return {"message": f"Role '{role_name}' removed from user '{user_id}'"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to remove role or assignment not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove role: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to remove role")

@router.get("/users/{user_id}/roles", summary="获取用户角色")
async def get_user_roles(
    user_id: str,
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    获取用户的角色列表
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_READ
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:read required"
            )

        # 用户只能查看自己的角色，除非有管理员权限
        if (user_id != current_user["id"] and
            not await check_user_permission(
                current_user["id"],
                Permission.USER_ADMIN
            )):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: cannot view other users' roles"
            )

        roles = rbac_manager.get_user_roles(user_id)
        return [
            {
                "name": role.name,
                "description": role.description,
                "permissions": [p.value for p in role.permissions],
                "is_system_role": role.is_system_role
            }
            for role in roles
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user roles: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user roles")

@router.get("/users/{user_id}/permissions", summary="获取用户权限")
async def get_user_permissions(
    user_id: str,
    current_user: dict = Depends(get_current_user)
) -> List[str]:
    """
    获取用户的所有权限
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_READ
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:read required"
            )

        # 用户只能查看自己的权限，除非有管理员权限
        if (user_id != current_user["id"] and
            not await check_user_permission(
                current_user["id"],
                Permission.USER_ADMIN
            )):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: cannot view other users' permissions"
            )

        permissions = rbac_manager.get_user_permissions(user_id)
        return [p.value for p in permissions]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user permissions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user permissions")

@router.get("/check", summary="检查权限")
async def check_permission_endpoint(
    user_id: str = Query(..., description="用户ID"),
    permission: str = Query(..., description="权限名称"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    检查用户是否有特定权限
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_READ
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:read required"
            )

        # 用户只能检查自己的权限，除非有管理员权限
        if (user_id != current_user["id"] and
            not await check_user_permission(
                current_user["id"],
                Permission.USER_ADMIN
            )):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: cannot check other users' permissions"
            )

        # 验证权限
        try:
            perm_enum = Permission(permission)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid permission: {permission}"
            )

        has_permission = rbac_manager.check_permission(user_id, perm_enum)

        return {
            "user_id": user_id,
            "permission": permission,
            "has_permission": has_permission
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check permission: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check permission")

@router.get("/statistics", summary="获取角色统计信息")
async def get_statistics(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取RBAC系统统计信息
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.SYSTEM_MONITOR
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: system:monitor required"
            )

        stats = rbac_manager.get_role_statistics()

        # 添加当前用户统计
        user_id = current_user["id"]
        user_roles = rbac_manager.get_user_roles(user_id)
        user_permissions = rbac_manager.get_user_permissions(user_id)

        stats["current_user"] = {
            "user_id": user_id,
            "roles": [role.name for role in user_roles],
            "role_count": len(user_roles),
            "permissions": [p.value for p in user_permissions],
            "permission_count": len(user_permissions)
        }

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get statistics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")

@router.get("/permissions", summary="获取所有可用权限")
async def list_permissions(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, List[str]]:
    """
    获取所有可用权限列表
    """
    try:
        # 检查权限
        if not await check_user_permission(
            current_user["id"],
            Permission.USER_READ
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: user:read required"
            )

        # 按类别分组权限
        permissions = list(Permission)
        grouped = {
            "user": [],
            "chat": [],
            "kb": [],
            "file": [],
            "tool": [],
            "system": [],
            "api": []
        }

        for perm in permissions:
            prefix = perm.value.split(":")[0]
            if prefix in grouped:
                grouped[prefix].append(perm.value)
            else:
                grouped["other"] = grouped.get("other", [])
                grouped["other"].append(perm.value)

        return grouped

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list permissions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve permissions")