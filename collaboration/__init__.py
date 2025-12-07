"""
实时协作系统
提供多用户文档协作、白板共享和实时同步功能
"""

from .workspace import (
    RealTimeCollaboration,
    User,
    Workspace,
    DocumentOperation,
    CursorPosition,
    PresenceStatus,
    OperationType,
    collaboration_engine
)

from .whiteboard import (
    Whiteboard,
    WhiteboardManager,
    DrawingElement,
    ShapeType,
    DrawingTool,
    Point,
    BoundingBox,
    whiteboard_manager
)

__all__ = [
    # 协作引擎
    "RealTimeCollaboration",
    "collaboration_engine",

    # 工作空间
    "User",
    "Workspace",
    "DocumentOperation",
    "CursorPosition",
    "PresenceStatus",
    "OperationType",

    # 白板
    "Whiteboard",
    "WhiteboardManager",
    "DrawingElement",
    "ShapeType",
    "DrawingTool",
    "Point",
    "BoundingBox",
    "whiteboard_manager"
]