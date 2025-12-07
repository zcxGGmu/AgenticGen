"""
实时协作工作空间
支持多用户实时编辑、共享画板和协同编程
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import uuid
from enum import Enum
from collections import defaultdict, deque

from fastapi import WebSocket, WebSocketDisconnect
from auth.middleware import get_current_user_from_token

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """操作类型"""
    INSERT = "insert"
    DELETE = "delete"
    RETAIN = "retain"
    FORMAT = "format"


class PresenceStatus(Enum):
    """在线状态"""
    ONLINE = "online"
    AWAY = "away"
    BUSY = "busy"
    OFFLINE = "offline"


@dataclass
class User:
    """用户信息"""
    id: str
    name: str
    email: str
    avatar: str = ""
    status: PresenceStatus = PresenceStatus.ONLINE
    cursor: Dict[str, Any] = field(default_factory=dict)
    color: str = "#007bff"


@dataclass
class DocumentOperation:
    """文档操作"""
    id: str
    user_id: str
    type: OperationType
    position: int
    content: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CursorPosition:
    """光标位置"""
    user_id: str
    document_id: str
    position: int
    selection: Dict[str, int] = field(default_factory=dict)


@dataclass
class Workspace:
    """工作空间"""
    id: str
    name: str
    description: str = ""
    owner_id: str = ""
    members: Set[str] = field(default_factory=set)
    documents: Dict[str, str] = field(default_factory=dict)  # doc_id -> content
    created_at: datetime = field(default_factory=datetime.now)
    settings: Dict[str, Any] = field(default_factory=dict)


class RealTimeCollaboration:
    """实时协作引擎"""

    def __init__(self):
        # 连接管理
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, Set[str]] = defaultdict(set)  # user_id -> connection_ids
        self.workspace_users: Dict[str, Set[str]] = defaultdict(set)  # workspace_id -> user_ids

        # 工作空间
        self.workspaces: Dict[str, Workspace] = {}

        # 用户信息
        self.users: Dict[str, User] = {}

        # 文档操作历史
        self.document_operations: Dict[str, List[DocumentOperation]] = defaultdict(list)
        self.operation_transformers: Dict[str, Callable] = {}

        # 光标位置
        self.cursors: Dict[str, CursorPosition] = {}

        # 消息队列
        self.message_queue = asyncio.Queue()

        # 启动消息处理循环
        asyncio.create_task(self._message_loop())

    async def connect_user(
        self,
        websocket: WebSocket,
        token: str
    ) -> Optional[str]:
        """
        用户连接
        """
        try:
            # 验证用户
            user_info = await get_current_user_from_token(token)
            if not user_info:
                await websocket.close(code=4001, reason="Unauthorized")
                return None

            user_id = user_info["id"]

            # 创建用户对象
            if user_id not in self.users:
                self.users[user_id] = User(
                    id=user_id,
                    name=user_info.get("name", f"User_{user_id[-4:]}"),
                    email=user_info.get("email", ""),
                    avatar=user_info.get("avatar", "")
                )

            # 生成连接ID
            connection_id = str(uuid.uuid4())

            # 接受连接
            await websocket.accept()

            # 存储连接
            self.active_connections[connection_id] = websocket
            self.user_connections[user_id].add(connection_id)

            # 更新用户状态
            self.users[user_id].status = PresenceStatus.ONLINE

            logger.info(f"User {user_id} connected with connection {connection_id}")

            return connection_id

        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            await websocket.close(code=4000, reason="Connection failed")
            return None

    async def disconnect_user(self, connection_id: str):
        """
        用户断开连接
        """
        try:
            # 移除连接
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]

            # 查找用户
            user_id = None
            for uid, connections in self.user_connections.items():
                if connection_id in connections:
                    connections.remove(connection_id)
                    user_id = uid
                    break

            # 更新用户状态
            if user_id and not self.user_connections[user_id]:
                self.users[user_id].status = PresenceStatus.OFFLINE

            logger.info(f"Connection {connection_id} disconnected")

        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")

    async def create_workspace(
        self,
        name: str,
        description: str = "",
        owner_id: str = None
    ) -> str:
        """
        创建工作空间
        """
        workspace_id = str(uuid.uuid4())

        workspace = Workspace(
            id=workspace_id,
            name=name,
            description=description,
            owner_id=owner_id or "",
            members=set([owner_id]) if owner_id else set()
        )

        self.workspaces[workspace_id] = workspace

        logger.info(f"Created workspace {workspace_id}: {name}")
        return workspace_id

    async def join_workspace(
        self,
        user_id: str,
        workspace_id: str,
        connection_id: str
    ) -> bool:
        """
        加入工作空间
        """
        try:
            workspace = self.workspaces.get(workspace_id)
            if not workspace:
                return False

            # 添加用户到工作空间
            workspace.members.add(user_id)
            self.workspace_users[workspace_id].add(user_id)

            # 通知其他用户
            await self._broadcast_to_workspace(
                workspace_id,
                {
                    "type": "user_joined",
                    "user": asdict(self.users[user_id]),
                    "workspace_id": workspace_id
                },
                exclude_connection=connection_id
            )

            # 发送工作空间信息
            await self._send_to_connection(connection_id, {
                "type": "workspace_joined",
                "workspace": {
                    "id": workspace.id,
                    "name": workspace.name,
                    "description": workspace.description,
                    "members": [
                        asdict(self.users[mid])
                        for mid in workspace.members
                        if mid in self.users
                    ]
                }
            })

            logger.info(f"User {user_id} joined workspace {workspace_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to join workspace: {str(e)}")
            return False

    async def leave_workspace(
        self,
        user_id: str,
        workspace_id: str
    ):
        """
        离开工作空间
        """
        try:
            workspace = self.workspaces.get(workspace_id)
            if not workspace:
                return

            # 从工作空间移除用户
            workspace.members.discard(user_id)
            self.workspace_users[workspace_id].discard(user_id)

            # 通知其他用户
            await self._broadcast_to_workspace(
                workspace_id,
                {
                    "type": "user_left",
                    "user_id": user_id,
                    "workspace_id": workspace_id
                }
            )

            logger.info(f"User {user_id} left workspace {workspace_id}")

        except Exception as e:
            logger.error(f"Failed to leave workspace: {str(e)}")

    async def handle_document_operation(
        self,
        operation: Dict[str, Any],
        connection_id: str
    ):
        """
        处理文档操作
        """
        try:
            # 创建操作对象
            doc_op = DocumentOperation(
                id=str(uuid.uuid4()),
                user_id=operation["user_id"],
                type=OperationType(operation["type"]),
                position=operation["position"],
                content=operation.get("content", ""),
                attributes=operation.get("attributes", {})
            )

            # 转换操作（处理并发）
            transformed_ops = await self._transform_operation(
                doc_op,
                operation["document_id"]
            )

            # 应用操作
            await self._apply_operation(doc_op, operation["document_id"])

            # 广播操作
            for workspace_id, workspace in self.workspaces.items():
                if operation["document_id"] in workspace.documents:
                    await self._broadcast_to_workspace(
                        workspace_id,
                        {
                            "type": "document_operation",
                            "operation": asdict(doc_op),
                            "transformed_operations": [asdict(op) for op in transformed_ops]
                        },
                        exclude_connection=connection_id
                    )
                    break

        except Exception as e:
            logger.error(f"Failed to handle document operation: {str(e)}")

    async def handle_cursor_update(
        self,
        cursor: Dict[str, Any],
        connection_id: str
    ):
        """
        处理光标更新
        """
        try:
            cursor_pos = CursorPosition(
                user_id=cursor["user_id"],
                document_id=cursor["document_id"],
                position=cursor["position"],
                selection=cursor.get("selection", {})
            )

            # 更新光标位置
            self.cursors[f"{cursor_pos.user_id}_{cursor_pos.document_id}"] = cursor_pos

            # 广播光标位置
            for workspace_id, workspace in self.workspaces.items():
                if cursor["document_id"] in workspace.documents:
                    await self._broadcast_to_workspace(
                        workspace_id,
                        {
                            "type": "cursor_update",
                            "user_id": cursor["user_id"],
                            "document_id": cursor["document_id"],
                            "position": cursor["position"],
                            "selection": cursor.get("selection", {}),
                            "color": self.users[cursor["user_id"]].color
                        },
                        exclude_connection=connection_id
                    )
                    break

        except Exception as e:
            logger.error(f"Failed to handle cursor update: {str(e)}")

    async def _transform_operation(
        self,
        operation: DocumentOperation,
        document_id: str
    ) -> List[DocumentOperation]:
        """
        转换操作以解决冲突
        """
        # 获取未转换的操作
        pending_ops = [
            op for op in self.document_operations[document_id]
            if op.id != operation.id and op.timestamp > operation.timestamp
        ]

        transformed_ops = []
        current_op = operation

        # 对每个未转换的操作进行转换
        for pending_op in pending_ops:
            transformed = await self._transform_pair(current_op, pending_op)
            if transformed:
                current_op = transformed
                transformed_ops.append(transformed)

        return transformed_ops

    async def _transform_pair(
        self,
        op1: DocumentOperation,
        op2: DocumentOperation
    ) -> Optional[DocumentOperation]:
        """
        转换两个操作
        """
        # 简单的转换规则
        if op1.type == OperationType.INSERT and op2.type == OperationType.INSERT:
            if op1.position <= op2.position:
                return None  # 无需转换
            else:
                # 移动op1的位置
                new_op = DocumentOperation(
                    id=op1.id,
                    user_id=op1.user_id,
                    type=op1.type,
                    position=op1.position + len(op2.content),
                    content=op1.content,
                    attributes=op1.attributes
                )
                return new_op

        elif op1.type == OperationType.DELETE and op2.type == OperationType.INSERT:
            if op1.position <= op2.position:
                return None  # 无需转换
            else:
                # 移动删除位置
                new_op = DocumentOperation(
                    id=op1.id,
                    user_id=op1.user_id,
                    type=op1.type,
                    position=op1.position + len(op2.content),
                    content=op1.content,
                    attributes=op1.attributes
                )
                return new_op

        # TODO: 实现更多转换规则

        return None

    async def _apply_operation(
        self,
        operation: DocumentOperation,
        document_id: str
    ):
        """
        应用操作到文档
        """
        # 查找工作空间
        for workspace in self.workspaces.values():
            if document_id in workspace.documents:
                content = workspace.documents[document_id]

                # 应用操作
                if operation.type == OperationType.INSERT:
                    content = (
                        content[:operation.position] +
                        operation.content +
                        content[operation.position:]
                    )
                elif operation.type == OperationType.DELETE:
                    end_pos = operation.position + len(operation.content)
                    content = content[:operation.position] + content[end_pos:]

                # 更新文档
                workspace.documents[document_id] = content

                # 记录操作
                self.document_operations[document_id].append(operation)

                # 限制历史大小
                if len(self.document_operations[document_id]) > 1000:
                    self.document_operations[document_id] = self.document_operations[document_id][-500:]

                break

    async def _broadcast_to_workspace(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        exclude_connection: str = None
    ):
        """
        向工作空间广播消息
        """
        workspace = self.workspaces.get(workspace_id)
        if not workspace:
            return

        # 获取工作空间中所有用户的连接
        connections_to_send = set()
        for user_id in workspace.members:
            for conn_id in self.user_connections.get(user_id, set()):
                if conn_id != exclude_connection and conn_id in self.active_connections:
                    connections_to_send.add(conn_id)

        # 发送消息
        for conn_id in connections_to_send:
            await self._send_to_connection(conn_id, message)

    async def _send_to_connection(
        self,
        connection_id: str,
        message: Dict[str, Any]
    ):
        """
        向特定连接发送消息
        """
        try:
            websocket = self.active_connections.get(connection_id)
            if websocket:
                await websocket.send_text(json.dumps(message))

        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {str(e)}")
            # 清理无效连接
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]

    async def _message_loop(self):
        """
        消息处理循环
        """
        while True:
            try:
                # 处理消息队列
                while not self.message_queue.empty():
                    message = await self.message_queue.get()
                    # 处理消息
                    await self._process_message(message)

                # 定期清理
                await self._cleanup_connections()

                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Message loop error: {str(e)}")
                await asyncio.sleep(1)

    async def _process_message(self, message: Dict[str, Any]):
        """
        处理消息
        """
        # TODO: 实现消息处理逻辑
        pass

    async def _cleanup_connections(self):
        """
        清理无效连接
        """
        to_remove = []

        for conn_id, websocket in self.active_connections.items():
            try:
                # 发送心跳
                await websocket.ping()
            except:
                to_remove.append(conn_id)

        for conn_id in to_remove:
            await self.disconnect_user(conn_id)

    async def get_workspace_info(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """
        获取工作空间信息
        """
        workspace = self.workspaces.get(workspace_id)
        if not workspace:
            return None

        return {
            "id": workspace.id,
            "name": workspace.name,
            "description": workspace.description,
            "owner_id": workspace.owner_id,
            "members": [
                asdict(self.users[mid])
                for mid in workspace.members
                if mid in self.users
            ],
            "documents": workspace.documents,
            "created_at": workspace.created_at.isoformat()
        }

    async def get_active_users(self, workspace_id: str) -> List[Dict[str, Any]]:
        """
        获取活跃用户
        """
        workspace = self.workspaces.get(workspace_id)
        if not workspace:
            return []

        active_users = []
        for user_id in workspace.members:
            if user_id in self.users and self.user_connections.get(user_id):
                active_users.append(asdict(self.users[user_id]))

        return active_users


# 全局实例
collaboration_engine = RealTimeCollaboration()